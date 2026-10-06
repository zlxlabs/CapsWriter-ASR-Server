# #76 SDK 双向进展与收尾：独立审查 1

failure-visibility: p2-only

## 冻结范围与结论

- 风险档：internal。固定审查范围：`e849c21748392ad848131e07ff17d32e4cc83a8b..050b6dc5f4756abf72f511c0012a2b0ef2b65c49`，head 为冻结 H0；未纳入范围外提交。
- 完整 diff：8 个文件，958 insertions、57 deletions。未将 600 行卡面上限套到被审实现。
- 结论：P1 0 项，P2 3 项，P3 1 项。未读取实现方 `report.md` 或旧 review verdict；已提交 diff 中的进展文档仅按公开文档审阅，关键证据另行实测。
- 本文件是本卡唯一新增仓库文件。

## OCR 前置扫描

执行命令：

```text
ocr-review --repo . --from e849c21748392ad848131e07ff17d32e4cc83a8b --to 050b6dc5f4756abf72f511c0012a2b0ef2b65c49 --audience agent --concurrency 4 --background-file ../../../../../../tmp/capswriter-sdk-review1-dlg-20261006-042522-4c2d73/spec-summary.md
```

命令中的仓库和摘要路径按 checkout-relative 方式记录；本机绝对路径保留在派发报告，不写入公开 verdict。摘要为 2453 字节。完整 stdout JSON 为 75437 字节，`jq -e 'type == "object"'` 退出 0，信封判据为 `status=reviewed_fallback`、`reason=primary=leg_timeout; backup:deepseek=success`，共 3 条 OCR finding。stderr 记录主腿 `leg_timeout elapsed_s=900.107`，备链 `deepseek` 成功；未把外部 severity 直接当本仓定级。

- OCR `medium`（`client.py:387`）经协议合规的网络探针确认。触发：是，匹配的真实结果可在上传结束后持续到达；后果：停滞秒数报错但 idle 仍按时触发，也不改变识别结果；不满足 P1 的不可接受后果条件，本仓判 P2，列为 Finding 2。
- OCR `low`（`client.py:239`）确认 `_audio_frame_bytes` 的 `data_length` 参数未读取。每次帧计算会触发，但无运行时后果；判 P3，列为 Finding 4。
- OCR `low`（`client.py:366-367`）确认 progress 快照注释没有说明生产者/消费者。这个文档缺口与 Finding 2 的共享快照问题合并记录；单独看没有当前运行时后果，不判 P1。

## Findings

### P2-1：绝对截止打断优雅 close 时没有 abort 连接

- Spec：`deadline_total` 是覆盖连接、上传、结果及有界收尾的绝对截止；异常/取消路径需有界 abort 并回收任务。
- 位置：`sdk/capswriter_asr/client.py:480-487`。`except BaseException` 只覆盖连接主体；成功结果开始 `connection.__aexit__()` 后，截止取消发生在 `finally` 内，不会进入该 abort 分支。
- 证据：独立 raw-socket 探针用协议完整的 `RecognitionMessage` 回 final 后保持连接且不读 close 帧，运行 `deadline_total=5`。输出：`caller_done=true elapsed=5.0s outcome=AsrError code=timeout final_sent=True exit_started=True exit_cancelled=True exit_error=None transport_closing=False websocket_state=CLOSING server_session_alive=True`。探针在记录状态后主动 abort 清理。
- 后果：截止返回时 WebSocket 仍未关闭，对端会话仍存活；未证明其永久存活，但它没有在本次调用的异常收尾中被回收。触发窗口是 final 后的 graceful close 遇到不响应 close 的对端并与截止重合。判 P2。

### P2-2：收到匹配结果没有刷新诊断用的最近进展时刻

- Spec：停滞消息中的阶段、帧数、结果数和距最近进展秒数必须是 SDK 实际观察到的事实；新 progress 对象需说明多个生产者与必要消费者。
- 位置：`sdk/capswriter_asr/client.py:331-343`、`:366-387`、`:419-423`。`_receive` 对匹配消息只放入 idle 队列并累加 `results`；`last_at` 仅由上传侧 `mark_progress()` 更新。快照注释也未标明 `_receive`、`upload` 和 `stall_error` 的读写关系。
- 证据：独立探针使用 `core.protocol.RecognitionMessage.to_json()` 生成完整协议 payload；停止发送前收到匹配结果后，实际距最后结果 1.00 秒，SDK 报文为 `等待结果连续 1 秒没有进展：已发送 1/1 帧，收到中间结果 11 条，距最近进展 2 秒`。
- 后果：idle 截止本身仍正确，但消息给出错误的最近进展秒数，可能将此前持续收到结果的时间算进去。判 P2。

