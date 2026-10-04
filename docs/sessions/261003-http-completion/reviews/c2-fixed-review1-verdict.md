# C2 固定增量独立审查结论

- 固定范围：`820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..9ef0e52145bc89610fb322724462955fb2fad15a`
- 风险档：internal
- 代码与测试范围：6 个文件（3 个服务端模块、fixture 包初始化文件、真实进程探针、cleanup whole test）
- 审查结论：未发现 P1；记录 2 条 P2，不阻塞本轮审查。
- 变更：本审查没有修改服务端或测试代码。

failure-visibility: p2-only

## 四问

| 问题 | 结论 | 依据 |
|---|---|---|
| 本轮是否只修登记在案的 findings？ | 无法核验 | 当前任务禁止读取原 review/verdict，且没有另附 finding 登记清单；不据此推断通过。 |
| 是否新增未经批准的抽象？ | 未发现 | `_drain_after_fatal()` 被两个异常分支调用；`HttpIoWorker` 同时服务 HTTP 请求、启动/关闭和周期清理。`tests/fixtures/__init__.py` 是新增真实 fixture 包入口。 |
| 是否无依据增加状态、第二事实源或 fallback？ | 未发现 | 新状态只用于服务生命周期与 cleanup task；终态年龄仍只读持久化 `terminal_at`，没有新增协议状态或重试路径。 |
| 是否留下双路径？ | 是，P2 | `CapsWriterServer.stop()` 发起一次 `HttpServer.stop()`；`HttpServer.serve()` 的 `finally` 也会调用它。信号停机时已实测两次并发进入，第二次跳过在途 cleanup drain。 |

## Findings

### P2：fatal 与信号关闭同一事件循环时，`_drain_after_fatal()` 可能再次启动 loop

- 位置：`core/server/app.py:181-193`；早退条件在 `core/server/app.py:61-67`，HTTP 完成回调在 `core/server/app.py:82-91`。
- 对应不变式：运行期 fatal 应回收资源并以非零退出；正常 SIGTERM 应保留 0 退出。
- OCR 标注：high，confirmed。人工结论：P2，触发顺序尚未在真实运行中复现。
- 实测：真实 App、HTTP listener、worker、Manager 与在途 cleanup I/O 均在运行时，先投递 SIGTERM，再经 `HttpServer.report_fatal(ValueError)` 触发非 `RuntimeError`。进程以非零状态退出，没有永久挂起；当时信号 stop 的 HTTP 收尾回调仍待完成，随后结束 loop。
- 未证实部分：OCR 所说的精确时序要求 `finish_http_shutdown` 已经调用 `loop.stop()`，随后同一次 `run_until_complete()` 又以非 `RuntimeError` 抛出，并使 `_drain_after_fatal()` 再次调用 `run_forever()`。该排列在这次真实进程探针中没有出现。代码上有窄竞态可能，但没有证据把它定为 P1。
- P1 两问：真实使用路径中实际触发？本轮未观察到 OCR 所需的精确时序。若永久挂起，监督器会看不到退出；后果在该前提下不可接受，但触发未证实，故按 P2 记录。

### P2：并发 `HttpServer.stop()` 会让第二个调用跳过 cleanup task 等待

- 位置：`core/server/http_server.py:303-321`；两个调用点为 `core/server/app.py:82` 与 `core/server/http_server.py:274-279`。
- 对应不变式：清理 I/O 完成并由 worker callback 观察后，才回收 runner、aiohttp listener 和单 I/O worker。
- OCR 标注：medium，confirmed。人工结论：P2，具体跳过 drain 已在真实路径复现。
- 实测顺序：已持久化的 TCP DONE Job 真实 source 被老化超过七天；周期 cleanup 在单 I/O worker 中处理该具体 source 时阻塞；真实 SIGTERM 进入第一次 stop（cleanup task 存在且 I/O in-flight）；`serve()` 的 `finally` 随后进入第二次 stop，看到 `_source_cleanup_task is None` 且 I/O 仍 in-flight，于是越过 `gather()`。随后仅对该 source 注入 `PermissionError`。源文件、DONE Job 与结果 payload 均保留；第二次 stop 最终返回，worker/store/runner 都已释放。
- 实测边界：确认了第二个 stop 跳过 drain；没有观察到数据丢失、重复解码或 systemd 重启失败。探针没有稳定捕获 runner 与 AppRunner 开始 teardown 的精确先后，因此不把 OCR 关于重复 `AppRunner.cleanup()` 异常的推断写成已发生事实。
- P1 两问：真实使用路径中实际触发？是，SIGTERM 下观察到两次 stop。触发后果不可接受？本轮未观察到；目标 source 与结果保留，且 SIGTERM 是正常停止请求，因此不判 P1。

## 不变式与测试索引

