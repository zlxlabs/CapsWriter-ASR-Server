# auto-budget-review2 审查结论（PR #71）

- 审查对象：冻结区间 `e117f0249b2cd503308fa1d682a72dcc6949b432..1c5e7b6671daa1dfe843d04e89672502d97e037e`（H0=`9efc7a6`，H1=`1c5e7b6`）
- 审查者：dlg-20261004-144406-2fb2fe（独立 review，只读 diff / `git show`，未读实现方 report.md）
- 日期：2026-10-04
- 第 1 轮：`6d7f6f9` 的 `auto-budget-review1-verdict.md`，`failure-visibility` 为 p2-only（protocol.md 仍写旧公式）
- 总体结论：**pass**。第 1 轮那条 P2 已关闭。本轮没有新的 P1，没有新抽象，没有双路径。第 1 轮 3 条 P3 保持 backlog，不升级。
failure-visibility: clean

## H0..H1 四问（本轮必核，均有实测）

1. **第 1 轮 P2 已关闭。** `git grep -n 'max(120 秒, 音频时长 + 60 秒)' 1c5e7b6 -- docs/reference/protocol.md` 无命中、退出码 1。同一命令打在 base `e117f02` 上命中 `docs/reference/protocol.md:161`，判据能分出「有」和「无」。H1 的同一行改为转录预算 ``音频时长 × 4 + 120 秒``，并写明「自动预算是 watchdog（挂死检测），不是识别时限 SLA」。`sdk/README.md:52` 仍出现这串字，位置在「旧公式 … 会误杀」的历史引证里；当前合同在同文件第 50 行。这不是第二份生效合同，不重开 P2。
2. **没有新的 P1。** H0..H1 的 diff 只有 `docs/reference/protocol.md`（+1/-1）和进度档。运行时路径没有改。全量 `e117f02..1c5e7b6` 复看后，公式、超时消息、`wait_for`、`on_progress` 都对得上 I1–I5（见下表）。内部档 P1 红线（数据丢失、静默出错、崩溃、越权、损坏他人数据）本轮没有新的可触发缺陷。
3. **没有新增无第二消费者的抽象。** H0..H1 没有新函数、新状态、新配置或包装层。进度档只记录这次文档同步。H0 已有的 `_auto_budget`、`set_deadline(..., duration=)` 和 `budget` 快照都有超时消息与测试在消费，本轮不新开。
4. **没有双路径。** 生产调用点只有 `set_deadline(_auto_budget(duration), duration=duration)`（`client.py:469`）。`_auto_budget` 只有一条 `return duration * 4 + 120`（`client.py:441`），下限由 `+ 120` 覆盖，没有 `max` 分支。`deadline_total is None` 是原来就有的显式墙钟覆盖，不是第二套自动预算。H1 没有加代码路径。

## 不变式核实（冻结全量，H1 树上实测）

| 不变式 | 判定 | 实测 |
|---|---|---|
| I1 `_auto_budget(93)>306`，公式 `duration*4+120` | 成立 | H1 函数体 `return duration * 4 + 120`。直接调用 `_auto_budget(93)` 得 492，492>306。红验在旧公式下为 `153.0 > 306` 失败 |
| I2 默认路径超时消息含「自动预算」、预算秒数、音频时长 | 成立 | `timeout_error()`（`client.py:528-535`）默认路径名字是「自动预算」，detail 带 `seconds:.0f`，duration 非空时再带 `音频 {duration:.1f} 秒`。`test_default_timeout_message_reports_budget_and_audio_duration` 锁「自动预算」「492」「93.0」「远端转录」 |
| I3 README 与 protocol.md 都写 watchdog ≠ SLA，且 protocol.md 不再写旧公式 | 成立 | `git grep -n '不是识别时限 SLA' 1c5e7b6` 命中 `docs/reference/protocol.md:161` 与 `sdk/README.md:52`。protocol.md 旧公式 grep 为 0（见四问 1） |
| I4 生产路径无 `asyncio.wait_for` Call | 成立 | 对 H1 的 `sdk/capswriter_asr/` 下 6 个 `.py` 做 AST，`wait_for` 调用数总计 0。`git grep -n 'asyncio.wait_for' 1c5e7b6 -- sdk/capswriter_asr/` 只有 `client.py` 359/382/557 三处注释 |
| I5 不把 on_progress 续期编码为根因 | 成立 | `git diff -U0 e117f02..1c5e7b6 -- sdk/capswriter_asr/client.py` 无 `on_progress` 改动。进度档写明否决在 on_progress 续期上补实现。文档里的 watchdog 句与 README 同一表述，没有新增续期代码 |

