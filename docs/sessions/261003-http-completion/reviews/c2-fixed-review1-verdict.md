# C2 固定增量独立审查结论

- 固定审查范围：820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..9ef0e52145bc89610fb322724462955fb2fad15a；不追后续分支。
- 风险档：internal。固定差异共 15 个路径，其中 6 个是本轮服务端/测试代码；其他文档未作内容审查。
- 实质结论：没有达到 P1 的 finding；记录两条 P2，failure-visibility 为 p2-only。
- 执行结论：冷输入边界被我一次检索意外破坏，不能把本轮作为完整合规的独立冷审。完整经过见“输入边界偏差”。
- 本审查没有修改产品代码或测试代码。

failure-visibility: p2-only

## 四问

| 问题 | 结论 | 依据 |
|---|---|---|
| 本轮是否只修登记在案的 findings？ | 无法核验 | 任务没有附 finding 登记清单，且禁止读取既有 review/verdict；不推断此前登记内容。 |
| 是否新增未经批准的抽象？ | 未发现 | HttpIoWorker 在固定差异前已存在。新增清理 task 的生命周期字段直接服务周期清理与 stop 排空；没有扩展出新的配置层或通用包装。 |
| 是否无依据增加状态、第二事实源或 fallback？ | 未发现 | 源龄仍仅取持久化 jobs.terminal_at；终态仍只认 DONE/FAILED；未增加协议状态、重试或自动重识别。新增字段是清理任务的内部生命周期记录。 |
| 是否留下双路径？ | 是，P2 | CapsWriterServer.stop() 与 HttpServer.serve() 的 finally 都会调用 HttpServer.stop()。真实 SIGTERM 探针观察到第二次调用在清理 I/O 仍在途时跳过 drain。 |

## Findings

### P2：fatal 收尾在信号 stop 已结束后可能再次启动事件循环

- 位置：core/server/app.py:181。_drain_after_fatal() 调用 stop() 后，只要 HTTP 已启用就无条件执行 loop.run_forever()；stop() 在 is_alive=False 时会立即返回，不再安排停止回调。
- 对应不变式：运行期 fatal 必须回收资源并以非零退出；正常 SIGTERM 必须保持零退出；未知运行期 RuntimeError 不应被吞掉（design §7）。
- OCR 标注：high / confirmed。人工判定：条件性 P2，未达到 P1。
- 真实运行测量：六轮 systemd fatal 重启、五轮裸 shell fatal 退出，以及一轮 SIGTERM 与清理 I/O fatal 交错，没有观察到 OCR 所说的精确排列——信号 stop 完成回调已经运行，之后同一次 run_until_complete() 又抛出非 RuntimeError 并进入 _drain_after_fatal()。额外的启动期 RuntimeError 探针在 HTTP 装配前运行，is_alive 仍为 true，成功排空后以状态 1 退出；它不覆盖该窄时序。
- 两问：真实使用方式下实际触发？本轮未触发该特定时序。若进入无待执行 stop 回调的 run_forever()，进程可能挂住、监督器看不到退出，后果不可接受；但第一问没有实测命中，因此不判 P1。该路径保留为待跟进 P2。

### P2：并发 HttpServer.stop() 的第二个调用跳过在途 cleanup drain

