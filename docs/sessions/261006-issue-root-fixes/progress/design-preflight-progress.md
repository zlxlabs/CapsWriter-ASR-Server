# 261006-issue-root-fixes 进度存档

会话：`261006-issue-root-fixes`。本卡 = 设计固化 + 最新主干最小复现（planning 阶段）。
Refs #87, #76, #85, #81（文档卡，不自动关单；关单判据见 design.md）。
设计真身：`docs/sessions/261006-issue-root-fixes/design.md`。

## 里程碑 1：现场核查与基线确认

- 阶段：planning
- 本段结论：
  - 独立 worktree `caps-issues-design-261006`，分支 `card/caps-issues-design-261006`，HEAD `e849c21`（含 PR #84、#86），`git status` 干净。
  - #87 路径复核成立：`audio_decoder.py:128-159` 在 ffmpeg 非零退出时只记 `_reader_error` 再投 `_END`；`:172-185` 的 `pcm_chunks()` 遇 `_END` 直接 `return`；`:187-202` 的 `finish()` 才抛。
  - `ws_recv.py:256-273` `_feed_compressed` 见 `decoder_task` 正常完成即 `return False`，`:376-381` 的 `_receive_compressed_frame` 据此可无错误帧结束连接。
  - HTTP 侧 `http_file_runner.py:137/157/166` 已是 finish 期检查，与 WS 不同构。
  - SDK 侧 `client.py:357-372` 逐帧 `asyncio.wait(timeout=idle_timeout)`；`:380-399` `idle_watch` 先 `await upload_done.wait()`；`:301-305` 任意下行消息在解析前就刷新 idle 令牌。
- 关键决策与否决：
  - 否决把探针 B 的未复现写成「机制已证实」：卡面明令不得把工单猜测当实测机制。
  - 否决为探针单独开分支或改生产代码注入故障：本卡无修复授权。
- 下一步唯一动作：跑有边界探针 A / B。

## 里程碑 2：探针 A 复现成功（观察级）

- 阶段：planning
- 本段结论：
  - 真 ffmpeg（6.1.1）两例对照，同一脚本一次跑完，退出码 0。
  - 合法 EOF：returncode 0，迭代正常结束，16000 样本，`finish()` ok。
  - 故障注入：returncode 251，`_reader_error` 已是 `decode_failed`，但消费协程 `returned_normally`、0 样本、迭代未抛；`finish()` 才抛 `AudioDecodeError:decode_failed`。
  - ffmpeg 子进程两例均 wait 回收，`pgrep -f f32le` 返回码 1 无残留。
- 踩到的坑（红验有效性）：首跑因缺 `websockets` / `httpx` / `numpy` 依赖 ImportError，属探针自身失败，不计入机制证据；补齐卡面窄依赖入口后重跑。
- 下一步唯一动作：跑探针 B（真 SDK + 本地假服务端）。

## 里程碑 3：探针 B 未复现（机制未证实）

- 阶段：planning
- 本段结论：
  - 已取得可靠事实：`task_id` 从服务端实收第一帧解出；14 182 340 字节负载上传未触发逐帧 idle 误杀；12s 快照显示 38 条合法中间结果已发出，`_receive`/`idle_watch` 健康。
  - 未复现原因：回环 socket 缓冲吸收整份负载，背压未真正到达 `ws.send`，被测失败前提不成立。
  - 附带观察：未知 `type` 当前确实会刷新 idle 令牌（`client.py:305` 先 put 再解析），卡 B 收窄它属行为变更，须显式锁测试。
  - 自身探针缺陷两处已修：服务端 `max_queue=None` 导致无背压；`websockets.serve` 退出时等待永不结束的 handler 导致挂死。
- 关键决策与否决：
  - 否决继续加时穷举背压构造：已达卡面 12 分钟实测墙钟上限，按卡面要求「明确未知、禁止加时无限查」停止。
