# auto-budget-review1 审查结论（PR #71，Card 2）

- 审查对象：冻结区间 `e117f0249b2cd503308fa1d682a72dcc6949b432..9efc7a6d08ee22ce6b5e9b9278b34a6ca49a6d18`（H0=H1=9efc7a6，单提交）
- 审查者：dlg-20261004-142244-b9f3ac（独立 review 卡，只读 diff，未读实现方 report.md）
- 日期：2026-10-04
- 总体结论：**pass**（实现满足 Card 2 spec I1–I5；1 条 P2 记 backlog 不阻塞，3 条 P3 记 backlog）
- failure-visibility: p2-only

## 不变式核实（本轮全部实测）

| 不变式 | 判定 | 实测证据 |
|---|---|---|
| I1 公式 `duration*4+120`，`_auto_budget(93)=492>306`，旧公式必红 | 成立 | 红验：base 树注入旧公式 `max(120.0, duration + 60.0)`（sentinel `RED-VERIFY-OLD-FORMULA` 已 grep 确认在第 431 行）+ 拷入 H0 版 `tests/test_sdk_deadline_stage.py`，6 条新用例全红，其中 `test_auto_budget_covers_observed_93s_recognition` 为行为红（153 > 306 为假，非 ImportError）；H1 上 `test_auto_budget_formula_is_four_times_duration_plus_120` 绿（93→492） |
| I2 超时仍 `AsrError(code="timeout")`，默认路径消息含「自动预算」+预算秒数+音频时长 | 成立 | `client.py`（9efc7a6）`timeout_error()` 返回 `AsrError("timeout", f"转录超过{name} {detail}：{stage['name']}阶段超时")`；H1 上 `test_default_timeout_message_reports_budget_and_audio_duration` 绿，断言 `"自动预算" in message`、`"492" in message`、`"93.0" in message`、`"远端转录" in message`、`"deadline_total" not in message` |
| I3 文档写明 watchdog ≠ SLA | 成立 | `sdk/README.md` 新增段落明写「自动预算是 watchdog（挂死检测），不是识别时限 SLA」；`_auto_budget` docstring 同述 |
| I4 不得把 `asyncio.wait_for` 加回 `sdk/capswriter_asr/` | 成立 | `git grep -n 'wait_for' 9efc7a6 -- sdk/capswriter_asr/` 3 处命中（359/382/557 行）逐目验均为解释性注释；AST 锁 `tests/test_sdk_no_wait_for.py` 在 H1 Narrow 中绿 |
| I5 不把 on_progress 续期编码为根因 | 成立 | 冻结 diff 全量无 on_progress 相关实现/文档改动；进度存档仅记录「否决在 on_progress 续期上补实现」 |

## 验证运行记录

1. **红验（base e117f02，scratch-worktree.sh，独立 uv venv）**：注入旧公式 + H0 测试文件，`pytest --noconftest -k "auto_budget or reports_budget or entry_cap"` → **6 failed, 1 passed, 5 deselected**。6 条红：covers_observed_93s / formula_is_four_times / keeps_the_120_second_floor / lets_93s_identification_finish / reports_budget_and_audio_duration / entry_cap（消息无预算秒数）。passed 的 1 条是存量 `test_default_path_timeout_names_auto_budget`（旧行为本就写「自动预算」）。红是断言失败非 ImportError，注入 sentinel 已 grep 确认，红验有效。
2. **Narrow（H1 9efc7a6，scratch-worktree.sh，同 deps + conftest，ffmpeg 在场）**：`pytest tests/test_sdk_deadline_stage.py tests/test_sdk_samples_total.py tests/test_sdk_no_wait_for.py -q` → **24 passed, exit 0**。
3. **生产公式旧写法清零**：`git grep -n 'duration + 60' 9efc7a6 -- sdk/capswriter_asr/client.py` → 0 命中（exit 1）。旧公式仅作为注释/docstring/测试说明文字存在。
4. 红验未污染主仓 venv（venv 全在 scratch 树内，树已自动拆）；/tmp 下临时脚本为本次审查产物。

## 已知越界复核（tests/test_sdk_samples_total.py）

