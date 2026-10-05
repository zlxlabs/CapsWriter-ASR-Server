# PR82 组合全量真实红：只读分层归因与主干对照

## 结论

在本次固定依赖、同机、同调用环境的全量对照里，远端主干 `6aa76f6` 与候选 `946bc99` 都只出现同样的 2 个失败，候选新增的二进制 payload 测试通过；没有观察到候选新增红。Actor27 旧现场的 55 failed / 24 errors 指纹与本次两臂完全不同，旧首因仍为 **unknown**：旧运行没有保留足以确认实际导入模块、`PYTHONPATH`、ffmpeg、会话总线和首个因果帧的记录，今天的同机环境不能替代它。

因此，本次可确认的「继承红」是受控环境中主干与候选共有的 2 个 `test_http_baseline` 失败；旧现场 55/24 是否继承或新引入，不能判定。当前对照没有新红。没有实施源码、测试或 CI 修改。

## 旧现场与 producer

- 旧源码冻结头：`e222d19cadb22f72330f72f3b316a8fed6170fde`；工件记录的 `freeze-code-head.sha` 与之相同。PR82 当前仍为 Draft，head `946bc99860709e3908032667367a6f48a4e4bdef`。
- 旧 runner 的真实命令来自 `ws15.log` 的 `CMD` 行：`uv run --no-project --python 3.12`，依次带 `numpy/rich/colorama/pytest==9.1.1/soundfile/pytest-asyncio==1.4.0/aiohttp==3.14.3/httpx==0.28.1/websockets==15.0.1`，执行 `pytest -q -ra --tb=line --junitxml=… tests`。runner 只跑 `ws15`；返回码 1 后 fail-stop，没有第二个 unpinned arm。
- 旧 JUnit：503 tests、55 failures、24 errors、421 passed、3 skipped；pytest 内部 298.23 秒，外层 299.06 秒，队列等待约 0.002 秒。异常类型安全聚类：45 个 failure 与 24 个 error 以 `EOFError` 结束，另有 9 个 `AssertionError`、1 个 `FileNotFoundError`。失败分布在 17 个模块：`test_http_file_runner` 23F，`test_backpressure` 5F，`test_http_qa_e2e` 6F，`test_error_contract` 3F+6E，`test_protocol_v2` 1F+8E，`test_server_e2e_baseline` 6E，`test_file_result_contract_e2e` 3E，`test_health` 3F，`test_http_cleanup` 4F，`test_http_baseline` 2F，`test_owner_ipc` 2F，`test_port_restart` 2F，`test_e2e_sdk_server` 1F，`test_http_file_tasks` 1F，`test_http_release_invariant` 1F，`test_segmentation_contract` 1F，`test_model_routing` 1E。`--tb=line` 的旧 XML 没有这些异常的调用帧，故不能从类型推断共同根因。
- 旧 runner 由脚本复制调用者环境、覆盖 `TMPDIR` 后以 `bash -lc` 从 runner 所在 worktree 根目录执行。可确认旧临时目录存在，权限为 `775`；旧环境变量值/键状态（除 runner 明确设置的 `TMPDIR`）、实际加载模块、ffmpeg 版本、`XDG_RUNTIME_DIR` 与 `DBUS_SESSION_BUS_ADDRESS` 状态未记录。旧三条 skip 不是 ffmpeg/aiohttp/会话总线缺失导致，这一点不作为失败因果。
- 旧锁队列、版本和 pytest 计数可由结构化工件恢复；禁止读取 provider 原始输出、完整日志、环境原值。相关记忆条目提到 SDK 假 ffprobe 恒返回会掩盖时长断言，但旧异常指纹没有证据指向该路径，未据此归因。

## 源码与导入对照

- `git ls-remote` 确认当时远端 `master` 为 `6aa76f6c6935e9cef00afc1bcbcf8327e7c95488`。`902400887445603a58f7dc960a24e809ca779a0a..6aa76f6` 只有 `docs/maintainers/project-memory.md` 变化。
- 候选生产路径 `core/server/`、`sdk/`、`tools/`、配置和启动入口逐字节等于修复源 `9e0dd6d`。相对主干，Python 改动只有 `core/server/http_store.py` 与 `tests/test_http_file_tasks.py`：前者在两处 `os.open` 增加 `getattr(os, "O_BINARY", 0)`；后者新增一个真实 producer 二进制 payload 恢复/重放用例。
- 两个受控 pytest arm 使用独立 scratch worktree，`cwd` 为对应提交根目录；Python 3.12.3 下 `os.name=posix`、`O_BINARY` 不存在、取值 0。新 flag 在这台 POSIX 环境不改变打开标志。新二进制 payload 用例在候选全量通过。
- 同依赖、同 cwd 的只读导入身份探针加载了 `tests.conftest`、`tests.test_http_file_tasks`、`core.server.http_store` 和 `capswriter_asr.http_client`；四个模块均来自各自 detached worktree。`PYTHONPATH` 未设置。主干/候选 `tests.test_http_file_tasks` SHA-256 为 `ba11e044a738b462e35c4b2e6ace4325a475624a471f211d0584b774fa81cd8e` / `8dc8e8cff1a2e11ca31060d852dea8286de6bccfdd595769887cffc28fea4c2b`；`core/server/http_store.py` 为 `23055c5cffd334762f19d7233bff8221ee3b973f7c4080d99fdb141eac035394` / `afa25f1b6bbddc2f964b061d06c86429a61ec1e6b5aa9ce360b40dfde3126576`；SDK HTTP client 两边相同（`9734b3bfdc73a41674eb55a9f9ab0b7a63d99cdd8dae0b01f6bc98762314f674`）。这些身份适用于本次受控运行，不能倒推旧现场导入路径。

