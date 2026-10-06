<!-- delegate-outcome: succeeded -->
# M6 H1 完整独立审查

固定审查对象：`6aa76f6c6935e9cef00afc1bcbcf8327e7c95488..337689689c9b2a314548b70667e447841bf070ad`；risk-tier：internal。仅新增本 verdict；未改 Goal、应用、SDK、CI 或源测试。

failure-visibility: p2-only

## 结论

执行器已完成本轮完整审查。五轮矩阵真实路径、受控重启后的旧 WebSocket、Hosted 结构校验和裸环境运行均有正证据；另有一个已实测的工件消费者反例，故本轮为 P2-only、无应用 P1。新设计/进度文件还保留两句与本次 harness 改动冲突的旧陈述，应在常规文档交付中逐条订正，不新增 App 机制。

M6 五轮矩阵子目标有 Hosted 与无会话运行证据。`goals/http-integration/M6-qa.md` 整体仍标为“进行中”；本审查没有重审原 12 组 QA 全部不变式，也不改 Goal 状态，故不据此宣布整个 Goal 完成。应用 P1 与 QA 工件假阳性分开判定。

## 六项不变式

### 1. 同一隔离服务与五轮归属

实现位于 `tests/test_http_qa_repeat_matrix.py::test_five_round_same_service_concurrency_cancel_restart_ws`；五次迭代复用一个 `tmp_path/httpdata`。并发/取消使用 `running_runner_server`，真实 `HttpServer`、`HttpFileRunner`、multiprocessing `queue_in/out` 和 `run_recording_worker` 共用 `ServerState`；WS 帧经真实 `ws_recv`。每轮重启先后使用 `ManagedHttpServerHarness.start(data_dir=data_dir)`，第二实例仍存活时由真实 WS 客户端发帧并收到 final。测试锁在 `harness.data_dir.resolve()`、HTTP/WS Task owner、同一队列、第二实例存活、不同旧/新 PID 和每轮状态断言。

`FAKE_ENGINE` 仅在受控重启的旧实例为第二个文件任务设 60 秒延迟，使其保持 RUNNING；新实例恢复普通假引擎以完成重启后 WS。这是测试引擎行为差异；代码、HTTP 配置、source 和 SQLite 持久根保持一致。并发相位直接 `websockets.serve(ws_recv)`，但与 HTTP 共享真实 state/queues/worker；重启后的 WS 则来自 Managed 子进程内 opt-in listener。原规格要求真实 WS producer、同 worker/结果队列与兼容回归，没有要求必须经 `CapsWriterServer`/`SocketManager` 装配；不把缺少这两个包装层判成缺陷。

### 2. Task.data 与持久结果都由真实消费者读取

PCM producer 是 `HttpFileRunner._submit` 的 `queue_in.put(Task(data=segment.data))`。`tests/harness/worker.py::recording_get` 在 multiprocessing Queue 解包后从收到的 Task 取完整 SHA；矩阵再与独立 ffmpeg 16 kHz mono f32 oracle 按段、offset、overlap 比较。后续证据文档记录的 H1 负向探针在 Queue 入队前 XOR 1 bit、长度不变，4 次命中，测试在 oracle SHA 比较处以 `AssertionError` 失败；该探针覆盖实际反序列化 worker 对象，不是 source 标签或长度摘要。

结果 producer 是 `HttpStore.record_result`：序列化完整 Result 到 `results.payload`，并与 DONE 同事务提交。实际消费者为 `HttpServer._get_result → HttpStore.get_result → JSON GET`。矩阵先经网络 GET 保存完整对象，停止首实例，再启动第二实例，并以 `replay_again.json() == replay` 锁全对象；不排除 `duration` 等非 final 字段。指定后续证据中的外置脚本 AssertionError 单独不能证明 H1 原断言转红。本审查另在 H1 scratch worktree 将真实 SQLite `results.payload.duration` 改 1、保留 `is_final`/`task_id`，由第二次网络 GET 读出；marker 显示持久字节已变、第二 GET 已到达，原 `_phase_restart` 完整 JSON 等式实际 `AssertionError`。该链路锁到了目标消费层。

### 3. 终态、停止和部分文件恢复

每轮实际 stop/close 发生在 trace 轮次写入前：in-process HTTP/worker teardown；受控旧实例 SIGTERM；第二实例旧 WS 完成后 SIGTERM/cleanup。它们只作用于 pytest 自有 `tmp_path` 与测试进程。恢复路径逐字节核对已确认前缀，拒绝旧 offset，显式 PATCH suffix 并比对完整文件；若任一阶段失败，当前轮不会写成 pass。CI 的 `always()` 工件结构校验要求恰好五轮，所以缺轮或无文件使 job 失败；测试错误时可上传不完整工件，但不会变绿。

新五轮矩阵每轮保留 ACK prefix，不在每轮重做未 ACK tail 故障窗；既有 `tests/test_http_supervision.py::test_http_offset_crash_windows_recover_in_new_processes` 覆盖 offset 提交前后的 SIGKILL、磁盘字节、可信 offset 与显式恢复，`test_result_producer_payload_and_done_survive_new_process` 覆盖重启前后完整 producer payload。此处沿用已有 QA，不扩成 12 组各五遍。

### 4. mailbox、PID、Task 与 queue 身份

`_phase_cancel` 真正取消 aiohttp handler；cancel-first 用线程 Event 卡在 `append_bytes`，io-first 卡在已完成的 I/O worker 路径。`_pending` 经 `_wait_for_worker_pending` 读取并断言，mailbox 读自真实 `_worker._mailbox._value`，`slot_held` 从现场值导出；工件不是照抄预期常量。

