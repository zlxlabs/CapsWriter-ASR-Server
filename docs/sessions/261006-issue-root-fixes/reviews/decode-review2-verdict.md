# #87 解码错误传播：运行时反向审查 2

- 风险等级：internal
- 固定对象：`e849c21748392ad848131e07ff17d32e4cc83a8b..d196db1277dd9d0339f09c32536b42633317ffce`
- 审查基线 / H0：`e849c21748392ad848131e07ff17d32e4cc83a8b` / `d196db1277dd9d0339f09c32536b42633317ffce`
- 冻结 diff：7 个文件，708 insertions、5 deletions（net +703）；后续提交不在审查范围。
- Verdict：未发现违反本轮 spec 的 finding。
failure-visibility: clean

## OCR 前置

实际命令：

```text
ocr-review --repo "$REVIEW_TREE" --from e849c21748392ad848131e07ff17d32e4cc83a8b --to d196db1277dd9d0339f09c32536b42633317ffce --audience agent --concurrency 4 --background-file "$SCRATCH_ROOT/spec-summary.md"
```

摘要 1,264 字节。stdout envelope 为 `reviewed_fallback`，profile/model=`deepseek`/`deepseek-v4-flash`，coverage=`complete`，selected_files=`7`，findings=`[]`，cli_status=`complete`；主腿 `minimax` 以 `leg_timeout` 在 900.104 秒超时，备腿成功。OCR 只作前置扫描，本审查仍完整读取固定 diff 和实际消费者。

## spec 不变式与实证

- **已知 reader 错误 EOF**：`core/server/connection/audio_decoder.py:180` 在 `_END` 上读取 `_reader_error`，已知 `AudioDecodeError` 原样传播，其它 reader 异常映为 `decode_failed`；正常 EOF 则返回。约束测试：`tests/test_audio_decoder.py:296`、`:331`、`:369`。正常 FLAC、ffmpeg 短成功 EOF、stderr 警告 + rc=0、取消对照分别由 `tests/test_audio_decoder.py:121`、`:152`、`:395`、`:418` 覆盖；stderr 判错不依赖文本是否非空。
- **真实 WebSocket 无末帧死亡路径**：`core/server/connection/ws_recv.py:401` 的 helper 在消费任务与 recv 同时完成时先取消费结果；接收循环在 `:498` 和 `:618` 分别处理 helper 路径、feed 路径中的 `AudioDecodeError`。约束用例为 `tests/test_ws_decode_failure.py:111`、`:153`、`:200`。
- **发布边界**：`core/server/connection/ws_send.py:66` 复用既有 `queue_error_and_close`，`core/protocol.py:148` 的 `ErrorMessage.to_json()` 发出 `type/task_id/code/message/retryable`；`tests/harness/client.py:61` 从真实 WebSocket 消息做 `json.loads`，并要求终态 `task_id` 等于当前任务。
- **same-tick 失败优先**：`tests/test_ws_decode_failure.py:255` 驱动实际 `_receive_compressed_frame` helper，并断言 `done` 含两任务且错误压过末帧。当前提交单测通过；把该测试文件单独拷到 base 临时 worktree 后，测试以 `AssertionError` 失败并实际返回末帧，导入路径确认来自 base 树，非 ImportError/工具失败。
- **关闭与释放**：生产路径在 `core/server/connection/ws_recv.py:428` 清理 decoder/process，`:659` 进入连接 `finally` 清理活动任务；`tests/test_ws_decode_failure.py:111` 的真实 WS 测试断言错误帧后连接关闭、`/proc` PID 消失、`/health active_tasks=0`。feed 路径另由 `:153` 用例覆盖；本次额外窄探针观察到其错误 JSON 后连接关闭。
- **边界**：`AudioDecoder` 的生产调用点为 `ws_recv.py:241`、`:346`；HTTP 使用独立 `FileSourceDecoder`（`core/server/http_file_runner.py:86`、`:137`），该文件不在本 diff 中。网络处理代码未读取私有 `_reader_error`；本次没有证据将测试中的 ffmpeg 退出外推成真实生产死亡原因。

## 独立复核与命令结果

运行证据从指定提交精确读取：`git show a5a526f4ee9ce5ba3fc1d33a6bc1acc0b738c56c:docs/sessions/261006-issue-root-fixes/progress/decode-runtime-evidence.md`。按证据路径独立核对当前测试源、`collect_terminal` 的 task_id 过滤、ErrorMessage 序列化，以及同 tick base 注入和导入树绑定。

本机窄复核（Python 3.12.3、pytest 9.0.3、ffmpeg 6.1.1）：

- 真实 WS 等下一帧 SIGKILL 用例：1 passed；实际客户端 JSON 白名单为 `type=error`、匹配 task_id=`74395fb7-7d7c-4aef-85fe-892232b5c32f`、`code=decode_failed`、`retryable=false`，message 前缀 `ffmpeg 解码失败，退出码 -9`。
- 当前 same-tick 用例：1 passed。
- feed 中死亡用例：1 passed；实际客户端 error 帧 task_id=`4a77b0fc-156a-406c-a558-0d4c2f135ebf`，`decode_failed`、`retryable=false`，并观察到服务端连接关闭。
- base 红验：使用已核实存在的 `$AGENT_CONFIG_ROOT/scripts/git/scratch-worktree.sh`，`SCRATCH_WORKTREE_ROOT` 指向本卡唯一 scratch。base HEAD 为 `e849c21748392ad848131e07ff17d32e4cc83a8b`；唯一注入文件 `tests/test_ws_decode_failure.py`；实际导入 `.../vt-D9u2SY/worktree/core/server/connection/ws_recv.py`；失败为断言 `同 tick 已知 decode_failed 必须压过 receive 结果，实际得到 '{"is_final": true}'`，pytest exit 1，临时 worktree 随后清理。

未跑全量测试。派发时主干基线不可用（`gh api request failed`），故继承红状态未能判定。没有核实 ffmpeg 在真实生产环境退出的触发原因。

## Findings

无 P1/P2 finding。当前错误传播、正常结束/取消对照、WS 实际错误帧及同 tick 新分支均与本轮 spec 一致。

## 踩到的坑与闸

- OCR 主腿启动后无 stdout 不等于扫描完成；等待至自身预算给出 `leg_timeout` 后，包装器自动切到 DeepSeek 并返回完整 envelope。
- 卡面记载的仓内 `scripts/git/scratch-worktree.sh` 在本仓不存在；先确认后使用 agent-config 提供的 helper，并把临时 worktree 根限制在指定 scratch。helper 的输出确认 dirty 临时树已删除。
- 本机没有 `python3.11` 命令；本机窄复核使用 Python 3.12.3。独立运行证据记录的 Python 3.11.15、websockets 15.0.1 矩阵仅通过精确提交的证据文件复核，本轮未本机重跑。

## 绕过与处置

没有绕过 review 或失败判据。OCR 主腿超时按 wrapper 的实际 fallback envelope 记录；base 红验以真实 AssertionError 为红、导入文件路径指向临时 base worktree，并由 helper 自动回收临时树。

## 与卡面的偏差

未改任何被审文件、默认分支或历史源对象；只新增本 verdict。按卡面未跑全量测试；只运行三条相关窄用例和一个 base 红验。未把设计文档或运行证据中的数字当作测试约束，均回到实际 producer/测试源核对。

## 最贵的一步

OCR 主腿运行 900.104 秒后超时，备腿再耗时 127.225 秒；这段单列为 OCR 耗时，不计入之后的冻结 diff 与消费者审查预算。
