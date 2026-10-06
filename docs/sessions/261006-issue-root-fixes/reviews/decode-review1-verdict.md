# #87 解码已知错误传播：独立审查 1

- 风险档：internal
- 冻结范围：`e849c21748392ad848131e07ff17d32e4cc83a8b..d196db1277dd9d0339f09c32536b42633317ffce`
- 审查 head：`d196db1277dd9d0339f09c32536b42633317ffce`
- 结论：clean；本范围未发现违反任务卡 spec 的新增问题。
failure-visibility: clean

## OCR 前置审查

OCR 状态为 `reviewed`，覆盖状态 `complete`，主腿 profile 为 `minimax`，工具 findings 为空。该结果仅作初筛；以下结论来自独立固定范围审查。

实际命令：

```sh
ocr-review --repo "$WORKTREE" --from e849c21748392ad848131e07ff17d32e4cc83a8b --to d196db1277dd9d0339f09c32536b42633317ffce --audience agent --concurrency 4 --background-file "$SCRATCH_DIR/spec-summary.md"
```

上式为本机路径脱敏后的命令记录；完整展开后的实际 shell 命令保存在本次派发报告中。

stdout envelope 原文：

```json
{"status":"reviewed","profile":"minimax","model":"MiniMax-M3.1-Flash-Preview","reason":"primary_selected","findings":[],"cli_status":"complete","coverage":"complete","verify":{"verify_status":"skipped","verifier":"none","concurrency":4,"counts":{"total":0,"verified":0,"confirmed":0,"refuted":0,"unverifiable":0,"unverified":0},"reason":"","budget_s":900.0,"finding_timeout_s":120.0},"attendance_ledger_write":"ok"}
```

## 审查证据

固定范围完整 diff 涉及 7 个文件：

- 修改：`core/server/connection/audio_decoder.py`、`core/server/connection/ws_recv.py`、`tests/test_audio_decoder.py`
- 新增：`docs/sessions/261006-issue-root-fixes/design.md`、`docs/sessions/261006-issue-root-fixes/progress/decode-failure-progress.md`、`docs/sessions/261006-issue-root-fixes/progress/design-preflight-progress.md`、`tests/test_ws_decode_failure.py`

1. 已知 reader 错误在 `_END` 到达时由公共迭代器转成 `decode_failed`：`audio_decoder.py:147-159` 记录进程退出/未对齐错误并投递结束标记，`audio_decoder.py:172-189` 在消费结束标记时抛出。新增测试分别锁住非零退出且不调用 `finish()`（`tests/test_audio_decoder.py:295-326`）、真实 ffmpeg 已输出 PCM 后被 SIGKILL（`:329-366`）和未对齐输出（`:368-391`）。
2. 正常 EOF、stderr 警告但退出码 0、取消保持各自语义：正常压缩 EOF 有 `test_flac_stream_accepts_irregular_input_and_preserves_samples`；警告 + rc0 有 `tests/test_audio_decoder.py:394-415`；取消有 `:417-427`。被审网络层只迭代 `cache.decoder.pcm_chunks()`（`ws_recv.py:239-253`），未读取私有 `_reader_error`。全仓 Python 调用点检索显示 HTTP 使用独立 `FileSourceDecoder`（`core/server/http_file_runner.py:86-168`），它不属于本次改动；HTTP 行为未改。
3. 无末帧的真实 WS 失败路径由 `tests/test_ws_decode_failure.py:108-148` 锁定：通过 `/proc` 找到新子进程、等待服务端识别调用证明解码已推进，再杀进程；客户端收到解析后的 `type=error`、`code=decode_failed`、`retryable=false`，随后连接关闭；进程消失且 `/health active_tasks=0`。`collect_terminal` 按目标 `task_id` 等待（`tests/harness/client.py:61-77`），错误 JSON 的生产契约含 `type/task_id/code/message/retryable`（`core/protocol.py:148-165`）。另有正在 feed 时死亡用例（`tests/test_ws_decode_failure.py:151-196`）。
4. 同 tick 错误优先分支位于 `ws_recv.py:408-421`。确定性测试 `tests/test_ws_decode_failure.py:254-295` 给 consumer 与 recv 同时设置完成结果，确认 `asyncio.wait` 返回两个已完成任务，并要求实际 helper 抛出 `decode_failed`；按冻结前代码的分支，两个任务都完成时会返回 recv 帧，因此该断言会抓住新增分支。
5. 异常处理路径把 `AudioDecodeError` 以当前活动任务的 `task_id` 传给 `queue_error_and_close`（`ws_recv.py:498-505`、`:615-624`；`ws_send.py:34-63`），连接 finally 清理任务状态和 socket 关联（`ws_recv.py:659-675`）。没有发现网络层错误分类读取私有解码器状态或修改 HTTP 的情况。
6. 新增设计/进度文档中的范围与限制按文档 diff 审查；文档所述运行结果未作为本 verdict 的运行证据，以上关键不变式均单独从被审代码、测试断言和实际 payload 生产链核对。未读取派发实现报告或旧 review finding。

## 验证与未验证限制

- `git diff --check e849c21748392ad848131e07ff17d32e4cc83a8b d196db1277dd9d0339f09c32536b42633317ffce` 无输出。
- 未运行本机测试套件；此结论是固定 diff 与消费者/测试契约审查，不是本地测试通过声明。
- 没有真实生产 ffmpeg 事故证据；SIGKILL 测试证明代码处理已启动进程死亡，不证明任何历史生产死亡原因。
- 卡面所述主干基线查询失败（`gh api request failed`），故继承红状态未能判定。
- 本次唯一新增产物为本 verdict；其提交 diffstat 与远端 ref 核验记录在派发报告中。
