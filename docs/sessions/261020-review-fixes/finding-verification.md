# 2026-10-20 全仓 code-review 发现复核

基线：`89a5192d950aa54b44cd5b50e0bd7b77a6557725`（与派发时 `origin/master` 一致）。代码行号均按该提交。状态值仅用 `CONFIRMED`、`REFUTED`、`PLAUSIBLE`。运行探针放在仓外 `/tmp/cw-261020-probe/`，不启动真实识别模型。

## 1. HTTP fail_job 排队超时会令服务进程退出

结论：CONFIRMED

代码证据：`core/server/http_file_runner.py:379-403` 对 `self.http.fail_job()` 使用 5 秒 `asyncio.wait_for`，任何异常都转成 `SystemExit(1)`；`core/server/http_server.py:83-116` 的 HTTP I/O worker 是 `max_workers=1` 的线程池，取消等待方不会停止已排队/执行中的 I/O；`core/server/http_store.py:688-701,703-724` 的 commit 在同一 worker 中逐块读完整源文件计算 SHA-256。

实测证据：`PYTHONPATH=. python /tmp/cw-261020-probe/io_queue_probe.py` 输出：

```text
queued_fail_job: exception=TimeoutError elapsed=5.01s timeout=5.0s pending_io=2
runner_fail_job: raises=SystemExit code=1
after_commit: pending_io=0
```

探针用一个 5.3 秒同步操作占住真实 `HttpIoWorker` 单线程，再排入失败写入；失败操作的等待方超时，底层 I/O 仍排队并最终执行。runner 的退出行为由 `fail_job` 对异常的代码分支确认。

真实部署可触发性：卡面给出的 ≤10 人局域网中，1 GiB 上限文件在存储读取速度低于约 205 MiB/s 时 SHA-256 超过 5 秒；若此时另一 HTTP 任务进入失败收尾，就会触发，具体部署磁盘速度未测。

修复方向：让终态持久化的等待语义覆盖其前方已受理的长文件校验，避免排队超时直接退出服务。

## 2. HTTP 结果 sink 会阻塞唯一 WebSocket 结果分发协程

结论：CONFIRMED

代码证据：`core/server/connection/ws_send.py:124-171` 是唯一消费 `queue_out` 的循环，HTTP 分支在 `:160-170` 直接 `await sink(result)`；`core/server/http_file_runner.py:202-228` 对每个中间/最终结果同步执行 `dumps_result`，最终段再于 `:230-243` 等待持久化并收尾，错误段于 `:245-246` 等待失败落库；`core/server/http_server.py:83-116,227-235` 让这些存储调用共用单线程 I/O worker。

实测证据：调用链追踪：`queue_out.get`（`ws_send.py:132`）→ HTTP 结果分支 `await sink`（`:160-170`）→ sink 的同步 JSON 检查或 HTTP I/O await（`http_file_runner.py:212-231`）→ 返回后才回到循环读取下一条结果。其间队列里的 WS 结果不能被该协程分发。

真实部署可触发性：一条慢盘大文件 commit（1 GiB、读取低于约 205 MiB/s）可占用共享 I/O worker 超过 5 秒；同时到达的 HTTP 终态写入会让唯一 sender 等待，≤10 人混合 HTTP/麦克风使用即可满足条件。

修复方向：避免唯一结果分发循环直接等待可能被长 I/O 排队的 HTTP sink。

## 3. HTTP commit 的准入锁与 SHA-256 会阻塞 WebSocket 新任务准入

结论：CONFIRMED

代码证据：`core/server/http_server.py:560-584` 在 `state.admission_lock` 内先查重、计数并调用同步 `commit_upload`；`commit_upload` 在 `core/server/http_store.py:703-724` 调 `_verify_source`，后者于 `:688-701` 读取全文件计算 SHA-256。WebSocket 首帧于 `core/server/connection/ws_recv.py:574-580` 获取同一把锁，并调用 `count_active_tasks`；该计数在 `core/server/state.py:122-152` 通过 `http_active_job_counter` 读取数据库，注入实现 `core/server/http_server.py:237-242` 仍走同一单线程 worker。

实测证据：串行执行链为 HTTP commit「持锁 → I/O worker 校验整文件 → 释放锁」；WS 首帧「等同一锁 → 计数 → begin_task」。`count_active_tasks` 与准入锁都没有等待超时；第 1 条的 5.3 秒单线程占用探针亦证明 I/O worker 不并行处理第二个操作。

真实部署可触发性：≤10 人部署中，只要 1 GiB 文件的完整哈希耗时超过 5 秒，期间到达的麦克风首帧就会等到哈希结束；慢 HDD/NAS 可满足该吞吐条件，部署盘速未测。