- 位置：core/server/http_server.py:303。第一个调用先将 _source_cleanup_task 置空再等待；并发调用会看到空引用，跳过 gather()，提前调用 file_runner.stop()。两个调用点分别为 app.py:82 与 http_server.py:279。
- 对应不变式：设计要求清理只删 terminal_at 超过七天、状态为 DONE/FAILED 且无活跃 runner 引用的登记源；所有写入/删除共用单 I/O worker；shutdown 必须等在途 I/O 完成（design §7、M4 plan §5 T6–T8）。
- OCR 标注：medium / confirmed。人工判定：P2。
- 真实触发：隔离裸 shell 中运行真实 App、HTTP listener、Manager/识别子进程及 SQLite；真实 TCP DONE 上传完成后将该任务老化，阻塞单 I/O worker 的具体源清理，再发送真实 SIGTERM。第 1 次 stop 看到 cleanup task 存在且 I/O in-flight；serve() 的 finally 进入第 2 次 stop，看到 task 已为空、I/O 仍在途；file_runner.stop() 在 I/O 完成前开始并结束，I/O worker 的 close 则排在清理 I/O 完成后。
- 结果：对该具体源注入的 PermissionError 被 _mark_fatal 观察到；该混合路径的 serve() 随后因取消结束，_serve_all 与 App 以状态 0 返回。源文件、DONE Job、COMMITTED upload 及结果仍在，未见丢数据或重识别。正常 SIGTERM 本来应返回 0，失败只影响过期源清理，下一次服务启动可重试；因此真实触发为“是”，但本轮观察到的后果不属不可接受的 P1。该状态码遮蔽及 teardown 重叠按 P2 记录。
- 未证实部分：有效探针没有稳定捕获 AppRunner cleanup 的开始顺序，也没有观察到重复 cleanup 抛错；不把 OCR 对 aiohttp 重复 cleanup 的推断写成已发生事实。该探针用屏障拉长真实 I/O 时窗，证明可达性，不用于推断自然发生频率。

## 不变式与锁定证据

| 不变式 | 实现位置 | 锁定测试或实测 |
|---|---|---|
| 只清理有 terminal_at、状态为 DONE/FAILED 且满七天的源；保留其他源 | http_store.py:773-805 | test_store_cleanup_uses_terminal_boundary_and_keeps_every_other_source；真实 TCP/systemd DONE 与 FAILED 回合 |
| runner 仍持有真实任务引用时不删源 | http_server.py:281-294、http_store.py:796-801 | test_periodic_cleanup_waits_for_real_runner_reference_then_keeps_result；active-reference 反向变异使断言转红 |
| partial、jobs、uploads、results 保留；结果重放不建新识别任务 | http_store.py:773-805 | HTTP producer 的 create/patch/commit/replay 与 Job 计数断言；systemd/bare 存储状态与 producer 字节摘要 |
| append、commit、record_result 和清理共用单 I/O worker | http_server.py:83-134、281-294 | test_upload_io_and_cleanup_share_one_worker_five_times；停机在途 I/O 探针 |
| runtime fatal 关闭监听、回收子进程并以非零退出 | app.py:142-193 | test_fatal_cleanup_exits_process_and_reaps_children；fatal 反向变异使 exit-code 断言转红；裸 shell 5 轮与真实 systemd 6 轮 |
| startup RuntimeError 在 Manager/worker 创建后仍回收并非零退出 | app.py:142-176 | 临时真实进程探针：两进程先存活、随后都消失，服务状态 1 |
| 正常 SIGTERM 与 HTTP-disabled WebSocket 默认生命周期不变 | app.py:61-93 | test_normal_sigterm_still_exits_zero、test_http_disabled_keeps_default_websocket_lifecycle；固定依赖全量套件 |

## 验证结果

- 定向 tests/test_http_cleanup.py：websockets 15.0.1 与 17.2 各 13 passed。
- 全量固定 websockets 15.0.1：459 passed, 3 skipped, 149 warnings，221.67 秒；3 项 skip 是 2 个 ForceAligner 后端/模型项和 1 个 silero-VAD/onnxruntime 项。
- 全量最新 websockets 17.2：裸 shell 下 455 passed, 7 skipped, 149 warnings，206.66 秒。额外 4 项 skip 是测试内 systemd-unit launcher 未继承用户 session 环境；它们由下方真实 user systemd 探针补测。没有 HTTP decode 测试跳过。
- 真实 user systemd Restart=on-failure：有效 v2 探针共 6 个独立 unit，每个限制最多两次启动、RuntimeMaxSec=80s、StartLimitBurst=2。每轮均有两个不同 InvocationID/MainPID；第一个自然 fatal 退出后 systemd 自然拉起第二次，第二次再自然 fatal 退出；最终 unit 为 failed/ExecMainStatus 1，cgroup 为空。4 轮处理真实 DONE、2 轮处理真实 FAILED/decode_failed；各轮两次具体源 unlink denial，源与数据库记录保留。没有人为 kill 制造重启。裸 shell 另 5 轮，DONE/FAILED 交替，均非零退出，PID 消失且源和终态记录保留。
- Startup RuntimeError 额外探针：注入点在真实 Manager 与识别 worker 均启动之后、HTTP listener 装配之前；二者在注入前 alive=true，退出时 alive=false，主进程退出码 1。
- 两条最小反向变异均在固定 base 9ef0e52145bc89610fb322724462955fb2fad15a 的 scratch worktree 中完成：fatal 非零边界和 active runner 引用保护分别触发预期 AssertionError；消费源确认含变异，scratch helper 随后移除各自 worktree。
- OCR 为三态中的 reviewed_fallback：primary=leg_timeout; backup:deepseek=success；完整 JSON 位于临时 OCR 输出。机器 severity 只作输入，本 verdict 按真实触发与后果逐条重判。

