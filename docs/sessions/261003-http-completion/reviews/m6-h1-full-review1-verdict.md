# H1 完整矩阵独立审查 verdict

- 审查对象：`6aa76f6c6935e9cef00afc1bcbcf8327e7c95488..337689689c9b2a314548b70667e447841bf070ad`
- 风险等级：internal
- 原规范：`goals/http-integration/M6-qa.md`、`docs/sessions/261001-http-files/qa.md`、`docs/sessions/261001-http-files/design.md`、`docs/reference/protocol.md`
- 本轮新外证：当前 H1 裸 `env -i` 五轮工件；Hosted run `37311065357` job `111766323793` artifact `11346765500`
- OCR：`skipped`（包装器挂超过 5 分钟无完整 JSON envelope，已停自有扫描；不得表述为扫过且干净）
- 审查结论：矩阵行为与原 Spec / 用户条件对齐；有一条文档 P2（过时「不改 harness」句未做条目级纠正）
failure-visibility: p2-only

## OCR

- wrapper：`ocr-review`
- from/to：审查对象两端 SHA
- background：`/tmp/ocr-bg-m6-h1-full-review1.md`（远小于 8000B）
- status：`skipped`
- reason：自有扫描运行约 6 分钟，stdout 0 字节，stderr 仅 `leg=primary event=start`，无完整 JSON envelope；按纪律停止，未反复刷新
- coverage：无
- verifier：本会话；`findings` 不得当干净

## 范围核对

Diff 5 文件：`tests/test_http_qa_repeat_matrix.py`（新）、`tests/harness/server.py`、`.github/workflows/ci.yml`、`docs/sessions/261003-http-completion/m6-repeat-matrix-design.md`、`progress/m6-repeat-matrix-progress.md`。未改 App/SDK/旧测试函数体（旧测试仍按默认 `enable_ws=False` 调 `ManagedHttpServerHarness.start`）。不是 H0..H1 四问复读，未重开 C2/M6/M7 全楼面。

## A 同服务身份

原 Spec：`M6-qa.md`「同一隔离服务执行并发/取消/重启矩阵至少 5 次且旧 WS 回归」；`qa.md` 组 5/7/12 允许隔离假引擎 + 真 ffmpeg + 既有 harness 家族。Scope 明确允许最小 harness 配 managed 旧 WS。

机械列（每轮，producer → consumer）：

| 循环 | start | stop | 配置 | queue/worker | 数据根 | state | listener |
|---|---|---|---|---|---|---|---|
| 并发/取消 | `running_runner_server(tmp_path)` 同进程 `HttpServer` | 退出 `async with` | `FAKE_ENGINE` | 新 `multiprocessing.Queue` + `run_recording_worker` | `tmp_path/httpdata` | 新 `ServerState` | HTTP 在 pytest 进程；WS 为同进程额外 `websockets.serve(ws_recv)` |
| 重启 first | `ManagedHttpServerHarness.start(data_dir=同一根)` 子进程 | `SIGTERM`，`exitcode==0` | stalled fake engine | 新 child `queue_in/out` + 识别子进程 | 同一 `httpdata` | child `ServerState` | 仅 HTTP；`info_queue` 仍 `(http_port, worker_pid)` |
| 重启 second + 旧 WS | 再 `start(..., enable_ws=True)` | WS 相位结束后 `stop` | `FAKE_ENGINE` + `CW_TEST_ENABLE_HTTP_WS=1` | 全新 queue/worker | 同一 `httpdata` | 新 child state | 同 child 内真 `ws_recv`；端口走 `published['ws_port']` |

变化：parent 始终是测试进程；每段 launcher 换 PID/queue/worker；持久身份是同一 `data_dir` + sqlite store，不是单一长活进程。second 相对 first 多了测试专用 WS opt-in。这是可接受的逻辑持久服务重启（组 5 本就用 managed SIGTERM；组 7 本就用 in-process HTTP+WS），不是无 Spec 依据的组件拼接。