`git grep -n 'duration + 60' 1c5e7b6 -- sdk/capswriter_asr/client.py` 无命中、退出码 1。

## 红验与 H1 绿验

解释器是 scratch 树内 uv 虚拟环境的 CPython 3.14.3（本机 `python3` 被 uv 解析到 3.14；仓库地板是 3.11）。这两条断言是纯算术，不经过 `asyncio.wait_for`。153 与 492 的比较不随 3.11/3.14 改变。虚拟环境在 scratch 树内，树已拆除；审查工作树和主仓都没有 `.venv`。

1. **base `e117f02`，只拷入两条锁之前。** `from sdk.capswriter_asr.client import _auto_budget` 为 `ImportError`（符号在 base 上不存在）。生产调用点仍是 `set_deadline(max(120.0, duration + 60.0))`。
2. **行为红。** 在该调用点保持不动的前提下，把同名函数定义成旧公式 `return max(120.0, duration + 60.0)`，哨兵 `RED-VERIFY-OLD-FORMULA` 在第 431 行，`grep` 已确认。导入的 `client.py` 属于这棵 scratch 树，`_auto_budget(93)` 打印 `153.0`。再只追加 `test_auto_budget_covers_observed_93s_recognition` 与 `test_auto_budget_formula_is_four_times_duration_plus_120`。pytest `--noconftest -k "covers_observed_93s_recognition or formula_is_four_times"`：**2 failed**。失败是 `assert 153.0 > 306` 与 `assert 153.0 == 492`，不是 ImportError。
3. **H1 `1c5e7b6` 绿。** 不注入。同一对 `-k`：**2 passed**。导入文件属于 H1 scratch 树，`_auto_budget(93)` 为 492。

`tests/test_sdk_samples_total.py` 的断言仍是字面量 `deadlines == [(2520.0, 600.0)]`，没有改成调用 `_auto_budget(600)`。

## OCR

对 H0..H1 重跑 `ocr-review`（`--from 9efc7a6 --to 1c5e7b6`）。stdout envelope：`status=skipped`，`reason=no_reviewable_items`，`findings=[]`，`coverage=none`。这是没扫，不是扫过且干净。上面的 pass 不引用这条 skipped。

## 第 1 轮 P3（不升级，仍 backlog）

- 超时秒数 `:.0f` 会把不足 1 秒的显式 `deadline_total` 显示成「0 秒」。默认预算是 120 或 `时长×4+120`，无功能后果。
- 本地准备阶段的默认消息也叫「自动预算 120 秒」，此时还没有音频时长。README 已写明该阶段消息不出现音频秒数。
- 入口 120 秒上限在 `transcribe_file` 里有两处字面量，当前同值。

`test_local_stage_timeout_message_names_entry_cap` 实际传入 `deadline_total=7`，锁的是显式路径的消息结构，不锁默认入口 120。这是第 1 轮已见的测试缝，不升成 P2。

## 范围

冻结 diff 6 个文件、233 行（client.py、sdk/README.md、protocol.md、两个测试、进度档）。本卡只新增本 verdict。未改实现，未标 ready，未合并，未关 issue，未 pin 下游。

## 结论

Card 2 加上 H1 的协议同步后，I1–I5 成立。第 1 轮 P2（protocol.md 旧公式）关闭。本轮没有新的 P1、没有无第二消费者的抽象、没有双路径。3 条 P3 留在 backlog。
