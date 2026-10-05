# Windows HTTP 完整性修复进度

## 范围与结论

- 基线：`492fe191e3f9568ea178b61970c732c9d37c4e29`。
- 修改范围仅为 `core/server/http_store.py` 与 `tests/test_http_file_tasks.py`。
- 根因已由 Windows 原生实测锁定：源文件的两个 `os.open` 调用未带 `O_BINARY`，Windows C 运行库把 `\n` 转为 `\r\n`，导致物理文件与 producer 字节不一致；长度与 SHA-256 拒绝是正确行为，未放宽校验。
- 修复为两个源文件打开点直接补 `getattr(os, "O_BINARY", 0)`；POSIX 上该值为 0，原语义保持不变。

## 字节证据

独立 Windows `win32/nt` Python 3.11.7 探针使用同一份含 NUL、LF、CRLF、`0x1a` 和非零字节的 payload，对照当前 flags 与显式二进制 flags：

| 打开方式 | flags | 写后物理长度 | 恢复后物理长度 | oracle 长度 | byte equal | SHA equal | LF（实际/源） | CRLF（实际/源） |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| 当前默认 | 1282 | 44 | 42 | 41 | false | false | 2/3 | 2/1 |
| `O_BINARY` | 34050 | 41 | 41 | 41 | true | true | 3/3 | 1/1 |

因此失败位于 `http_store.py` 的 Windows 文件读写语义，不在 SDK producer、HTTP handler 的 payload 或 SHA/length/offset 判定。

## TDD 与验证

- Windows 原生旧实现红测：新增 HTTP 跨边界测试在真实 `AssertionError` 处失败，落盘前缀 `b"\x00A\r\nB\r\r\nC"` 与 producer 前缀 `b"\x00A\nB\r\nC"` 不等。
- Windows 原生修复绿测：同一测试 `1 passed`；覆盖二段 PATCH、已确认 offset 后的未确认物理尾、严格 readback/SHA、commit `202`、commit replay 同一 Job。
- Windows 原生候选服务：新目录、复用已有模型缓存目录联接；真实 SDK、HTTP listener、ffmpeg、Paraformer worker 完成 tiny gold 弱网显式 resume 与 77 秒 WAV 正常上传，最终 `uploads=2 COMMITTED`、`jobs=2 DONE`、`results=2`。tiny gold 为 137036 字节（物理文件同长、确认 offset 同长、LF 559/559），77 秒 WAV 为 2469966 字节（物理文件同长、确认 offset 同长、LF 8866/8866）；两任务都断言源与磁盘逐字节相等、SHA 相等、结果 token 非空、commit replay 不新增 Job；初次 commit 与重放状态分别断言为 `202` 与 `200`。
- 本地 `pytest -q tests/test_http_store.py tests/test_http_client.py`：`36 passed`。
- 本地新增 HTTP listener 测试因开发环境缺少 `aiohttp` 被跳过，未将该跳过计作通过；Windows 原生已实际执行同一测试。Windows 仓库 pytest 配置另有插件导入失配，已用 `--noconftest` 执行该测试，失败原因仍是业务断言而非导入或环境空跑。
- `git diff --check`、限定文件 `compileall` 通过。

## 本轮补验收（dlg-20261005-074250-f6b02e）