生产 `CapsWriterServer.start()` / `SocketManager` **未调用**。缺：生产默认 WS 端口、SocketManager 生命周期、`config_server` 正式启用链。在场：`HttpServer` / `HttpFileRunner` / `HttpStore` / `ws_recv` / `ws_send` / `ProcessManager` / 识别子进程。取消「handler.cancel 需同进程」是 in-process 相位的既有理由，Scope 已允许，不因此自动失败。

不能只靠工件字段 `data_dir_role=persistent-httpdata`：裸跑与 Hosted 都断言 `harness.data_dir.resolve() == tmp_path/httpdata`，重启 `start(data_dir=)` 传入同一对象。

## B 每轮完整

原 Spec：五轮完整并发/取消/重启 + 旧 WS；空 socket 不拦 HTTP；断连 WS 不继续投段；取消-first / io-first 真 write/queue/ACK；sameRoot 停进程 → 新 PID → prefix / 未 ACK tail / 显式 suffix / 不自动重处理；DONE 整份 JSON 前后一致；second 仍存活时连其 listener。

证据（Hosted artifact `11346765500` 与本会话裸 `env -i` 各 5 轮，结构同形）：

- rounds 恰好 `[1,2,3,4,5]`；每轮四相位；20 个 `round_job_id` 互异且含 `r{n}`
- 并发：`http`/`ws` owner、空 socket HTTP DONE、断连、PCM oracle、源字节相等
- 取消：cancel-first `pending=1 mailbox=31 slot_held=true`；io-first `pending=0 mailbox=32 slot_held=false`（`IO_MAILBOX=32`）
- 重启：`pid_old != pid_new`；`known_empty_received`；`engine_calls_after_restart=0`；`prefix_offset=2` `suffix_offset=4`；`result_payload_equal`（物理比较在 `_phase_restart`：`replay_again.json() == replay`，协议 `GET /v1/jobs/{id}/result` 完整结果）
- 旧 WS：`ws_on_restarted_instance=true` 且 `second.process.is_alive()`；`test_legacy_ws_fails_if_restarted_instance_has_no_ws` 锁「禁止另起 stub」
- ffmpeg：事件下标 `[0,7,14,21,28]` 递增，每轮 `start_count=4`（下标不是 byte offset）

已知为空：重启后 `list(second.received)==[]`，不是「变了」。时间墙钟未当身份。

物理边界：并发/取消的 WS 不在 managed child 上；旧 WS 不在 in-process runner 上。字段声明不能单独证明「一个进程跑完四相位」。按 Scope 这是允许的 launcher 分工。

## C producer bytes

原 Spec：`qa.md` 组 1/10；`M6-qa.md` 真实 SDK/CLI body、subprocess argv/env、文件字节、Queue pickle。

- HTTP：SDK `submit` / 裸 PATCH → `sources/*.bin` `disk == source.read_bytes()`（不只 size）
- WS：真 `AudioMessage` JSON frame，`task_id`/`is_final` 来自客户端收到的 JSON
- FFmpeg：shim 记录真实 argv 列表 + `env_marker=runner-env-marker`；独立 ffmpeg 16k mono f32 oracle 对 `Task.data` sha256（工件不落 hash）
- 每轮独立跑；不以一次旧 QA 替五轮背书

反向（scratch-worktree @ H1，注入行有 `# RED-VERIFY`）：

1. `_ws_frame` 强制 `is_final=False`（L527）→ `AssertionError: 等待「WS 客户端收到 is_final」超时`，exit 1，非 ImportError
2. recording worker `data_sha256` 改为空摘要（`tests/harness/worker.py` L66）→ `AssertionError` 真 sha ≠ 空 sha（`e3b0c442…`），exit 1

文件消费者看不到媒体字节，这是工件安全约束；真消费者是测试进程内的 oracle / JSON 相等。变异同长度 PCM 摘要会被真消费者看见。

## D 工件真实

