# M6 原完成条件证据盘点

- **源码基线**：`902400887445603a58f7dc960a24e809ca779a0a`；本表按该树核查。
- **Goal 状态**：`goals/http-integration/M6-qa.md` 仍为「进行中」。本盘点不改 Goal、不缩减五轮或双环境要求。
- **判定口径**：表中「达」只表示该组的跨边界断言存在，且 902 主干 hosted 全套测试 job 成功一次；不代表 M6 整体完成。

## 十二组证据

| 组 | 代码、测试与真实 producer 边界 | 已知阴性/反向控制 | 裸环境证据 | Hosted 证据 | 状态与最小补项 |
|---|---|---|---|---|---|
| 1 上传字节 | `tests/test_http_qa_e2e.py::test_real_sdk_upload_bytes_match_server_disk_sha` 比对 SDK 真 PATCH body、原文件及服务端落盘字节/SHA；`tests/test_http_client.py::test_cli_submit_subprocess_emits_real_http_requests_and_no_token` 用 CLI 子进程向 TCP capture 发请求并核 body。 | 等长全零不是本组；组 1 的反向变异红验在既有证据中明确未跑。 | 旧 `6` 条 e2e 一轮含 SDK 测试；旧全套 `457×2`，均非 902 树。 | H1。 | 达；纳入双环境五轮入口，逐轮记 PATCH 字节数和落盘长度/SHA。 |
| 2 断连后取结果 | `tests/test_http_file_runner.py::test_real_container_upload_then_other_connection_takes_done_result`：提交连接关闭后，另一连接取得 worker Result；真实 Queue/Result 记录见 `tests/harness/worker.py::run_recording_worker`。 | 未找到该组专属变异红验记录。 | B0。 | H1。 | 达；五轮记录独立领取的真实 Result 数与状态。 |
| 3 幂等/显式恢复 | `tests/test_http_qa_e2e.py::test_lost_commit_response_recovers_with_exactly_one_recognition` 断掉真实 202，锁请求序列、SQLite 行数、ffmpeg 次数及子进程实际 Task 数。 | 自动重发 commit 的反向实现由红验 D 触发 `AssertionError`。 | 旧 `6` 条 e2e 一轮；非 902 树。 | H1。 | 达；五轮记录 commit/GET/Job/Task 的 producer 计数。 |
| 4 可信续传 | `tests/test_http_file_tasks.py::test_resume_after_failed_patch_only_sends_unconfirmed_suffix` 检查真实请求后缀；`tests/test_http_supervision.py::test_http_offset_crash_windows_recover_in_new_processes` 对照磁盘字节与确认 offset。 | 以未确认尾字节/SHA 和重发 body 为直接反例；未找到专属变异红验。 | B0。 | H1。 | 达；五轮保留实际 PATCH body 长度和恢复 offset。 |
| 5 部分上传重启 | `tests/test_http_supervision.py::test_http_offset_crash_windows_recover_in_new_processes` 在同一 data dir 中经历进程终止、重启和修复；`test_http_file_runner.py::test_sigterm_exits_zero_and_restart_marks_server_restarted` 锁终态。 | 重启后磁盘前缀、offset 与 worker 未重跑断言；未找到专属变异红验。 | B0。 | H1。 | 达（单次重启链）；矩阵五轮须每轮沿用其 data dir 跨重启。 |
| 6 结果重启 | `tests/test_http_supervision.py::test_result_producer_payload_and_done_survive_new_process` 由真实 HTTP 子进程写 producer JSON，重启后新进程 GET 并逐字段比对结果。 | 重启前 producer 文件与重启后 GET 直接比较；未找到专属变异红验。 | B0。 | H1。 | 达；五轮记录 producer/consumer 结果条数及相等判定。 |
| 7 WS/HTTP 双 owner | `tests/test_http_qa_e2e.py::test_real_ws_and_http_share_one_worker_without_key_pollution` 发送实际 WS frame；同一 worker 子进程 Queue 收到 WS 与 HTTP Task，并分别断言 `socket_id`、owner、断连清理。 | 删除 WS 断连清理的反向实现由红验 A 触发目标断言失败。 | 旧 `6` 条 e2e 一轮；非 902 树。 | H1。 | 达；五轮按 Queue 实收 Task 的 owner/socket/task 计数。 |
| 8 取消/I/O 竞态 | `tests/test_http_file_tasks.py::test_handler_cancellation_and_io_completion_orders_preserve_confirmed_bytes` 在一个 `running_server` 实例、同一临时目录中，对 cancel-first 与 io-first 各循环 5 次，核 SQLite offset、磁盘字节及 mailbox。 | 两个 winner 的直接相反顺序均覆盖；它只重复此竞态，不含重启或十二组全矩阵。 | B0；该源码循环数是每种顺序 5 次，不是整套矩阵五次。 | H1；CI 每次运行该测试时执行上述内部循环。 | 达（窄竞态）；仍需编排完整矩阵五轮并同时运行重启、旧 WS。 |
| 9 资源/错误边界 | `tests/test_http_file_tasks.py::test_negative_matrix_keeps_old_bytes`、`test_upload_identity_and_limit_validation`、容量与 release-invariant 测试核错误码、旧字节和 DB 副作用。 | 多个已知无效输入有否定断言；没有一条覆盖所有组的统一变异红验。 | B0。 | H1。 | 达；完整矩阵每轮保留错误类别和副作用计数。 |
| 10 ffmpeg/PCM | `tests/test_http_file_runner.py::install_recording_ffmpeg` 记录真实 subprocess argv/env 后 exec 真 ffmpeg；`tests/test_http_qa_e2e.py::test_resampled_sources_produce_bounded_16k_mono_f32_segments` 将独立 ffmpeg 参照与 worker Queue 实收 `Task.data` SHA 对照。 | 去掉 `-ar 16000` 的红验 B、替换为等长零 PCM 的红验 E 均触发断言失败。 | 旧 `6` 条 e2e 一轮含该参数矩阵；非 902 树。 | H1；#79 后缺 ffmpeg 为显式失败，非静默 skip。 | 达；五轮记录 argv/env 形状、两类输入的实收段数与内容对照。 |
| 11 末段失败/状态机 | `tests/test_http_qa_e2e.py::test_final_segment_failure_fails_job_without_publishing_partial` 先跑成功对照，再让真实 `is_final` 调用失败，断言 FAILED、零 results 行及 409。 | 先发布正文再失败的反向实现由红验 C 触发 `DONE != FAILED`。 | 旧 `6` 条 e2e 一轮；非 902 树。 | H1。 | 达；五轮记录各段 Result、终态、results 行数。 |
| 12 清理/default WS 回归 | `tests/test_http_cleanup.py::test_periodic_cleanup_waits_for_real_runner_reference_then_keeps_result`、`test_http_disabled_keeps_default_websocket_lifecycle`；旧 WS 回归见 `test_server_e2e_baseline.py`、`test_backpressure.py`、`test_protocol_v2.py`、`test_health.py`、`test_error_codes_contract.py`、`test_segmentation_contract.py`。 | fatal probe 消费有已知错误输入；这不等于旧 WS 全套有反向变异红验。 | `19 passed/0 skipped` 是 `6ffaed` 的 env-i cleanup 记录；902 后 cleanup 与 protocol-v2 测试文件有改动，不能标成 902 裸环境实测。 | H1。 | 达（hosted 单轮）；当前树需重跑 cleanup 与旧 WS 回归，并纳入五轮矩阵。 |

