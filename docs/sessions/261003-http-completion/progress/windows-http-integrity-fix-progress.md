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