- Linux 全量 CI 栈两套顺序执行：`uv run --no-project --python 3.12`，pytest 9.1.1 / pytest-asyncio 1.4.0 / aiohttp 3.14.3 / httpx 0.28.1，另加 numpy/rich/colorama/soundfile；共享 `flock --timeout 600` + `timeout 900`；每套先 `mkdir` 独立 `TMPDIR`；失败即停、未重跑。套件 1 钉 `websockets==15.0.1`：`490 passed, 7 skipped, 163 warnings in 244.35s`，rc=0。套件 2 不钉 websockets，实际解析 `17.2`：`490 passed, 7 skipped, 163 warnings in 261.55s`，rc=0。七条 skip 均为依赖/环境缺项（ForceAligner 两项、本机 ffmpeg+user systemd 四项、silero-VAD/onnxruntime 一项），不是缺 aiohttp 空跑。Python 实际为 3.12.3。原本地 36 passed 与 HTTP filetasks 1 skip（缺 aiohttp）事实保留，未回填。
- Windows 隔离 cached CPython 3.12.12 新建专属 venv，pytest 9.1.1 / pytest-asyncio 1.4.0 / aiohttp 3.14.3 / httpx 0.28.1 / websockets 15.0.1，加载项目 conftest（未使用 `--noconftest`）。旧实现 `492fe191e3f9568ea178b61970c732c9d37c4e29` 叠加新测试：`1 failed in 2.18s`，真实 `AssertionError`，落盘前缀 `b"\x00A\r\nB\r\r\nC"` 与 producer `b"\x00A\nB\r\nC"` 在 index 2 处 `b"\r" != b"\n"`；无 ImportError/INTERNALERROR。候选 `0bb836e37eab8314e1e5fb29681a7d10ece7ce4d`：`1 passed in 0.73s`。Python 3.11.7 + `--noconftest` 的历史红绿仍作独立事实保留，不改写成 3.12。
- 第一枚 PID 探针按启动后进程树记录 launcher 24008、server 17692、两个 multiprocessing 子进程 2504/28384；CTRL_BREAK 后四者精确 PID+创建时间均 gone，退出码 3221225786，`server_forced=false`。日志未能解析识别子进程 PID。第二枚必要小探针用候选目录私有 helper 在真实 `ProcessManager.start()` 之后写出身份：launcher 24832 ≠ server 7628，recognizer 14456（parent 7628，启动前存活），manager 13704（parent 7628，启动前存活）；health `ok` / paraformer / `worker_alive=true`。CTRL_BREAK 后四者精确身份均 gone，退出码仍为 3221225786，未强杀。旧 Task15 子进程身份保持 unknown，不用本轮数字回填。
- 字节对照链只报告相等布尔：真实 SDK `rb` PATCH 为 TCP producer；handler 以 204/`Upload-Offset` 确认；磁盘物理长度与源相等；声明 size/SHA 与磁盘 readback/SHA 相等。tiny gold 137036 与 77 秒 WAV 2469966 两任务均为 `source_byte_equal=true`、`sha_equal=true`，commit 202 / replay 200，独立 SQLite 重开 `uploads=2 COMMITTED`、`jobs=2 DONE`、`results=2`。摘要不写私有 hex。`getattr(os, "O_BINARY", 0)` 是 POSIX 无该常量时为 0、NT 上为真实二进制位的接口选项，不是业务 fallback。旧 8 个 UPLOADING 损坏源未截断、清理或修复。
- 本轮只追加本文档；实现与测试文件未再改。未开 PR、未标 ready、未 merge、未重跑 Gate、未部署生产。

## 未能判定项

- 派发时主干基线查询不可用，继承红与新红无法按同名 CI 步骤区分；本地未运行 Gate，不声称 CI 结果。
- 本卡未执行生产部署、旧损坏上传自动修复或全平台完整质量矩阵。
- 旧 Task15 启动记录里 launcher 之外的子进程身份仍 unknown。

## 组合交付验证（dlg-20261005-093848-fe9697）

- 远端 `origin/master` 实际为 `902400887445603a58f7dc960a24e809ca779a0a`（含已合 probe #77 与 ffmpeg 缺则失败 #79）。四份已审输入按 normal merge、无 squash/amend/rewrite：`9e0dd6db68e30c2d9c109705957845aca7d77f03`（源修在其父 `0bb836e37eab8314e1e5fb29681a7d10ece7ce4d`）、`6cb69885606a4012d9ea0c6a54c3ec7fba963c5b`、`2a6b76443f3abe95b9376b3ba9aa38b33688b1d4`、`1776101eaab0b57daedc0457fc0deb4bda0a33f3`。相对 902 仅六条允许路径：`core/server/http_store.py`、`tests/test_http_file_tasks.py`、本进度文档与三份 review 原文。未回滚 probe/FFmpeg 测试。
- 冻结代码头（文档追加前）`e222d19cadb22f72330f72f3b316a8fed6170fde`。生产运行模块按机械路径集合（`core/server/`、`sdk/`、`tools/`、`config_server.py`、`config_proxy.py`、`start_server.py`、`start_proxy.py`）共 197 个非空路径，与 9e **逐字节相等**。known-false：9e vs `492fe191e3f9568ea178b61970c732c9d37c4e29` 的 `core/server/http_store.py` 长度 47706 vs 47601，exit 1；无效 ref 与非空 diff 分态（bad-ref 128）。因此 Windows 三机/41 红绿与 POSIX 21/25 边界仍归属原 9e 证据，**不是**本组合 head 新跑模型或最终三机 runtime。
- 新组合全量不得复用旧 490+7 或 probe 499+3。本卡真实跑组合 head：`uv run --no-project --python 3.12`，pytest 9.1.1 / pytest-asyncio 1.4.0 / aiohttp 3.14.3 / httpx 0.28.1 / numpy / rich / colorama / soundfile；共享 `~/.cache/caps-http-261005-fullsuite.lock` flock timeout 600 + timeout 900；每套先 mkdir 独立 TMPDIR。套件 1 钉 `websockets==15.0.1`（实际 15.0.1，Python 3.12.3）：queue_s≈0.002，exec_s=299.06，`55 failed, 421 passed, 3 skipped, 70 warnings, 24 errors in 298.23s`，rc=1。套件 2（unpin，预期实际 17.2）因 fail-stop **未跑**，未加 timeout、未改 skip、未改他人 ffmpeg 测试。
- 三条 skip 均为资源缺项，不是应用质量：`tests.test_aligner_integration::test_aligner_loads_not_fallback`、`::test_aligner_produces_token_timestamps`（ForceAligner 后端/模型未安装）、`tests.test_segmenter.py:208`（缺 silero-VAD 模型或 onnxruntime）。**不是** ffmpeg / aiohttp / user systemd skip。`test_http_cleanup` 15 passed / 4 failed，失败均在 `naked-shell`（探针在 ready/pre_fatal 前以「再见！」rc=1 退出，或 120s 未产出报告）；systemd 侧用例在上述 15 passed 中实际跑过。`test_http_store` 16 passed。组合套件内 `test_http_binary_payload_survives_append_recovery_and_commit_replay` **passed**。其余失败以 `EOFError`（45）与 setup `EOFError`（24）为主；`test_options_missing_and_none_default_but_falsy_wrong_types_are_rejected` 在全量中 409≠400，隔离复跑该用例与二进制用例 `2 passed in 0.28s`，不把隔离绿写成第二套全量。
- 主干基线作业查询派发时失败，继承红 **未能判定**。本组合全量红记为 **新红（本卡实测）**，不声称与 902 同环境对照。旧 8 个损坏 UPLOADING 与旧 unknown 缺口不改写、不宣布根因已消失。未部署生产，未改 Goal/index，未标 ready。