## 环境、次数与完成判定

- **H1，当前 hosted**：GitHub Actions run `37289712410`，attempt 1，`head_sha=9024008…`，2026-10-05 09:23:29Z 创建，run 与 3 个 job 均 `SUCCESS`。`.github/workflows/ci.yml` 的 Python 3.12 job 跑 `tests/` 一次；两个 Python 3.11 job 只跑 `tests/test_sdk_*.py`，不能合计为三次 M6。受限于本次只读取 run/job/step 结构，当前 hosted pytest 总数及 skip 节点未从日志取得；不把候选树 `499 passed/3 skipped` 冒记为当前 CI 计数。PR #79 的 primary 与三条 CI 检查均为 `SUCCESS`；primary 不作为行为测试证据。
- **B0，历史裸环境**：旧 QA 候选记录 `tests/` 在 `env -i` 下 `457 passed/3 skipped`，两种 websockets 各一轮；旧主干 `4de4a7f` 的六条 e2e 在 `env -i` 下 `6 passed/0 skipped` 一轮。fatal-probe 进度另记 `6ffaed` 的 cleanup `19 passed/0 skipped` 与两次本地全套 `499 passed/3 skipped`；其中只有 cleanup 明确标为 `env -i`。这些不是 902 的完整裸环境矩阵。
- `git diff --name-status 6ffaed573c3f78d3dbc522e13d984a7e3c080392 902400887445603a58f7dc960a24e809ca779a0a -- tests` 显示 `tests/test_http_cleanup.py`、`tests/test_protocol_v2.py` 等测试源在 6ffa 后有改动。因此 `19/0`、`499/3` 的计数必须留在原 SHA 与环境名下；902 当前树裸环境完整套件的计数为 **unknown**。
- `progress/m6-qa-progress.md` 记录三个并发准入用例五轮均 `3 passed`，这是三个窄用例的跨运行重跑；每次测试 fixture 会新建隔离服务/data dir，不能与取消、重启、旧 WS 用例拼成「同一服务完整矩阵五轮」。取消/I/O 测试自身的两个顺序各有 5 次循环，但重启测试只验证单条同目录恢复链。`test_http_qa_e2e.py` 六案 ×5 的历史窄跑也不是十二组同服务矩阵。
- **总体**：十二组已有可追溯测试，902 hosted 的 `tests/` job 单轮成功；原完成条件仍**未达**：没有同一隔离服务的并发/取消/重启完整矩阵五轮，也没有同一 902 源码在 hosted runner 与无会话 bare shell 各执行该矩阵五轮的证据。当前 skip 只可报已知历史事实：旧 499+3 的三项为 ForceAligner×2、silero-VAD/onnxruntime×1；902 hosted 的 skip 数和真实原因未由安全结构查询证实。

## 下一步最小运行边界

主脑后续卡应给现有 QA 测试增加一个具名的 M6 编排入口：每轮隔离一个服务，跑十二组 producer/consumer、并发、取消、同 data dir 跨进程重启及旧 WS 回归；重启场景在该轮内复用同一 data dir。入口固定 5 轮，并从真实 producer 侧汇总 SDK/CLI body、文件写盘字节、subprocess argv/env、Queue Task/Result、重启前后结果及错误终态的实际计数，核对每轮期望节点和 payload 数均非零且相符。将同一源码 SHA、同一入口分别放到 hosted CI 与 `env -i` 裸 shell 执行；按结构化计数单列真实 skip，禁止把不同测试的各自 `range(5)` 或三种 runtime 版本拼成五轮。本卡未改代码、workflow、测试或 Goal。