## 受控 arm 环境和结果

两臂各执行一次 `pytest -q -ra --tb=line tests`，各自队列等待 0 秒、执行超时上限 900 秒，均无重试。argv 使用 Python 3.12、pytest 9.1.1、pytest-asyncio 1.4.0、aiohttp 3.14.3、httpx 0.28.1、websockets 15.0.1，另带 `numpy/rich/colorama/soundfile`。同套依赖的版本探针得到 numpy 2.5.3、rich 15.0.0、colorama 0.4.6、soundfile 0.14.0；旧 JSON 未记录 rich/colorama 版本。

| arm / 输入 | 结果 | 失败指纹 | 判定 |
| --- | --- | --- | --- |
| 旧现场 `e222d19`，原输入缺记录 | 503；55F、24E、421P、3S；rc=1 | 45F+24E 为 EOFError；其余为断言/文件缺失，分散 17 模块 | 与新 arm 不匹配；旧根因 unknown |
| 候选单例 `test_inflight_limit_stops_reads_and_returns_all_results` | 1/1 通过 | 旧 EOFError 未在该固定输入复现 | 不证明全量旧红是假红 |
| 候选单例 `test_options_missing_and_none_default_but_falsy_wrong_types_are_rejected` | 1/1 通过 | 旧断言未在该固定输入复现 | 不证明顺序污染 |
| 远端主干 `6aa76f6` 全量 | 502；2F、0E、497P、3S；rc=1 | `test_http_baseline::test_cli_http_producer_payload_and_private_json_bytes` / AssertionError；`test_empty_reference_fails_loudly_before_health_or_upload` / FileNotFoundError | 本次对照的继承红 |
| 候选 `946bc99` 全量 | 503；2F、0E、498P、3S；rc=1 | 与主干相同的两个节点、相同异常类型 | 本次对照没有新红 |

两臂版本与环境字段相同：TMPDIR 为各自独立、存在、可写、模式 `0700` 的 scratch 子目录；`PYTHONPATH`、`VIRTUAL_ENV` 未设置；PATH 长度 743；`XDG_RUNTIME_DIR` 已设置、长度 14；`DBUS_SESSION_BUS_ADDRESS` 已设置、长度 28；`CW_MAX_TASK_SECONDS`、`CW_SEGMENT_TIMEOUT`、`CW_LOG_LEVEL` 未设置。ffmpeg 存在，版本 `6.1.1-3ubuntu5+esm13`。这些是本次消费环境的安全字段，不是旧运行值。

| 旧观测 | 新 arm 指纹是否匹配 | 代码/环境依据 | 结论与最小处置 |
| --- | --- | --- | --- |
| 旧 55F/24E，主导 EOFError，跨 17 模块 | 否；单例通过，6aa 与 946 均未出现这些节点/异常 | 旧 `PYTHONPATH`、会话字段、ffmpeg 与实际模块身份缺失；今天的 TMPDIR/会话环境不可替代 | 归因为 unknown；不改代码。若必须追因，先由原 producer 补安全 provenance 和异常首帧，再开有界复现 |
| 6aa 主干 2F | 候选 946 完全匹配 | 两臂同依赖、同 runner、同安全环境字段；新增 flag 在 POSIX 为 0 | 标为本次对照继承红，不归 PR82 变更 |
| PR82 精确 head 的公共 CI | 不解释旧本地红 | py3.11、py3.12 与 py3.11/websockets 15.0.1 测试 job 成功；Draft gate 的 primary/resolve_advisory/OCR/notify 为 SKIPPED | CI 绿只说明这些 hosted job 通过；primary 没有运行，不作主审通过结论 |

## 边界与建议

已有独立记录的 naked cleanup 15 passed/4 failed、systemd cleanup passed、HttpStore 16 passed（含二进制 payload）及 options 两例通过，都是分层诊断结果，不能解释旧全量 55/24。受控全量仅说明当前 Linux/POSIX 代码组合与主干在同一环境下有相同两条红；不外推 Windows 上 O_BINARY 行为，也不把「主干也红」当成旧 55/24 的豁免证据。