修复方向：避免把整文件哈希放在共享准入锁和唯一 I/O worker 的临界路径中。

## 4. Proxy 故障切换可能再次选中已失败后端并放弃其它后端

结论：CONFIRMED

代码证据：`core/proxy/router.py:86-133` 只按健康状态与得分选后端，没有排除 `tried`；`:206-253` 在连接失败后记录失败并继续循环，但下一轮仍可选回相同后端，若 `backend.id in tried` 则立即抛 `NoHealthyBackendError`。`core/proxy/backend.py:87-92` 只有累计失败数达到 3 才把后端标为不健康；失败计数不进入 `backend_score`（`router.py:135-136`）。

实测证据：`PYTHONPATH=. python /tmp/cw-261020-probe/runtime_probe.py` 输出：

```text
router: attempts=['ws://a'] a_healthy=True a_failures=1 b_healthy=True error=NoHealthyBackendError
```

探针设置 a 权重为 10、b 权重为 1；a 的首次连接失败后仍健康且得分更优，第二轮命中 `tried` 抛错，b 没有被尝试。

真实部署可触发性：配置了不等权重的多后端时，一个高权重后端短暂连接失败且失败次数未达 3 即可触发；单后端或同分轮转不触发此具体路径。

修复方向：选择故障切换候选时排除本次任务已经尝试过的后端。

## 5. HTTP 推理段超时会使其它活动任务失败并退出服务

结论：CONFIRMED

代码证据：`core/server/worker/process_manager.py:200-210` 检查最早未完成段的超时；WS 分支在 `:216-231` 关闭对应连接后 `continue`，只终结该 WS 任务。HTTP 分支在 `:232-240` 可靠终结当前 Job 后，仍于 `:246-253` 调 `fail_active_tasks(..., skip_key=key)` 并抛 `SystemExit(1)`；`core/server/connection/ws_send.py:81-96` 会遍历其余活动任务，HTTP 任务落库 FAILED，WS 任务排错并关闭。

实测证据：代码调用链逐行对照：默认 `CW_SEGMENT_TIMEOUT=600`（`process_manager.py:200`）→ 找到超时 HTTP key（`:201-210`）→ `finalize_http_job`（`:236-240`）→ 对其余任务调用 `fail_active_tasks`（`:246-252`）→ 进程退出（`:253`）。WS 路径在前面已 `continue`，不进入服务退出分支。

真实部署可触发性：默认需单个推理段超过 600 秒（10 分钟），或部署主动调低该环境变量；≤10 人时不常见，但单个挂住的 HTTP 推理段会中断其它活跃 WS/HTTP 任务。

修复方向：明确 HTTP 单任务超时与整个 worker/服务不可恢复故障的边界，避免仅一条任务超时就终结所有任务。

## 6. 已过期未完成上传仍占用 16 GiB 源预留

结论：CONFIRMED

代码证据：`core/server/http_store.py:378-392` 的懒过期只把 `UPLOADING` 改为 `EXPIRED`；`:427-450` 的 `_iter_present_sources` 对所有 uploads 行统计，只排除源文件已经不存在的记录，`_reserved_source_bytes` 按声明长度计费且不看状态。`cleanup_terminal_sources` 明确只将未完成上传改为 `EXPIRED` 并保留 partial 文件与 source-presence 计费（`:777-791`）；创建时的源预留上限为 16 GiB（`:526-536`）。

实测证据：`PYTHONPATH=. python /tmp/cw-261020-probe/store_probe.py` 输出：

```text
expiry: rows=16 expired=16 source_files=16 reserved_before=17179869184 next=source_reserve_full/507
```

探针在临时 SQLite/源目录中创建 16 个声明为 1 GiB 的空上传文件，再按生产清理方法过期；第 17 次创建返回 507。

真实部署可触发性：无需上传实际 16 GiB，16 个 1 GiB 未完成上传过期后即可占满声明预留；≤10 人也能在多次中断上传后累计触发，需清理数据目录/元数据才能恢复准入。

修复方向：过期未完成上传时释放其源文件和对应声明预留，或使容量核算不再把可回收过期记录永久计费。

## 7. IncompleteRead 会终止 proxy 的周期探活协程

结论：CONFIRMED

代码证据：`core/proxy/proxy_server.py:25-34` 通过 `response.read()` 读取健康响应；`:268-284` 周期探活循环没有外围异常处理，`_probe_backends` 用默认 `asyncio.gather`，而 `_probe_backend` 只捕获 `OSError`、`URLError`、`TimeoutError`。`http.client.IncompleteRead` 不属于这几个类，因此异常会穿出 `gather` 并结束 `_health_probe_loop`；探活任务由 `:43-47` 创建，没有运行期重启路径。

