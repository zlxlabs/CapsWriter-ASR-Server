# fatal 探针 producer/consumer 独立 review

- 审查范围：`492fe191e3f9568ea178b61970c732c9d37c4e29..185035e4df95f7497e74d8dfd50f2b469cb6c3af`
- 文件：`tests/fixtures/http_fatal_exit_probe.py`、`tests/test_http_cleanup.py`、`docs/sessions/261003-http-completion/progress/fatal-probe-contract-progress.md`
- 风险等级：internal
- 判定：发现一项 P2 测试环境缺口；未发现本 diff 引入的 P1。
- failure-visibility: p2-only

## P2：无会话环境能启动 user unit，但测试进程无法读取和清理它

新 `_user_bus_env()` 被 `_systemd_usable()` 和 `ProbeRun.start()` 使用，令无会话 shell 中的 `systemd-run --user` 能实际启动探针。相同的 bus 环境没有传给 `ProbeRun._unit_properties()`、`cleanup()` 的 `systemctl --user`，以及 `log_tail()` 的 `journalctl --user`。在 `env -i` 且当前 UID 有同属主 user bus 的本机环境中，探针进程确实启动并退出，但 `_unit_properties()` 收到空属性，`_wait_unit_loaded()` 超时；四个 systemd 测试节点均在模式断言前失败。

复现命令使用项目测试文档指定的 Python 3.12 `uv run --no-project` 依赖集，并以 `env -i` 启动，仅显式设置 `HOME` 和 `PATH`：`tests/test_http_cleanup.py -q -p no:cacheprovider`。结果为 **14 passed / 4 failed / 0 skipped**；失败节点是 fatal、SIGTERM、HTTP 初始化失败、HTTP disabled 各自的 `[systemd-unit]` 参数。四个节点的 systemd 子进程均运行了对应 fixture，但测试没有检查其结果，不能算作这四种 systemd consumer case 已通过。此缺口违反 `goals/http-integration/M6-qa.md` 对 bare shell/systemd 消费环境与实际收集结果的要求。

**本仓 P1 两问：**

1. 真实使用方式下会触发吗？**会。** 本次在无会话环境实际确认同属主 user bus 可用；四个 systemd 参数均被收集并启动了 unit。
2. 后果能否接受？**不按 P1。** 后果是测试显式失败并阻止该套件通过；没有证据表明服务运行结果静默错误、数据丢失、越权或崩溃，低于 internal 档 P1 红线。

最小修正方向：让 `_unit_properties()`、`cleanup()` 与 `log_tail()` 的 user manager 命令也使用同一个 owner-scoped bus 环境，并保留命令失败/属性缺失时的可见失败。本卡不实施修复。

## Producer / consumer 证据

| 不变式 | 代码与实际 consumer | 审查结果 |
|---|---|---|
| fatal 写入后、loop 停止前同步落盘 | fixture `_install_mark_fatal_observer()` 保存真实 `_mark_fatal`，先调用原方法，再确认 `self.fatal` 已存储，随后调用 `_emit_post_fatal()`；`emit()` 追加 JSONL、flush 并 fsync。 | 顺序正确；没有轮询、异常吞掉或伪造 App 方法。重复 fatal 仍执行原方法，仅不重复写首次事件。 |
| fatal payload 来自真实路径 | 全链路 fixture 先实际上传 WAV、走 HTTP/ffmpeg/TaskHandler/SQLite，等待真实 Job DONE 并释放 runner 引用，再对具体 source unlink 注入 PermissionError；pre_fatal 与 post_fatal 使用同一 source SHA 和 job_id。 | 主 fatal consumer 从子进程报告文件字节解析 JSONL，并核对类型、消息、source SHA 与 job_id；source/Job/SQLite reopen/端口与进程回收原断言仍在。ASR 引擎使用固定测试假引擎；ProcessManager、multiprocessing Manager、OS worker 进程、HTTP、ffmpeg、TaskHandler 和 SQLite 边界是真实对象。 |
| IO worker 构造期 callback 产生新事件 | `HttpServer.prepare()` 构造 `HttpIoWorker(self._mark_fatal)`；observer 在 `app.start()` 使 HttpServer 实例化/prepare 之前安装。`test_io_worker_bound_mark_fatal_and_disconnect_negative` 从独立文件读 producer 实际字节，且把实例 `_mark_fatal` 晚绑改坏后仍触发原 bound callback。 | 文件初始为空/不存在，fatal 前为 None；具体 PermissionError 后消费成功。断开 `_on_failure` 的负样本没有 JSONL。 |
| 原 cleanupDone 保持原方法且产生独立新事件 | 生产 `_on_source_cleanup_done` 仍调用 `self._mark_fatal(exc)`；identity 测试确认安装 observer 后函数对象不变。`test_original_cleanup_done_fresh_jsonl_and_negatives` 在另一独立空路径调用保存的原函数对象。 | 新文件只由该事件写出；错误 job/type 与晚绑实例负例不能满足 positive consumer。未把 worker 文件的旧行复用为 cleanupDone 证据。 |
| 同一 turn 的 loop.stop 不丢 post_fatal | `same_turn_observer` 子进程调用真实 `HttpServer._mark_fatal(PermissionError)` 后在同一 `call_soon` callback 调 `loop.stop()`；父测试直接读该子进程实际写入的文件 bytes。 | 当前目标下 consumer 通过。红验中抑制 observer 落盘后，真实 fatal 已写入但该 consumer 断言转红。 |
| 非 fatal 生命周期不多报 phase | SIGTERM、HTTP disabled、HTTP 初始化失败测试均断言没有 `post_fatal`。 | 裸环境节点通过；systemd 参数因上述 setup 缺口失败，不能把它们记作验证通过。 |

`_FATAL_SNAPSHOT` 是测试 fixture 的单进程单服务快照，用来把稍后发生的真实 fatal 与先前取得的同一 source/job 元信息关联；它不是第二份业务账本。`_user_bus_env()` 有 preflight 和 launcher 两个消费者，抽象有现实第二调用方，但当前漏接了 manager 查询、日志与清理调用。

## 红验与工具结果

- 使用 `scratch-worktree.sh` 在基线 `492fe191...` 建临时树，只把冻结目标的 fixture 与测试文件拷入；生产 `core/server` 保持基线字节。一次注入在真实 `_mark_fatal` 写入后抑制 JSONL 落盘，marker 证明实际 `PermissionError` 到达 observer；same-turn 子进程的文件 consumer 按预期失败。
- 第二次注入在 worker 构造前不安装 observer；真实 `HttpIoWorker.run()` 的 PermissionError 仍由已绑定原 `_mark_fatal` 存储，测试明确确认 `server.fatal` 后，独立 worker JSONL consumer 按预期失败。两次都不是 ImportError、空 collector 或未触发 producer 的假红；临时树已清理。
- OCR 包装器 stdout 是完整 JSON（413 bytes）：`status=skipped`、`reason=no_reviewable_items`、`findings=[]`。这是 skipped，不是干净扫描；以上结论来自独立人工 review。
- 冻结 SHA 的 GitHub check-runs `total_count=0`，commit status contexts `total_count=0` 且整体 `pending`，无 hosted CI 结论。派发给出的主干基线 API 失败原因未知；继承红未能判定。
- 首次误用系统 Python 的模块导入因缺少 aiohttp 得到 `1 skipped`、退出码 5，未计作测试结果。正式测试入口随后按项目文档改用 Python 3.12 uv 依赖集；唯一正式模块运行结果见 P2 finding，未重跑追绿。
- `git diff --check 492fe191... 185035e4...` 通过；冻结区间 `core/server` 与 `sdk` 无差异。