建议保留这两个继承失败作为单独基线记录；旧现场标注「首因未能判定」，不据严重度猜测新代码、ffmpeg、导入路径或顺序污染。未修改实现、测试、CI、PR 状态或主干。



## 本轮两个历史失败节点的有界补诊

本轮只跑 **test_cli_http_producer_payload_and_private_json_bytes** 与 **test_empty_reference_fails_loudly_before_health_or_upload**，没有重跑全量。两个节点在一次有界依赖差分的两臂中都通过：臂 A 使用项目文档列出的 uv --no-project --python 3.12 依赖集合，未 pin 的 websockets 解析为 17.2；臂 B 只把它固定为此前全量记录中的 15.0.1。两臂其余依赖均为 numpy 2.5.3、rich 15.0.0、colorama 0.4.6、pytest 9.1.1、pytest-asyncio 1.4.0、soundfile 0.14.0、aiohttp 3.14.3、httpx 0.28.1；Python 3.12.3。每臂在同一调用中执行两个节点一次，pytest 退出码均为 0。

运行时使用临时内存观察器调用 pytest.main，把 stdout、stderr 和测试内真实 CLI 子进程结果解析为白名单字段；没有写入或修改仓库测试。当前 worktree HEAD 为 1645534485481e3b27365f6b126844df1996409b，目标脚本与测试的 SHA-256 分别为 62f4b7254bc24212553a855b7c5f32c10352be3ba4fcfbfb78e8024184e6f79a、9be0b5a4dafe0c139487243d4226b506974776664d04e21a081a356a94b09b0c；这两个文件从候选 946bc99860709e3908032667367a6f48a4e4bdef 到本 HEAD 没有变化。Python 解释器角色是 uv 的 Python 3.12 临时环境；cwd 为当前仓库根目录；测试、scripts/_baseline_http_ws.py 和 SDK HTTP/WS 模块均从当前仓库/SDK 加载。

子进程实际 argv 的脱敏角色序列为：同一 Python 解释器、scripts/_baseline_http_ws.py、--protocol http、loopback server 与 health URL、生成的 WAV、匿名 fixture ID、40 位服务 SHA、--expected-model paraformer、仓库外生成的私有目录、生成的参考稿；首测试另带 --reference-status unverified --timeout 5。第一子进程环境中测试专用 CW_MODEL_TYPE 与 sentinel 变量仅记录长度 27、20；没有输出环境值。脚本没有读取环境变量值。

第一节点的真实 CLI 子进程两臂均为 rc=0、stderr 0 字节、stdout 为 schema 1 JSON。通过测试内 TcpCapture 观察实际 loopback 请求：health GET；上传 POST 的真实 JSON 为 options/sha256/size_bytes 三个顶层字段，options 实际值为 language=null、context=null、model=paraformer、seg_duration=15.0、seg_overlap=2.0；PATCH 实际发送 364 字节，与生成的 WAV 逐字节相等；随后有 commit、两次状态查询和结果 GET。SDK 实际计量到 6 个请求、196 个 control JSON 字节、1 个 364 字节 PATCH、0 重传。CLI 实际写出的私有 JSON 工件为 4498 字节、schema 1、规范 JSON 编码、权限 0600，含 6 个 producer events；未读取或输出正文、源文件哈希、响应体或私有路径。

第二节点的真实 CLI 子进程两臂均为 rc=1、stdout 0 字节、stderr 45 字节，安全解析类型为 ValueError，包含 BASELINE_FAILED 标记；私有目录存在且为空，工件数为 0。源码顺序定位为 _run 先调用 _private_dir 创建该目录（第 456–458 行），读入 WAV 与参考稿后调用 normalize_reference；归一化结果为空时于第 466–467 行抛出 ValueError，validate_health 到第 468 行才会执行。因此该输入在 health/上传前 fail-loud，测试的 list(private_dir.iterdir()) == [] 在两臂中均成立。没有创建缺失目录或改变断言。

本轮在当前代码、当前仓库导入路径和上述两套明确依赖下均未复现这两节点失败；15.0.1 与 17.2 的差别也没有复现差异。它不证明旧全量失败由测试顺序导致。既有全量记录只保留 AssertionError / FileNotFoundError 类型，没有异常行、调用帧或 CLI 子进程状态；旧 FileNotFoundError 与测试最后枚举私有目录的语句相符，但旧记录不足以证明失败就在该行，也无法解释当时目录为何缺失。故旧全量中的两个失败首因仍为 **unknown**，不能归咎于 CLI 契约、测试夹具、依赖版本或 sourceArchive/Gitroot 边界。

处置：当前没有有证据支持的源码/测试修复点，不改代码、不改断言、不重跑全量。若要解释旧全量那次红，最小新增证据应由原消费命令在首个失败发生时记录异常函数/行号、CLI rc、stderr 安全错误类型和私有目录存在性；不需要扩大成依赖矩阵或重试到绿。
