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
