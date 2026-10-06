<!-- delegate-outcome: succeeded -->
failure-visibility: skipped

# M6 五轮矩阵独立审查 verdict

## 结论

**审查未通过，M6 完成条件未满足。** H0 确实在本地裸环境与 Hosted CI 中执行了五轮并产出可消费工件；但重启后的旧 WebSocket 回归另起了 worker/queue，未测那次重启返回的服务。重启后结果只检查 `is_final` 和 `task_id`，未比较完整结果。另有逐轮字节 oracle 与工件证据错误，见 P2。

**应用 P1：未发现。** 以下意见都是测试契约/证据 P2，不把缺测判成应用故障。`failure-visibility: skipped` 表示重启后同一服务边界缺关键验证，不能据绿 CI 宣称矩阵合格；OCR 未返回 envelope，也记为 skipped。

## P2 findings

1. **重启后的 WS 相位换了服务与识别队列**（S1/S2）。`_phase_restart` 在 `tests/test_http_qa_repeat_matrix.py:801` 停止并清理 `second`；主入口随后在 `:891-892` 新建 `running_runner_server` 再跑 WS。该 helper 会新建 `ServerState`、multiprocessing queues、`run_recording_worker` 与 `ProcessManager`（`tests/test_http_file_runner.py:211-237`）。即使复用 DataDir，也没有证明被测重启服务/识别进程的旧 WS 结果路径。建议在刚重启的同一 state/worker 上接入真实 WS listener 并完成回归。

2. **DONE 回放没有比较完整结果**（S2）。`tests/test_http_qa_repeat_matrix.py:710-714` 仅查重启前结果的 `is_final`/`task_id`；`:753-755` 对重启后结果也只查状态码、`is_final`。完整文本、tokens、timestamps 等可在重启后变化而测试仍绿。建议比较重启前后的完整 JSON payload。

3. **每轮 producer 字节链只核长度**（S3）。`_phase_concurrency` 确实调用真实 SDK `submit_file_http`，worker 也收到跨 multiprocessing Queue 的真实 `Task`；但 `:528-533` 只断言源文件与落盘文件长度相同，未逐字节或 SHA 比较。录音 ffmpeg shim 记录了真实 argv/env，但主入口 `:893-897` 只要求全局日志非空，未把调用归到当前轮；worker 的 `data_sha256` 也未与独立 PCM 参照比较。既有 once QA 不自动证明本重复域每轮。建议为每轮补源文件落盘 byte/SHA oracle，并核实本轮 ffmpeg/Task producer 证据。

4. **`io-first` 工件布尔值与 mailbox 事实相反**（S2/S4）。`_phase_cancel` 在 `:594-599` 等真实 I/O 完成后暂停 route；`:616-619` 明确要求此时 `pending==0` 且 mailbox `_value == IO_MAILBOX`（名额已归还）。但 `:673-676` 对两种顺序都写 `slot_held_before_release: true`，消费者 `:161-171` 又把该值当必须证据，因此会接受与实际状态相反的声明。建议记录实测 slot 数，并按 cancel-first/io-first 分别校验。

5. **ffmpeg 计数是跨轮累计值**（S2/S4）。`ffmpeg_log` 在入口开始时创建一次；每轮 `:893-900` 重新读取整份追加日志并把总数写到当前 round。实际 trace 计数为 `[2,4,6,9,11]`，不是每轮调用数，前轮事件会给后轮背书。建议记录每轮日志起止差值或以本轮唯一任务关联事件。

## S1-S6 核对

- **S1 同服务：未达。** DataDir 在每轮复用，且 `HttpServer`/store 实际读取传入路径；但 post-restart WS 使用新 worker/queue。
- **S2 完整相位：未达。** 五轮循环真实执行；完整 DONE 回放和重启后同一 worker 的 WS 未被证明，`io-first` 工件字段不实。
- **S3 producer 字节边界：部分。** 真实 SDK、HTTP listener、ffmpeg、Task/Queue 和 store 路径到达；重复矩阵只有长度相等，没有每轮字节 oracle，ffmpeg 计数未按轮隔离。
- **S4 工件消费者：部分通过。** 测试进程和 CI 同款 `importlib` 消费器读同一文件字节；H0 实际工件通过。Scratch H0 中省略真实 `io-first` 相位、以及把真实第 1 轮证据复制并改轮次标签，都由生产入口末尾的消费者以 AssertionError 拒绝。消费者仍接受上述错误 slot 声明。
- **S5 CI/裸环境：通过测试契约消费。** `env -i` 裸环境具名入口 6 passed、0 skip；PR #83/H0 的 py3.12 `pytest tests/`、矩阵工件校验与上传步骤均成功。工件 `source_sha` 是 checkout merge ref `750ecfb4f3e8853707cc7357901a40a7820ac3e5`，与 PR head `da81cacc13061be8a7693775ebca7e413a29a189` 区分明确。PR 仍为 Draft，`gate / primary` 为 SKIPPED，不能称完整主审 gate 通过。
- **S6 简单性：部分。** 未改 App/SDK、配置或依赖；独立 CI 消费者有第二消费者理由。`required_phases()` 只是单消费者转发 `REQUIRED_PHASES`，可直接收敛；未因该 P2 扩机制。

## 验证与边界

- H0 固定审查范围：`6aa76f6c6935e9cef00afc1bcbcf8327e7c95488..da81cacc13061be8a7693775ebca7e413a29a189`；全量 diff 含 CI、设计/进度文档与新测试。
- 裸环境 focused run：Python 3.12.3、pytest 9.1.1、pytest-asyncio 1.4.0、aiohttp 3.14.3、httpx 0.28.1、websockets 15.0.1；`env -i` 白名单仅含 HOME/PATH/TMPDIR/PYTHONPATH/工件目录，6 passed、40 warnings、22.23s，具名入口无 skip。真实 ffmpeg shim、HTTP/WS producer、受管服务进程均执行。
- 反向验证均在 `scratch-worktree.sh` 的 H0 worktree 中进行并清理：省略真实 `io-first` → `round 1 缺少 io_first 证据`；复制真实第 1 轮并改标签 → `round 2 ... 禁止借旧事件贴标签`。两次都在实际矩阵消费者处失败，不是缺文件或导入错误。
- 只读 Hosted CI：PR #83 H0 run `37302715605`，py3.12 pytest/工件校验/上传步骤 success；下载的 `trace.json` 5 轮完整，实际消费通过。Draft 的主审 gate skipped，未触发新 CI。
- `git diff --check HEAD^ HEAD` 与固定完整范围 `git diff --check 6aa76f6..da81cacc` 均通过。基线作业不可用，继承红未能判定。
- OCR：调用 `ocr-review --from origin/master --to HEAD` 后约八分钟仍无 stdout envelope（stdout 0 字节），手动中断退出 130；记录为 **skipped / no envelope**，没有把空 findings 当 clean，也未展开可能含内部响应的 stderr。OCR 未实际完成审查。
- 接手巡检：无交接单；本仓未关闭 issue #81、#76 已观察但未扩展处理。archive 摘要：`orphan 0 owned 0 unattributable 0 too-new 0 recent-7d 0 stale-over-7d 0 missing_ledger_repos 0`；memory probe 不可用，返回 `memory_dir_mismatch`，未将其记作欠账为零。巡检项未展开，需要时跑 `/worksite-audit`。

完整取证报告写入本派发的 `$DELEGATE_REPORT_PATH`；本仓仅新增本 verdict。
