# #76 SDK 双向进展与收尾独立审查

- 冻结审查范围：`e849c21748392ad848131e07ff17d32e4cc83a8b..5c05a0c4023140b2d3bdb20413936f6105415108`
- 先审修后增量：`050b6dc5f4756abf72f511c0012a2b0ef2b65c49..5c05a0c4023140b2d3bdb20413936f6105415108`
- OCR 前置：`status=reviewed`，CLI 完成，Minimax profile，4/4 findings 已核验。
- OCR 命令：`ocr-review --repo <本卡树> --from e849c21748392ad848131e07ff17d32e4cc83a8b --to 5c05a0c4023140b2d3bdb20413936f6105415108 --audience agent --concurrency 4 --background-file <摘要>`（仓库与摘要路径使用任务卡占位符，避免提交本机路径。）

failure-visibility: p2-only

## Findings

### P2 — 背压用例没有断言 `ws.send` 当时确实挂起

位置：`tests/test_sdk_progress_watchdog.py:453`

用例关闭服务端读闸后，断言仍收到至少 5 条结果、调用未结束且已读帧数少于总数（465–483 行）。这些条件说明上传未完成，但没有观察实际 `ws.send` 是否处于 pending；发送缓冲暂时未满也能满足这些断言。任务验收明确要求证明实际 `ws.send` pending，因此当前回归测试可能在目标背压没有发生时仍通过。独立窄测用只包真实 `websockets.connect`/`send` 的观察器复现了 pending send，但该断言只存在于 scratch 探针，未锁入仓库测试。

### P2 — 名为“上传途中”的服务端错误用例实际在最终帧后发错

位置：`tests/test_sdk_progress_watchdog.py:522`

该用例设置 `on_upload_complete="error"`（525 行）；假服务端仅在读到 `is_final` 帧后调用 `_finish()`（`tests/test_sdk_progress_watchdog.py:227-230`），错误帧也由该完成回调发送（242–259 行）。所以测试证明的是上传完成后的错误透传，没有覆盖上传仍 pending 时收到错误、取消剩余上传并回收任务的失败路径。测试名和文件开头矩阵（14 行）对所覆盖时机的描述与实际行为不符。

## 已核实的不变式与证据

- 上传成功帧和匹配当前 `task_id` 的已知 `result`/`error` 共享 `mark_progress`；未知 type 与其它 task 被忽略：`sdk/capswriter_asr/client.py:377-383, 424-429`；对应测试含 `tests/test_sdk_progress_watchdog.py:452-511`。
- 自动预算公式及显式 `deadline_total` 路径保留；持续进展不能放宽绝对截止：`sdk/capswriter_asr/client.py` 及 `tests/test_sdk_deadline_stage.py`、`tests/test_sdk_progress_watchdog.py` 的连续进展截止用例。
- 取消、idle 错误及有界收尾的任务清理有窄测覆盖；成功路径设置 `completed` 后优雅关闭，异常路径 abort 并回收：`sdk/capswriter_asr/client.py:399-400, 465-493`；本地窄测覆盖 idle、取消、关闭截止和任务泄漏。
- raw-socket 假服务端读取真实 SDK 上传帧；常规中间结果/最终结果由 `RecognitionMessage.to_json()` 生成，错误由 `ErrorMessage.to_json()` 生成，task id 来自实际收到的帧：`tests/test_sdk_progress_watchdog.py:35-40, 179-189, 242-259`。
- `git diff --check e849c21748392ad848131e07ff17d32e4cc83a8b..5c05a0c4023140b2d3bdb20413936f6105415108` 通过，无输出。

## 验证范围与限制

- 使用 Python 3.11.15 / websockets 15.0.1 的隔离环境，将与冻结 HEAD blob 完全一致的 watchdog 测试文件复制到 scratch，针对相关用例运行，结果 `8 passed in 23.22s`。Python 3.12 / websockets 16.0 的相关窄测结果 `5 passed in 6.25s`。
- 原始仓库全量测试未运行；审查范围固定在上述 base/head。scratch 中另有真实连接边界观察器窄测，背压期间结果持续到达、frame 数未满，并直接断言 `ws.send` pending，结果 `1 passed in 9.62s`。
- 冻结实现范围共 9 个文件，`git diff --stat` 为 1290 insertions、61 deletions（1351 changed lines）。这比实现卡 hard 1200 多 151 行，作为独立预算偏差记录；本审查不改被审对象。