## 监督产物与源码指纹

- 原始阶段证据：scripts/tmp/c2-fixed-review1-261004/summary.jsonl；含每阶段实际 argv/env、PID、cgroup、InvocationID、健康状态、SQLite 终态及 source/result 字节摘要。没有在报告中展开环境值或原始响应体。
- 第 6 轮 unit：dlg-20261004-041827-ff748e-c2-v2-r6，目录 scripts/tmp/c2-fixed-review1-261004/systemd-v2-6/。两个 invocation 的文件与加载代码指纹一致：
  - core/server/app.py source SHA-256 b3a58909d45451978d17903a66eb3bd215e2aa142316f72f5a85bf69f6681520；CapsWriterServer.start loaded-code SHA-256 ba6056eb450f672524ae8cd31e8682a250afe83d6b3fa5a909d6adf92440558d；_drain_after_fatal loaded-code SHA-256 faf14d419c3affa050091ab86521b36179df2f1a790a846f6608edb243285de4。
  - core/server/http_server.py source SHA-256 1d286dc38656e6cf34142f18ae676ad3d1b08b36d767636c806eefe81bbfcf35；HttpServer.stop loaded-code SHA-256 6083f5aa5bab95e4aea28ecbd07f2331cec27268b0d57e5dd27fce1188e95ced。
  - core/server/http_store.py source SHA-256 23055c5cffd334762f19d7233bff8221ee3b973f7c4080d99fdb141eac035394；cleanup_terminal_sources loaded-code SHA-256 758f81473e3dbcb90fbc7b8fcf0af006404733ee5ef709fcea29fde7292fea27。
- 初次 systemd 控制器把 NRestarts 误按成启动总数并提前中止；该轮保留但排除统计，随后修正为按 InvocationID/MainPID 数独立重跑 6 轮。只停止核实过的本卡 unit。
- 测试反向变异的第一条临时记录曾包含合成 fixture 的完整 pytest AssertionError 行；已用保留脚本清除原始断言文本，只保留测试 ID 与 AssertionError 类别。临时摘要现不含该 payload 行。
- 本地 .git/info/exclude 增加了该卡临时证据目录的精确忽略项；证据目录保留在 worktree 内供核验。

## 输入边界偏差与未知项

- 输入边界偏差：查找测试命令时，我执行了一次覆盖 docs/ 的 rg 搜索；其输出命中了任务明令排除的既有 review/evidence 片段，我读取了这些搜索命中。这里不复述、不把那些旧记录作为结论依据；但这使“全新冷输入”条件客观上没有满足。固定源代码、规格、实际运行和新生成探针证据仍独立审查。基于该偏差，派发执行结果标记 failed，并建议另派干净上下文复审。
- OCR finding 1 的永久挂起窄时序没有在真实进程中复现；启动 RuntimeError 的实测不覆盖信号后异常排列。
- 并发 stop 已确认跳过 drain 并在 I/O 仍运行时停止 idle runner；未观测 AppRunner cleanup 的精确先后，也未证明会造成数据损坏或资源泄漏。
- 派发时 GitHub API 基线不可用；继承红无法判定。