| 关键不变式 | 实现 | 锁定测试 / 实测 |
|---|---|---|
| 只清理有 `terminal_at`、状态为 DONE/FAILED 且到期的源 | `core/server/http_store.py:773-805` | `test_store_cleanup_uses_terminal_boundary_and_keeps_every_other_source`；真实 HTTP/systemd DONE 与 FAILED 回合 |
| runner/decoder 仍持有引用时不删源 | `core/server/http_server.py:281-294`、`core/server/http_store.py:796-801` | `test_periodic_cleanup_waits_for_real_runner_reference_then_keeps_result`；其 active-reference 反向变异使断言转红 |
| partial、Job、upload 元数据和结果按契约保留；result replay 不创建新 Job | `core/server/http_store.py:773-805` | `test_periodic_cleanup_waits_for_real_runner_reference_then_keeps_result`（含真实 HTTP create/commit replay 与 Job 数量断言） |
| append、commit、record_result 与 cleanup 共用单 I/O worker | `core/server/http_server.py:83-134` | `test_upload_io_and_cleanup_share_one_worker_five_times` |
| runtime fatal 关闭监听、回收进程并非零退出 | `core/server/app.py:142-193` | `test_fatal_cleanup_exits_process_and_reaps_children`；fatal 反向变异使 exit-code 断言转红 |
| startup 装配失败回收已创建 worker 与 Manager | `core/server/app.py:142-176` | `test_http_startup_failure_exits_nonzero_without_hanging_worker`；额外裸 shell 探针确认两个 PID 先真实存活、再消失 |
| 正常 SIGTERM 与默认 WebSocket-only 生命周期兼容 | `core/server/app.py:61-93` | `test_normal_sigterm_still_exits_zero`、`test_http_disabled_keeps_default_websocket_lifecycle` |

## 验证结果

- 目标 cleanup 测试：websockets 15.0.1 与当前 latest 16.0 各 13 passed。
- 全量测试（websockets 15.0.1）：459 passed，3 skipped，149 warnings。
- 全量测试（latest websockets 16.0）：459 passed，3 skipped，149 warnings，217.21s。
- 唯一跳过项：两项 ForceAligner 后端/模型测试与一项 silero-VAD/onnxruntime 测试；没有 HTTP decode 路径跳过。
- 实际 systemd `Restart=on-failure`：修正控制器对 `NRestarts` 的计数判据后完成 5 轮，DONE/FAILED 交替；每轮均看到两个不同 InvocationID 和两个不同 MainPID，两个主进程自然以状态 1 退出，最后仅停止确认过的自有 unit。另有第 6 轮 DONE 用于运行时源码指纹，结果相同。每个 unit 最多两次实际启动，最终 cgroup 为空。
- 裸 shell：5 轮，DONE/FAILED 交替；每轮进程自然非零退出、PID 消失、具体源文件保留、SQLite 状态与 producer 字节一致。FAILED 回合为 `decode_failed`，不要求存在结果 payload。
- 两条最小反向变异：fatal 非零退出断言、active runner 引用保护断言都在目标测试中转红，mutation source 路径在 scratch worktree 内确认，scratch-worktree 随后移除了各自的 dirty tree。
- 主干基线：派发时 GitHub API 查询不可用；继承红无法判定，没有据此归责。

## 运行时源码指纹与证据

第 6 轮真实 systemd unit `dlg-20261004-041827-ff748e-c2-v2-r6` 在两个实际 Invocation 中都记录了加载函数的文件 SHA-256 和代码对象 SHA-256。两个 Invocation 的指纹一致：

- `core/server/app.py` SHA-256：`b3a58909d45451978d17903a66eb3bd215e2aa142316f72f5a85bf69f6681520`
- `CapsWriterServer.start` loaded code SHA-256：`ba6056eb450f672524ae8cd31e8682a250afe83d6b3fa5a909d6adf92440558d`
- `CapsWriterServer._drain_after_fatal` loaded code SHA-256：`faf14d419c3affa050091ab86521b36179df2f1a790a846f6608edb243285de4`
- `core/server/http_server.py` SHA-256：`1d286dc38656e6cf34142f18ae676ad3d1b08b36d767636c806eefe81bbfcf35`
- `HttpServer.stop` loaded code SHA-256：`6083f5aa5bab95e4aea28ecbd07f2331cec27268b0d57e5dd27fce1188e95ced`
- `core/server/http_store.py` SHA-256：`23055c5cffd334762f19d7233bff8221ee3b973f7c4080d99fdb141eac035394`
- `HttpStore.cleanup_terminal_sources` loaded code SHA-256：`758f81473e3dbcb90fbc7b8fcf0af006404733ee5ef709fcea29fde7292fea27`

唯一临时证据目录保留在 `scripts/tmp/c2-fixed-review1-261004/`。systemd 生产者脚本为 `systemd_restart_probe.py`；事件、unit Invocation/MainPID、cleanup callback、存储状态与拒删计数保存在 `summary.jsonl`。没有对生产服务或模型权重做操作。首次 systemd 控制器因把 `NRestarts` 误当启动数而中止；该轮在证据中保留并明确标为控制器判据错误，后续修正后独立重跑，没有把它算作产品通过或隐藏的产品失败。

## 未知项

- `_drain_after_fatal()` 的永久挂起只在“stop 完成回调先运行、非 RuntimeError 在同一次 run_until_complete 收尾又完成”的窄时序成立；本轮没有观察到该时序。
- 并发 stop 已确认跳过 cleanup task drain，但 runner teardown 与 worker cleanup I/O 的开始时间没有稳定观测；未推断其必然导致 AppRunner 异常。
- GitHub 基线不可用，所以无法分类基线继承红。