- 下一步唯一动作：把 design.md 与本存档提交并 push，交主脑拆实现卡；卡 B 的最小复现入口写入 design.md。

## 里程碑 4：设计与拆卡落盘

- 阶段：planning（收尾）
- 本段结论：
  - `design.md`（131 行，≤250 行约束）含模板全部节：目标 / 非目标 / 为什么不是分区删除约定 / 方案要点与已否决 / 关键不变式 / 本轮实测证据 / 待验证前提 / 验收路径 / 拆卡 / 失败可见性 / 主干基线。
  - spec 与待证机制分开标注：#85 卡死点、#76 历史 ffmpeg 退出触发原因、`audio_too_long` 17501s 样本均列在「待验证前提」，未混入锁定决策。
  - 拆卡表给出每卡候选文件、现有相关测试、调用方/构造方影响与并行边。
- 与卡面的偏差：
  - 探针 B 未完成，按卡面「不编造成功」如实记为未复现并给出最小后续复现入口。
- 下一步唯一动作：由主脑据本设计拆四张实现卡；本卡不开独立 PR。
## 里程碑 5：主脑复核后的设计事实订正（同卡修订，仅文档）

- 阶段：planning（修订）
- 本段结论：
  - 按主脑逐条指正订正设计事实，全部经源码复核，未改生产代码与测试代码。
  - HTTP：`FileSourceDecoder`（`core/server/http_file_runner.py:136-170`）是独立类，与 `AudioDecoder` 无继承或调用关系，迭代 + finish 已整体保证失败可见 → 本批 HTTP 不改，删除首版「WS 与 HTTP 消费同一语义」的共享契约说法与「HTTP 失败必须迭代立即抛」的强制承诺。
  - stderr：returncode 0 也可能有日志，`_stderr_tail` 仅用于错误消息细节；唯一现已知失败条件是 `_reader_error`（非零退出 / 未对齐等），沿迭代传播。
  - 无 error 帧分支订正：`_feed_compressed`（`ws_recv.py:256-275`）的 `False` → `message_handler`（`:381-382`）→ `ws_recv.py:613` 直接 `return`；`_receive_compressed_frame`（`:401-419`）发现提前结束是抛 `RuntimeError` 走 `internal`，属另一条路径，首版把它写成 False 的消费方已删除。
  - 「删除」节改写为本次就是删冗余：删逐帧 send 时限、删 `_END` 无条件正常返回的歧义。
  - 卡 C 根治点改为 `tests/harness/server.py`（`ManagedFakeServerHarness` / `ManagedHttpServerHarness` 的 owner 职责），新增独立 `tests/test_harness_shutdown.py`；卡 A 新增独立 `tests/test_ws_decode_failure.py`；两卡不得同时改 `tests/test_ws_progress_watchdog.py`。
  - 探针 A 故障形态限定：垃圾 FLAC 是「ffmpeg 启动后自行非零失败」，不等于生产「上传中途死亡」；后续验收必须取真实 pid 中途杀死且不发末帧。回收证据限定为已持有的 `Process.wait()` returncode，`pgrep -f f32le` 从完成判据中删除。
  - 未知 `type` 的失败形态改为「在 idle 上暴露」，不再写成「等总预算才失败」。
- 踩到的坑（编辑侧）：
  - `edit` 工具与 python `str.replace` 对同一段中文（含全角括号 + 半角空格的 `（含 ffmpeg 及其孙进程）`）连续返回 count=0，而 `repr` 与码点打印显示完全一致；改用整体重写 design.md 绕开，未绕过任何校验闸。
- 与卡面的偏差：
  - 首轮「探针调用次数超出 18 次预算、墙钟略超 12 分钟」为既有披露，本轮修订**未撤销**该披露，也不主张本轮存在同类超限（本轮未重跑任何探针、未跑全量）。
- 下一步唯一动作：交主脑复验本轮文档修订；仍不开 PR、不 merge。