round-specific key、WS task ID、实际 HTTP job ID、每次 harness 自己的 Queue/worker/Manager state 和旧/新 `Process` 对象共同归属事件。trace 记录 PID，不记录 ctime；这里没有后续按 PID 查进程的消费路径，PID 是从两个实际 Process handle 读取且每轮另有 round/task 标识，缺 ctime 不会把事件归到别轮。known-empty 来自新子进程的真实 `received` 列表，另断言 `engine_calls_after_restart == 0`。DONE 结果来自新 HTTP 连接，旧 WS 来自仍存活的重启后实例。

### 5. Hosted 与裸环境工件

无会话 `env -i` 中用 Python 3.12、`websockets==15.0.1`、`pytest==9.1.1`、`pytest-asyncio==1.4.0`、`aiohttp==3.14.3`、`httpx==0.28.1`、numpy 2.5.3、rich 15.0.0、colorama 0.4.6、soundfile 0.14.0，显式设置 HOME/PATH/TMPDIR/PYTHONPATH/工件目录，执行新矩阵及旧 SIGTERM harness 测试：12 passed、0 skipped、58.33 秒。生成的 trace 经测试内真实文件 consumer 消费。

固定 Hosted run `37311065357/1` 的 py312 job `111766323793` 结论 SUCCESS；同 run 的 artifact `11346765500` / `m6-repeat-matrix-py312` 未过期，job 的 pytest、矩阵工件结构校验、上传步骤均 SUCCESS。下载的实际 trace 是 schema 1、Python 3.12、round 1..5、四相齐全、五轮结果完整比较与重启后 WS 均为 true，`source_sha=f99b7517c01d9fc7b7b7218ade1a1eda65900ce2`。GitHub merge commit f99 的 parents 是 base 6aa 与 H1 337，tree `6b129a73a5520bd36021cb2f818d5e7e0a66fe0a` 与 H1 tree 相同；H1 `git ls-tree -r -z` 有 475 个非空 NUL 分隔叶项。已知旧树 `da81cac` 与 H1 tree 不同；独立 bad-ref 保持未解析，未用 live branch 替代 run checkout。

### 6. 范围与新增熵

本 diff 五文件新增 1,331 行；主要是 1,104 行矩阵测试与两份文档。`tests/harness/server.py` 仅新增 opt-in `enable_ws`、由 Manager dict 发布实际 WS 端口，同时保留旧 info_queue 二元 tuple ABI。发布字典在 child 与 parent 间有实际 producer/consumer，不是生产 App 状态；没有新增 App/SDK 状态、重试、fallback、通用框架或依赖。

两份文档中的旧表述尚未随 H1 更正：设计第 31 行“不改 harness”，进度第 13 行“未改 harness”，与本 diff 修改 `tests/harness/server.py` 及后文 `enable_ws` 说明冲突。按卡面要求，这是正常文档条目订正，不推导出 App 机制需求。

## Findings 与严重度

1. **P2：工件 consumer 会接受整轮复制并全面重标的伪五轮数据。** `consume_repeat_matrix_trace` 只要求 `round_job_id` 含 `rN` 且字符串唯一；`test_trace_consumer_rejects_relabeled_round_without_unique_job` 只改 `row.round`，让旧 `r1` ID 留着，因此没有覆盖“复制首轮，再改 round、phase IDs 和 offset 标签”。以实际 Hosted trace 复制首轮五份并重标这些字段，H1 consumer 返回成功。它可将一份实际事件序列当作五轮工件，违背设计的自贴标签/复制事件拒绝契约；当前正常 producer 仍真实跑五轮，所以这是 QA verifier 的缺口，不是应用运行路径 P1。后续应补这一个反例并把轮次标签与现有实际 Task/WS/job 身份关联。
2. **P2：新增设计/进度文档有过时 harness 事实。** 设计第 31 行与进度第 13 行仍称未修改 harness，而本 diff 实际新增了 Managed HTTP 子进程的 WS 发布/opt-in 监听。会让读者误读对象边界；不改变应用行为，按正常文档整理更正，不阻塞本轮代码判定。

P1 两问：当前应用实际使用是否会触发？否，本次改动是 QA/harness/doc，应用产品路径未变；伪五轮只由被接受的克隆 trace 触发。若发生会否不可接受？它会污染 M6 QA 证据，但不直接影响用户数据或服务行为，按本仓标准为 P2。没有 OCR severity 可供落地。

## 验证、OCR 与未知

- 一次限定 OCR：wrapper 300 秒超时，退出 124，stdout 为空、无 envelope；记 `skipped`，reason 为硬超时，coverage/verifier 未提供。不据此写 scan clean，未重试、未读取 stderr。
- H1 标准裸环境 focused run：12 passed、0 skipped；包含旧 harness SIGTERM 用例。未跑全量本地 suite。
- SQLite 持久 duration 反向探针：1 hit；持久字节变化；第二 GET 到达；原矩阵完整 JSON 断言以 AssertionError 失败。
- 工件克隆反例：首轮全相位数据复制五份、重标 round/phase IDs/offset 后，当前 consumer 接受；这是 P2 证据。
- Hosted 基线 API 作业状态不可用（卡面记录 `gh api request failed`）；本审查未判继承红。未跑 Windows、systemd 或生产服务/私有媒体，不将其推成合规或通过。
- 接手简报无工作区交接单。收件箱开放 issue #81（本仓文档/产物缺口）与 #76（WS 长文件任务）；巡检原行：`summary: orphan 0 owned 0 unattributable 0 too-new 0 recent-7d 0 stale-over-7d 0 missing_ledger_repos 0`。记忆探针返回 `memory_dir_mismatch`（仅私有 dispatch 报告保留原始本机路径）。