## 正式 python -m pytest 两套入口（dlg-20261005-114620-eb018f）

- 续接前核对：PR82 仍 OPEN/Draft，head `946bc99860709e3908032667367a6f48a4e4bdef`。远端 master 实际 `6aa76f6c6935e9cef00afc1bcbcf8327e7c95488`（相对 902 仅 `docs/maintainers/project-memory.md` +31，无生产/测试/workflow 源变）。normal merge 为 `075edcbc8bbf903a4b3b5ee688ea4359e0da722d`。非文档源（core/sdk/tools/tests/.github/config/start）287 路径与 946 逐字节相等；生产 197 路径仍与 9e 相等。known-false：946 vs 492 的 `http_store.py` 47706 vs 47601，exit 1；bad-ref 128。因此仍复用 9e 端点的 Windows 21/25 与 POSIX 物证，不是本 head 新跑三机。未 merge PR83。
- 独立 meta probe（与全量不同 argv）：cwd=工作树根；父进程 `sys.executable` 为系统 python3，uv 解释器为 cache 构建目录下的 3.12.3；Store/SDK/start 工作树=HEAD=946=9e 为真，测试文件工作树=HEAD=946 为真（相对 9e 非生产集合、不要求相等）。TMPDIR 预建可写。白名单 env 键长度另见本卡私有 `meta-probe.json`，未读完整 env/凭据。
- 原 27 入口是 `pytest -q -ra --tb=line --junitxml=… tests`，结果 `55 failed / 24 errors / 421 passed / 3 skipped`、rc=1、套件 2 未跑，原日志与 JUnit **原字节保留**。本续接补的是标准 `python -m pytest tests/ -q -rs -p no:cacheprovider`，不是把那条命令再跑一遍刷绿。未完成的 `--with` 顺序偏差启动已中止，未当一次全量结果。
- 套件 1 精确 argv：`uv run --no-project --python 3.12 --with numpy --with rich --with websockets==15.0.1 --with colorama --with pytest==9.1.1 --with soundfile --with pytest-asyncio==1.4.0 --with aiohttp==3.14.3 --with httpx==0.28.1 python -m pytest tests/ -q -rs -p no:cacheprovider`。cwd=源根；argv 相对卡面无增量。实际版本 python 3.12.3 / websockets 15.0.1 / pytest 9.1.1 / pytest-asyncio 1.4.0 / aiohttp 3.14.3 / httpx 0.28.1。queue_s≈0.002，exec_s=262.74，`55 failed, 421 passed, 3 skipped, 70 warnings, 24 errors in 262.02s`，`__EXEC_RC__=1`（进程标记，非事后构造）。套件 2（`--with websockets` 不钉）因 fail-stop **未跑**。不声称旧 55/24 根因已修，也不把定向 2 node 绿当全量。
- skip：`tests/test_aligner_integration.py:53`、`:62`（ForceAligner 后端/模型未安装）、`tests/test_segmenter.py:208`（缺 silero-VAD 或 onnxruntime）。不是 HTTP/ffmpeg/aiohttp/systemd skip。首个异常类型 `EOFError`，stdlib `multiprocessing/connection.py:399` `_recv`；rc=1。最大尚缺条件：标准全量入口在本消费环境下仍非 all-passed，未加第四泛诊断。
- 只追加本文档；源码/测试/三份 review 未改。未 Ready、未 merge、未改 Goal。