该文件不在实现卡 Scope-Globs，改动为必要偏离且合规：`deadlines == [660.0]`（旧公式对 600s 的输出）改为 `deadlines == [(2520.0, 600.0)]`——**字面值断言，不是 `_auto_budget(600)` 表达式**，未把断言改成调用被测函数，不恒真。不变式「预算取自解码样本数而非容器元数据」保留：若误用容器 1 秒则得 124 ≠ 2520 转红；若公式回退旧版则 660 ≠ 2520 转红。断言牙齿未削弱。✓

## OCR 待核实四项处置（工具标注 → 本仓判定 → P1 两问）

| # | 工具标注（severity 为工具侧） | 本仓判定 | P1 两问实测 |
|---|---|---|---|
| 1 | `:.0f` 把 `deadline_total` 小数四舍五入（0.5→「0 秒」） | P3 backlog，不阻塞 | Q1：真实触发路径是显式传 `deadline_total` 带小数值（如 0.5）时的报错文案；默认路径预算是 120 或 `时长×4+120`，时长由整数样本数/16000 得，显示误差 <1s 无实际误读。Q2：文案显示误差，实际超时行为用真实值裁决，无功能后果。可接受 |
| 2 | 本地准备阶段消息也叫「自动预算 120 秒」，与重锚定预算同名 | 可接受（文档已声明），P3 观察项 | Q1：默认路径本地阶段超时确实报「转录超过自动预算 120 秒：本地准备阶段超时」。Q2：README 已明写本地阶段受入口 120 秒上限约束、该阶段消息不出现音频秒数；两处「自动预算」同属默认路径预算，命名一致不构成误导。可接受 |
| 3 | `docs/reference/protocol.md` 仍写旧公式 `max(120 秒, 音频时长 + 60 秒)` | **P2 backlog，不阻塞合并** | Q1（真实环境实测）：protocol.md:161 明写「转录预算 `max(120 秒, 音频时长 + 60 秒)`」并整段声称 SDK 默认时限合同，SDK README 又链接该文件——读者按此算预算会得到与实现矛盾的旧公式。会触发。Q2：仅文档矛盾，运行时行为正确、SDK README（SDK 自带文档）已改对；后果是读者预算预期错误，无挂死/误杀/数据后果。可接受 → P2。处置：记 backlog 待主脑派文档卡同步 protocol.md（本卡只审不修） |
| 4 | 入口 120 秒上限写了两处字面量（client.py:504 `deadline = {"at": started + (120.0 if …)}`、client.py:512 `"seconds": 120.0 if …`） | P3 backlog，不阻塞 | Q1：改一处漏另一处会让默认路径入口上限不一致。Q2：两处当前同为 120.0，无行为差异；属常量重复非失败路径。可接受 |

## 熵增审查

新增 `_auto_budget` 纯函数（单一公式点 + 可测性，有 5 条用例消费）、`set_deadline` 关键字参数 `duration`（第二消费者为 timeout 消息与测试 recorder）、闭包内 `budget` 快照 dict（替代原先无名可报的预算，I2 需要）。均无第二余抽象，未命中坏味道词表。P3 项 4 的常量重复是本轮唯一熵 +1。

## 范围与边界核对

- 冻结 diff 5 文件：client.py（+33/-6 近似）、sdk/README.md（+4/-2）、test_sdk_deadline_stage.py（+123/-2）、test_sdk_samples_total.py（+9/-4）、进度存档（新增 52 行）。与 Card 2 范围一致；无 fallback/重试/防御式 catch 新增；无 `wait_for` 回加；无 on_progress 根因化。
- 未标 ready、未合并、未关 issue、未 pin 下游、未写他仓；未读实现方 report.md（输入隔离）。

## 结论

Card 2 实现成立，I1–I5 全部实测通过，红验有牙（旧公式 6 红）、Narrow 绿、生产旧公式清零、越界改动未削弱断言。1 条 P2（protocol.md:161 旧公式与 README 矛盾，backlog 不阻塞）+ 3 条 P3（backlog）。建议主脑：合并前或后派一张文档卡同步 `docs/reference/protocol.md` 的预算公式与 watchdog 表述。