### P2-3：新增网络夹具的 result payload 不符合协议 schema

- Spec：真实网络 producer payload 的 task 帧 ID/schema 必须符合协议；夹具不得 mock SDK 自身逻辑。
- 位置：`tests/test_sdk_progress_watchdog.py:165-168`、`:216-219`。匹配的中间与最终 result 手工省略 `time_start`、`time_submit`、`time_complete` 等 `RecognitionMessage` 必备字段。`core/protocol.py:107-128` 定义并序列化这些字段。旧用例 `tests/test_sdk_client.py:1033-1037` 的“持续进展”消息还缺 `task_id`，现会被 `_receive` 过滤掉。
- 证据：新增 14 条测试通过，但它们的 payload 与服务端 `RecognitionMessage.to_dict()` 实际 schema 不同。另用真实 SDK 上传与 raw-socket 对端、并以 `RecognitionMessage` 构造完整上下行 payload 实测：`valid_protocol_payload=true underlying_ws_send_pending=true pending_seconds=4.0 frames_read=3/10 matched_results=27 caller_alive=true`；解开读闸后为 `after_release=completed final_task_id_matches=true outstanding_send_tasks=0`。
- 后果：测试没有保留真实 server result schema；旧的总截止测试在无有效进展消息时仍可通过，完整 payload 合同也没有被新增测试锁住。判 P2（测试/契约覆盖缺口，不是已观察到的生产解析错误）。

### P3-4：帧字节 helper 的长度参数未使用

- 位置：`sdk/capswriter_asr/client.py:239-255`。`_audio_frame_bytes(data_length, encoding)` 只按编码选择常量，长度参数不会影响返回值；长度仅由 `_audio_frame_count` 消费。
- Spec：无直接行为不变式受影响。后果限于签名误导和多余参数；判 P3，不阻塞。

## 不变式证据与未验证限制

- 连接建立后开始 idle、上传成功 send 更新 idle：`client.py:418-427`；锁定用例为 `tests/test_sdk_progress_watchdog.py::test_blocked_upload_with_silent_server_fails_on_idle_before_upload_done` 与 `::test_successful_sends_keep_upload_alive_past_one_idle_window`。
- 匹配 task_id 的已知消息与噪声隔离：`client.py:324-343`；协议服务端 `RecognitionMessage.to_dict()` 和 `ErrorMessage.to_dict()` 都携带 task_id，proxy `no_backend` 错误也带 task_id。新增匹配消息夹具缺部分 schema（Finding 3）；完整 payload 另由上述独立探针验证。
- ws.send 实际 pending/backpressure：独立探针直接观察底层 `ws.send` Future pending 4 秒，期间完整协议中间结果持续到达且调用存活；解闸后完成，观察到的 send task 全部结束。
- 自动总预算 `_auto_budget(duration) = duration * 4 + 120` 与显式 `deadline_total` 路径未改；相关窄测通过。截止恰落在 graceful close 的收尾缺口见 Finding 1。
- 服务端上限、17501 秒样本成功承诺和下游 pin 均未改写或新增承诺。
- 仅运行相关窄测：`tests/test_sdk_progress_watchdog.py` 14 passed；`tests/test_sdk_client.py tests/test_sdk_deadline_stage.py tests/test_sdk_samples_total.py` 52 passed。未跑本机全量 suite，未做生产部署测试。
- 探针使用的环境为 Python 3.12、`websockets` 16.0；SDK 依赖声明下限为 `websockets>=15.0.1`。
- 卡面记录主干基线查询失败（`gh api request failed`），继承红无法判定。
- 原异常在常规 server error/cancel 用例中保留；没有单独构造“关闭操作自身再抛错”的双故障探针，该并发形态未验证。

## 验证

冻结实现范围 `git diff --check e849c21748392ad848131e07ff17d32e4cc83a8b 050b6dc5f4756abf72f511c0012a2b0ef2b65c49` 退出 0、无输出。verdict 提交自身的 `git diff --check`、commit SHA、clean status 与远端核验记录在派发报告。
