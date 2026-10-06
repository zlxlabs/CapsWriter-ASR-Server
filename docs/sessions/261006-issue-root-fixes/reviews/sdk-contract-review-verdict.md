# #76 双向进展与上传中错误测试契约独立验收

- Task-Id：dlg-20261006-075921-d91041
- Risk-tier：internal
- 审查对象：`e849c21748392ad848131e07ff17d32e4cc83a8b..137032657a2ca9f5a3bf66194a5ddf24334e1956`
- 新测试卡增量：`5c05a0c4023140b2d3bdb20413936f6105415108..137032657a2ca9f5a3bf66194a5ddf24334e1956`
failure-visibility: p1-found

## 冻结与隔离

未读实现报告、旧 verdict 正文或 `progress/sdk-progress-progress.md` 自述；旧 verdict 仅核 Git blob：`3068b668bbc2fc67fde87d7e143a84e38467c7e4`。全量 OCR 与人审均排除此二文件；人审覆盖其余生产 SDK、测试、SDK README、协议文档和真实调用点。原始契约取自 Git 对象 `8e93f7e49b07c8a25d199d0942dd7145b48f339b:docs/sessions/261006-issue-root-fixes/design.md`，并对照 `sdk/README.md`、`docs/reference/protocol.md`。

增量四问（5c05..137）：①仅增加与 I1/I2/收尾约束对应的测试覆盖，没有越界修实现；②无新增抽象；③`_CloseObserver` 只观测真实 send/close 状态，无生产状态镜像；④未形成替代生产或测试路径。增量仅改 `tests/test_sdk_progress_watchdog.py`。

## OCR

- 实际命令：`ocr-review --repo <worktree> --from e849c21748392ad848131e07ff17d32e4cc83a8b --to 137032657a2ca9f5a3bf66194a5ddf24334e1956 --audience agent --concurrency 4 --background-file /tmp/caps76-contract-review-spec.md --exclude 'docs/sessions/261006-issue-root-fixes/progress/sdk-progress-progress.md,docs/sessions/261006-issue-root-fixes/reviews/sdk-review1-verdict.md' --format json`
- status=`reviewed`，profile=`minimax`，coverage=`complete`，候选 3/3 已核；两个被排除文件没有送入 OCR。
- 其三条候选与独立验证及本仓定级见下表；工具严重度不直接沿用。

## Findings 与定级

| 候选 | 工具标注 → 本仓 | 真实触发？ | 后果可接受？ | 结论 |
|---|---|---|---|---|
| `client.py:_transcribe_connected`：收到 final 即置 `completed=True`，之后仍 await 上传任务回收；此时 deadline/cancel 命中会跳过预先 abort，再进入可能阻塞的 graceful `__aexit__`。 | OCR high → P1 | 是。scratch 使用真实 raw WS、final-after-3-frames、真实 pending send/paused socket，并只门控 cleanup gather 扩宽取消窗口；deadline 后调用仍挂住。 | 否。绝对 `deadline_total` 到期后仍不能返回，连接未回收。 | P1：违反 I3。自然调度命中频率未测；受控窗口证实该真实等待点可被截止取消。 |
| `tests/test_sdk_progress_watchdog.py:_pending_sdk_tasks`：只匹配 `_transcribe_connected.`、`transcribe_file.`、`_operation.`；独立 task 的 coroutine qualname 是 `_receive`，因此“无遗留任务”断言漏检接收任务。 | 本审查 → P2 | 是。此 helper 在新增清理用例中实际运行，当前过滤条件排除 `_receive`。 | 有界资源泄漏回归可能被误报为通过；不是当前已观察到的运行时泄漏。 | P2：I2 清理断言覆盖不完整。 |
| `client.py:_receive` 的新增 `idle_messages` 参数不再读取，令牌由 `mark_progress` 写入。 | OCR low → P3 | 是。生产路径会传入，但函数不消费它。 | 无运行时影响；仅留死接口。 | P3：非阻塞维护项。 |
| `client.py:_audio_frame_bytes(data_length, encoding)` 不读 `data_length`。 | OCR low → P3 | 是。帧构造与计数会调用该 helper。 | 无行为影响；单参数多余。 | P3：非阻塞维护项；helper 本身被帧构造和计数共用。 |

## 不变式与证据

- I1：raw-socket/read-gate 用例证明真实 `ws.send` pending、匹配下行跨越多个 idle 后仍存活、解除背压后取得 final；发送完成后 observer 清为 false。未知 type 与陌生 task_id 不刷新 idle。
- I2：三种错误码在上传尚未发 final 时透传原 code/message，连接会话结束；AsrError 不要求公开 task_id。以 scratch 捕获实际 `writer.write` 参数及真实客户端接收，三条 ErrorMessage wire body 均含当前 task_id、对应 code/message、`retryable=false`。红验在 5c05 原“末帧后 error”用例追加相同非 final 断言，明确以 `AssertionError: assert True is False` 命中；这是 fixture 时机对照，不是生产缺陷复现。接收任务清理 oracle 的遗漏见上方 P2。
- I3：文档与现有 SDK 测试保持 `duration*4+120`、显式 deadline 为绝对墙钟；五文件窄测含 deadline-stage 用例。另有 P1：final 后回收窗口遇截止时没有先 abort，实际观察到 deadline 后挂住，手动 abort 才释放。
- I4：保留 raw WebSocket、`read_gate`、生产 `ErrorMessage` / `RecognitionMessage` schema 与 `_CloseObserver`；无 SDK 生产新机制、无重试/fallback/逐帧 send 限时。

## 环境、命令与预算

- Python 3.11.15 / websockets 15.0.1：SDK 实际导入本 worktree 的 `sdk/capswriter_asr/client.py`。两完整文件无 `-k`、无 NODE/PYTEST 环境过滤 collect-only 得 46 项；指定五文件窄测：61 passed / 77.26s。
- Python 3.12.3 / websockets 16.0：两个完整文件无过滤 collect-only 得 46 项；`pytest -ra`：46 passed / 65.98s，skip=0、fail=0。
- 环境使用 `uv run --no-project`；临时探针保存在 `/tmp/caps76-review/`。首次探针因脚本位于 `/tmp` 被该目录 `concurrent.py` 遮住标准库而失败，移到独立子目录后导入与测试成功。未跑全套测试或 CI。
- 真实 producer wire 三错误码探针：3 passed；5c05 红验注入：目标 assertion 单测失败 1 项，栈落在目标 assertion；cleanup deadline scratch 探针：1 passed，打印 `stuck_after_deadline=True, send_pending_at_cleanup=True, socket_paused_at_cleanup=True, final_sent=True`，只在观测后手动 abort 清理。
- 预算分别核算：旧实现卡 `e849..5c05` 为 1,351 changed lines，超过当时 hard 1,200 共 151；本独立测试卡 `5c05..137` 为 80 changed lines，等于 target 80、低于 hard 120。新卡合格不追认旧卡预算违规。

## 收尾

本 verdict 仅提交此文件；不改 PR #90 head/draft、issue #76，不创建 PR、不合并、不部署。完整取证及命令记录写入派发报告（文件名 `report.md`），由本机 `DELEGATE_REPORT_PATH` 指定。
