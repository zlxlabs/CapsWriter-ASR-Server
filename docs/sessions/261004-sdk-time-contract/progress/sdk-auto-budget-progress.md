# 261004-sdk-time-contract 进度存档（Card 2：#69 自动预算）

会话：`261004-sdk-time-contract`。Card 2 = 把 SDK 自动预算抽成纯函数 `_auto_budget(duration)`
并改为 `时长 × 4 + 120`（Refs #69），Formula/文案/文档。
前置：Card 1（#67/#68，PR #70）已进主干 `e117f02`，生产路径已无 `asyncio.wait_for`。

## 里程碑 1：现场核查

- 阶段：implementing（起步）
- 本段结论：
  - 基线 `e117f0249b2cd503308fa1d682a72dcc6949b432`（PR #70 已合），分支 `card/sdk-auto-budget-261004`，工作树干净。
  - 卡面「已证事实」复核成立：`client.py:455` 处 `set_deadline(max(120.0, duration + 60.0))`；93 秒音频 → 153 秒预算 < 实测约 306 秒。
  - `timeout_error()` 是 `transcribe_file` 内的闭包，看不到 `_operation` 里算出的 `duration`；卡面已预判这点并要求走 deadline/stage 结构、禁全局变量。
- 关键决策与否决：
  - 否决把 `duration` 做成模块级全局：卡面明令禁止，且会让并发调用互相串值。
- 下一步唯一动作：先写红（纯函数断言 + 93 秒行为锁 + 超时文案锁）。

## 里程碑 2：先红

- 阶段：implementing
- 本段结论：
  - 为让红是**真断言失败**而非 `ImportError`，先把 `_auto_budget` 以**旧公式** `max(120.0, duration + 60.0)` 落盘（纯重构、行为不变），再跑用例：5 红。
  - 红明细：`test_auto_budget_covers_observed_93s_recognition`（153 > 306 为假）、`test_auto_budget_formula_is_four_times_duration_plus_120`、`test_auto_budget_keeps_the_120_second_floor`、`test_auto_budget_lets_93s_identification_finish`（旧预算把 93 秒识别误杀成 timeout）、`test_default_timeout_message_reports_budget_and_audio_duration`（消息里的预算是 153 而非 492）。
- 关键决策与否决：
  - 否决“先写死新公式再补红”：那样红只证明我写对了，不证明测试对旧行为有牙齿。
- 下一步唯一动作：换公式、补 `duration` 回传，跑到绿。

## 里程碑 3：实现 + 绿

- 阶段：verifying
- 本段结论：
  - `_auto_budget(duration) = duration * 4 + 120`；`_operation` 改为 `set_deadline(_auto_budget(duration), duration=duration)`。
  - `duration` 经 `set_deadline` 的关键字参数回传到闭包里的 `budget` 快照 dict（`seconds` + `duration`），未用全局变量。超时消息形如
    `转录超过自动预算 492 秒（音频 93.0 秒）：远端转录阶段超时`；本地准备阶段时长未知，消息只写入口上限、不编造音频秒数。
  - `+120` 覆盖了旧 `max(120, …)` 的下限语义，0 时长仍是 120 秒，无需双分支（`test_auto_budget_keeps_the_120_second_floor` 锁住）。
  - 绿：Narrow（四个 SDK 文件）54 passed exit 0；全量 `tests/` 463 passed / 3 skipped exit 0（基线 457/3，净增 6 条新用例）。
- 关键决策与否决：
  - **越界改 `tests/test_sdk_samples_total.py`（必要偏离，已在报告披露）**：`test_deadline_uses_decoded_sample_count` 写死 `deadlines == [660.0]`，那是旧公式对 600 秒音频的输出（`max(120, 600+60)`），公式一换必红，无法靠不动它满足 Verify-Command exit 0。该用例真正的不变式是「预算取自**解码样本数**而非容器元数据」（源 WAV 只有 1 秒），故保留该不变式：把记录器从 `list.append` 换成 `record_deadline(seconds, *, duration=None)`（原替身无法接收第二个参数），期望值改为 `[(2520.0, 600.0)]` 并写明「若误用容器 1 秒会得到 124」。断言牙齿未削弱。
  - 否决把该文件的期望值写成 `_auto_budget(600)` 表达式：会让它对公式改动恒真，正好抹掉这卡要锁的东西。
  - 否决改 CI Python 矩阵、pin 下游、动服务端：均超本卡边界。
- 下一步唯一动作：commit + push + draft PR（`Refs #69`）。

## 里程碑 4：推送与 PR

- 阶段：verifying（收尾）
- 本段结论：
  - 终态验证：Narrow exit 0、全量 `tests/` 463 passed / 3 skipped exit 0。改动 4 文件 +167/-10（预算目标 250 / 硬上限 700）。
  - 完成条件 grep 复核：`_auto_budget` 定义与测试均命中；`assert _auto_budget(93) > 306` 在 `tests/test_sdk_deadline_stage.py:301`；`duration + 60` 在 `client.py` 零命中；`wait_for` 只剩 Card 1 留下的注释，本卡未加回。
  - draft PR（base master），head `card/sdk-auto-budget-261004`，远端 SHA 与本地一致。未标 ready、未合并、未关 issue，正文只写 `Refs #69`。
- 关键决策与否决：
  - 否决在 `on_progress` 续期上补实现：服务端 progress 节奏未实证，卡面把它排除在根因之外，不臆造。
- 下一步唯一动作：交主脑验收与后续独立审查。