实测证据：`PYTHONPATH=. python /tmp/cw-261020-probe/runtime_probe.py` 输出：

```text
probe: propagated=IncompleteRead caught_by_fallback=False
```

探针把真实 health reader 替换为抛出 `IncompleteRead` 的无网络桩，直接调用生产 `_probe_backend`。

真实部署可触发性：健康端点在返回体期间断开/截断就能产生该异常；一次异常后周期探活停止，proxy 不再用健康响应更新后端状态。

修复方向：把 HTTP 响应读取可能抛出的协议异常纳入探活结果处理，避免异常退出整个周期协程。

## 8. SDK HTTPX 默认 5 秒超时会把慢 commit 映射成 timeout

结论：CONFIRMED

代码证据：`sdk/capswriter_asr/http_client.py:608-612` 创建 `httpx.AsyncClient` 时没有指定 timeout；`:296-320` 将 `httpx.TimeoutException` 映射成 `AsrError("timeout")`。服务端在 `core/server/http_server.py:546-594` 等待同步 commit 后才返回 202；commit 在 `core/server/http_store.py:703-724` 校验整文件并创建 Job。SDK 已先持久化本地恢复信息（`http_client.py:597-606`），恢复入口会重新查询服务端上传状态并可识别已提交 Job（`:632-650`）。

实测证据：`PYTHONPATH=. python /tmp/cw-261020-probe/runtime_probe.py` 输出：

```text
httpx_timeout: connect=5.0 read=5.0 write=5.0 pool=5.0
```

同一条 HTTPX 请求在无响应超过默认 read timeout 后会被 `_request` 转成上述 `AsrError("timeout")`；服务端的哈希计算发生在提交响应之前。

真实部署可触发性：文件 commit 校验超过 5 秒即可触发，1 GiB 文件在读取吞吐低于约 205 MiB/s 时满足；≤10 人慢盘部署可能遇到。恢复文件可用于显式续接，因此是提交结果不确定/误报超时，不等于 Job 或源文件丢失。

修复方向：让 SDK commit 等待期限与受理前整文件校验的允许耗时一致，并保留当前恢复能力。

## 9. WS 终态迟到帧检查在正常状态转移后不可达

结论：CONFIRMED

代码证据：`core/server/connection/ws_recv.py:486-527` 每轮从 `connection_tasks` 取活动任务；`:552-592` 在 `active is None` 时重新准入并 `begin_task`；之后 `:611-613` 才检查终态。`core/server/state.py:366-389` 的 `transition_terminal` 对 WS 任务先弹出 `connection_tasks`。同一个迟到 task_id 因此会走新的 `begin_task`，它覆写 `state.tasks[key]` 为新生命周期（`:322-345`），终态检查看到 `RECEIVING`。

实测证据：`PYTHONPATH=. python /tmp/cw-261020-probe/runtime_probe.py` 输出：

```text
late_frame: mapped_after_terminal=False status_after_begin=RECEIVING terminal_branch=False
```

探针调用生产 `begin_task`、`transition_terminal`，再模拟同一 task key 被重新受理；终态映射已删除，重建记录状态非终态。

真实部署可触发性：客户端在同一 WebSocket 连接中于任务完成/失败后再发同 task_id 的迟到音频帧，就会重新进入准入流程；结果可能是重复推理或覆盖旧内存生命周期。

修复方向：在重新登记之前保留并检查该连接上已终结 task_id 的身份，避免迟到帧被当成新任务。

## 10. Linux 上 GPU boost 的管理员检测恒为 False

结论：CONFIRMED

代码证据：`core/server/worker/gpu_boost.py:26-40` 在命令任务上先调用 `_check_admin`，False 即记录“非管理员权限”并返回；`:67-73` 只用 `ctypes.windll.shell32.IsUserAnAdmin()`，并把异常吞成 False。`config_server.py:84-88` 的功能开关默认关闭，但 `docs/guides/显卡加速的若干问题.md:33-35` 允许在当前平台支持命令与权限时启用。

实测证据：`PYTHONPATH=. python /tmp/cw-261020-probe/runtime_probe.py` 输出：

```text
gpu_admin_linux: windll=False result=False
```

探针在当前 Linux Python 进程调用真实静态方法；当前身份是否为 root 不影响 `windll` 属性不存在。

真实部署可触发性：Linux/NVIDIA 用户启用该可选功能且配置可运行的 boost 命令时必触发检测失败；默认关闭，未启用时不影响常规识别。

修复方向：按平台检测执行命令所需权限，使 Linux 上管理员身份不会被误报为无权限。