- `ffmpeg_log_offset = len(invocations_before)`，事件条数下标
- 缺第 5 轮 / 缺相位 / 复制首轮改 round 号 / io-first 虚占位 / `result_payload_equal=False` 均有消费者红测
- schema 布尔 ≠ 相位物理执行：Hosted 与裸跑是物理执行后的序列化；纯构造的 `_complete_round` 只锁消费者拒假件，不冒充服务跑过
- `resolve_artifact_dir`：未设 env 时普通 pytest 用 `tmp_path`；CI/裸必须显式目录。本会话裸设了 `M6_REPEAT_MATRIX_ARTIFACT_DIR`，未吞成默认假绿
- `source_sha`：Hosted = `f99b7517c01d9fc7b7b7218ade1a1eda65900ce2`（PR merge checkout）；裸 = `3376896…`（本 worktree HEAD）。live ref 不能事后改 run 源

merge 对象核（GitHub API；本地 `git cat-file` 为 badref）：parents = H0 `6aa76f6…` + H1 `3376896…`；tree = H1 tree `6b129a73…`。H1 `git ls-tree -z -r` 475 条非空；H0 472 条；H1 tree ≠ H0 tree（known-false）。非法 `source_sha` 消费者 AssertionError（badref 两态）。

## E CI 两个消费场景

固定 run `37311065357` / PR 83；3.12 job `111766323793` success（pytest → 校验工件 → upload）；artifact `11346765500` `m6-repeat-matrix-py312`。未用旧 run 373027。

py3.11 两 job（`111766323586` / `111766323957`）SDK-only，校验/上传步骤 skipped。primary/OCR draft skip 不是本卡主审。

本会话：0700 私目录取原件；`consume_repeat_matrix_trace` 接受 Hosted 五轮；clone 删第 5 轮 → AssertionError；非法 sha → AssertionError。裸 `env -i`（HOME/PATH/TMPDIR/PYTHONPATH/显式 artifact，无 DELEGATE_*）`12 passed / 67.73s`（新模块 11 + 旧 `test_sigterm_exits_zero_and_restart_marks_server_restarted` 1）。python 3.12.3 / pytest 9.1.1 / aiohttp 3.14.3 / httpx 0.28.1 / websockets 17.2 / pytest-asyncio 1.4.0。临时 venv 在 `/tmp/m6-h1-review-venv-b14cfe`，仓内无 `.venv` 可污染。

未跑全量 500 / 真模型 / 私音频。`git diff --check` 审查对象干净 ≠ 本审查整体。

## F 机制与影响

新增：`enable_ws`（默认 False）、`published` Manager.dict、`CW_TEST_ENABLE_HTTP_WS`、`consume_repeat_matrix_trace`、CI 3.12 工件校验/上传。第二消费者：矩阵测试 + CI importlib 读同一 `trace.json`；旧 `info_queue` 二元组消费者未改。无新产品 debug API / pool / 依赖 / 资源状态层。模式是显式 opt-in，不是无根据 fallback。生命周期发布前：WS 端口进 `published` 后才 `info_queue.put`；父进程先解二元组再读 `ws_port`。

**P2（文档）**：`m6-repeat-matrix-design.md` L31 仍写「不改 harness」，同文件 H1 表（L72–77）已授权 `enable_ws` / `published`。`progress/m6-repeat-matrix-progress.md` L13 仍写「未改 harness」，后文 H1 节描述了 harness 最小 WS。这是已登记过时声明未做条目级纠正，不是新机制迎合旧句。不因此判应用失败。

## P1 两问

无新 P1。文档 P2 真实触发（打开 design L31 与 H1 表即矛盾），后果可接受（测试与 CI 不读那句）。

工具 severity：OCR skipped，无工具 finding 对照表。主干基线本次不可用，继承红未能判定。

## 未达 / unknown

- OCR 未扫过
- 生产 `CapsWriterServer`/`SocketManager` 组合未进本矩阵（Scope 允许；记边界）
- 文件消费者不重放 DONE JSON / PCM 字节（工件禁 hash/path；物理比较在测试进程）
- 真模型 / 录音 / 资源峰值属 M7，不在 Scope
- 未跑 Windows / systemd / 生产 URL / 全量 500

## 验证命令摘要

- 裸：`env -i HOME PATH TMPDIR PYTHONPATH M6_REPEAT_MATRIX_ARTIFACT_DIR` → pytest 新模块 + 旧 SIGTERM，12 passed
- Hosted 原件 + clone 负例 + badref 负例
- scratch-worktree @ H1 两次反向，均业务 `AssertionError`
