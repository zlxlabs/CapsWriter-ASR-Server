# 独立审查 verdict：SDK 消灭 wait_for / Python 3.11（PR #70）

- 派发：`dlg-20261004-122434-82261d`（review 卡，只审不修）
- 审查对象（H0 冻结）：`b0818dc7859d1d8100e42f5c70cb75d34da422f7..44394ce72b3cb4f5f860ca2b7315da270198bfd0`
- PR：#70（draft，headRefOid = 44394ce，与冻结 SHA 逐字一致）
- 审查树：`sdk-time-contract-review1-261004`（本文件所在 worktree，基线 b0818dc）
- 方法：全量审 diff（8 文件，+322/-14，未因 OCR 已扫而缩范围）＋ base 红验 ＋ H0 双解释器实测 ＋ 机械核对 ＋ CPython 3.11.15 源码核对机制声称

failure-visibility: p2-only

## 结论

**未发现 P1。** I1–I6 六条不变式全部「支持」。OCR 4 条 finding 重判：1 条 P2（3.11 维漏 2 个 SDK 测试文件，实测它们在 3.11 上绿，应改 `tests/test_sdk_*.py`），3 条 ≤P3/backlog（非本卡引入或无真实触发路径）。建议合并前把 3.11 维的 `pytest-targets` 从写死三文件改成 `tests/test_sdk_*.py`（一行改动，且不触碰 ci.yml 注释里已说明的 `test_http_file_tasks.py` 继承红问题）。

## 红验（base `b0818dc`，scratch-worktree.sh，Python 3.11.15，websockets 17.2）

注入方式：`git show 44394ce:tests/test_sdk_no_wait_for.py` 与 `git show 44394ce:tests/test_sdk_client.py` 拷入 base scratch 树（留痕：`grep` 确认两个新用例在树内、`git rev-parse HEAD` = b0818dc、base `client.py` 的 `asyncio.wait_for` 在 360/516 行）。venv 建在 scratch 树内（各树独立），树随命令结束销毁；主仓 `.venv` shebang 守卫空输出（无污染）。

1. **AST 锁——行为红**（rc=1，非 import/syntax 红）。原文：

   ```
   E  AssertionError: 生产路径不得调用会吞取消的 asyncio.wait_for：
   E    sdk/capswriter_asr/client.py:516
   E    sdk/capswriter_asr/client.py:360
   1 failed, 1 passed in 0.03s
   ```

   命中行号与卡面预测（约 360 / 516）逐字一致；同文件自检用例（planted wait_for 必红、注释/字符串不算）绿。

2. **默认预算连接拒绝——行为红，120.082s**（`timeout 150` 外层硬截止内自然失败，rc=1）。原文：

   ```
   E  AssertionError: 连接拒绝耗时 120.082s，超过 5s 说明挂到了自动预算
   E  assert 120.08242713700747 < 5
   1 failed in 120.30s (0:02:00)
   ```

   错误码断言（connection_lost）先过、耗时断言挂到自动预算 120s——正是 #67 的用户可见形态。修前基线红与实现方记录的 120.103s 同形态（0.02s 属抖动）。

## H0（44394ce）实测（scratch-worktree.sh，各树独立 venv）

| 运行 | 解释器 | 结果 |
| --- | --- | --- |
| Narrow（test_sdk_client + test_sdk_deadline_stage + test_sdk_no_wait_for） | Python 3.11.15（uv 托管）/ websockets 17.2 | **38 passed, exit 0** |
| 同上 | Python 3.12.3（系统）/ websockets 17.2 | **38 passed, exit 0** |
| 默认预算连接拒绝 连跑 5 次 | 3.11 | 5× RC=0，单次最长 0.21s（<5s） |
| 默认预算连接拒绝 连跑 5 次 | 3.12 | 5× RC=0，单次最长 0.21s（<5s） |
| 补漏：test_sdk_samples_total + test_sdk_transcode_track（3.11） | 3.11 | **17 passed, exit 0（绿）** |

连接拒绝用例在 H0 上相对 base 的 120.082s → ≤0.21s，五个数量级收敛，I2 成立。

## 机械核对（全部针对冻结 SHA，git 对象非工作区）

- `git grep -n "wait_for" 44394ce -- sdk/`：3 命中全是注释（client.py:359/382/529），**0 处调用**。I1 文本面成立，AST 锁见红验/H0。
- CPython 3.11.15 `asyncio/tasks.py` 源码核对：`wait_for` 存在吞取消分支（`except exceptions.CancelledError: if fut.done(): return fut.result()`）；`asyncio.wait` 的内部 `_wait` 是 `try: await waiter finally: ...`，**无该分支**，取消必然向上抛——client.py 注释的机制声称与解释器源码逐字相符。I6 机制成立。
- `sdk/pyproject.toml`：`requires-python = ">=3.11"`；`git grep "3\.10" 44394ce -- sdk/` 零命中（README 首段已改 3.11）；`git grep -e asyncio.timeout -e sys.version_info 44394ce -- sdk/` 零命中。I5 成立。
- 自动预算公式未动：base client.py:441 与 44394ce client.py:455 同为 `set_deadline(max(120.0, duration + 60.0))`。
- 既有 `deadline_total=2` 连接失败用例（test_sdk_client.py:1027 `test_websocket_connection_failure_maps_to_connection_lost`）仍在；新锁 test_sdk_client.py:1034 **不传** `deadline_total`（`await transcribe_file(audio_path, url)`）。
- I3 锁：test_sdk_deadline_stage.py:181 `test_default_path_timeout_names_auto_budget` 断言 `"自动预算" in caught.value.message`（:201）；上传超时仍抛 `AsrError("timeout", "发送音频帧超过 idle_timeout")`。均在 3.11 Narrow 38 条内绿。

## CI（I4）

`ci.yml` @44394ce 矩阵三行：`3.11×websockets==15.0.1`、`3.11×websockets(latest)`、`3.12×websockets(latest)`，`fail-fast: false`，`setup-python` 用 `${{ matrix.python-version }}`，3.12 维 `pytest-targets: "tests/"` 全量。

`gh pr checks 70`（head=44394ce）：三个「单元测试」job **真跑且全 pass**——py3.11/websockets 49s、py3.11/websockets==15.0.1 1m2s、py3.12/websockets 4m33s；非 skip。gate 的 primary/ocr/notify 显示 skipping 是 draft PR 的已知 gate 行为（review-discipline 已载），与本仓 ci.yml 无关。

继承红/新红：PR #70 自身检查全绿，无红可分类。派发时刻主干基线不可用（gh api failed），继承红一项标「未能判定」——本审查未复跑 `test_http_file_tasks.py` 的 3.11 全量红声称（超出本卡红验边界，且下方 finding 2 的改法不依赖其颜色）。

## I1–I6 逐条映射

| 不变式 | 判定 | 证据 |
| --- | --- | --- |
| I1 生产代码无 `asyncio.wait_for`（AST 锁） | 支持 | grep 0 调用；AST 锁 base 红（命中 360/516）、H0 绿；3.11.15 源码核对机制 |
| I2 默认预算连接拒绝 5s 内 `AsrError(connection_lost)` | 支持 | base 120.082s 红原文；H0 3.11/3.12 各 5 连跑全绿 ≤0.21s；新锁不传 deadline_total |
| I3 发送/总时限超时仍 `AsrError(timeout)`，默认路径消息含「自动预算」 | 支持 | `timeout_error()` 消息含「自动预算」；test_sdk_deadline_stage.py:181/201 锁；38 窄测绿；预算公式未动 |
| I4 CI 含 3.11（pin+latest 两维）真跑非 skip，3.12 全量 | 支持 | 矩阵三行；gh pr checks 三个 job pass 带时长 |
| I5 `requires-python>=3.11`，README 无 3.10，无双路径/无 `asyncio.timeout()`，公式不改 | 支持 | pyproject/README grep 全过；公式 base↔head 同行同文 |
| I6 取消向上传播、finally 回收 | 支持 | 两处 `ensure_future + asyncio.wait + finally cancel`；`_wait` 源码无吞取消分支；idle_watch 同构先例 + 收尾断言绿 |

## OCR 4 条 finding 独立重判（对照表：工具标注 / 本仓判定 / P1 两问）

P1 两问口径（review-discipline）：Q1 真实使用方式下会被触发吗（第一问必须实测）？Q2 触发了后果能否接受？两问都过才是 P1。

| # | 工具标注 | 本仓判定 | 两问答案 |
| --- | --- | --- | --- |
| 1 | ci.yml 无 `permissions:` / 无 `timeout-minutes` | **≤P3，backlog，非本卡引入**。base `ci.yml` 同样两者皆无（已 `git show b0818dc` 核对），按「只审本次 diff，存量记 backlog」处置 | Q1：本 PR 不扩大 workflow 权限/超时面，与基线同形态；Q2：与基线同风险，不因此卡阻塞 |
| 2 | 3.11 维写死三文件，漏 `test_sdk_samples_total.py`、`test_sdk_transcode_track.py`，应改 `tests/test_sdk_*.py` | **P2，backlog，建议合并前顺手改**（一行 glob）。实测两文件 3.11 上 **17 passed 全绿**——漏选不是因为它们红；I4 字面已满足（3.11 在矩阵、两维、真跑），但这是 3.11 生产解释器上的 SDK 覆盖缺口 | Q1：本 diff 不触发（改动面不在样本计数/转码路径，那两文件不碰 asyncio）；Q2：未来若出现 3.11-only 回归在那两条路径，3.11 维漏检、但 3.12 全量维仍跑这两文件，后果可接受 → 不过 P1 |
| 3 | `upload` 里 `sender.cancel()` 不 await，且 `sender` 不在外层 `tasks` 集合 | **非缺陷：与既有 `idle_watch` getter 模式同构，且该模式已被接受**（#65/#66，`sdk65/root-cause.md` §4 留有实测证据；`sdk_queue_getter_tasks` 夹具断言 getter 全部被回收）。取消路径无泄漏：超时分支 `sender.cancel()` 后 `AsrError` 上抛，外层 finally 的 `gather` 驱动事件循环把 sender 收尾；38 窄测含多条收尾断言全绿 | Q1：真实路径下不可观测泄漏（cancel + gather 兜底，同 idle_watch 已证形态）；Q2：n/a → 不过 P1 |
| 4 | 新 `sender`/`waiter` 逃出既有 leak 检测夹具 | **≤P2 观察项，backlog**。事实成立：`sdk_queue_getter_tasks` 只盯 `asyncio.Queue.get` 的 ensure_future，`_pending_sdk_tasks` 只按外层协程 qualname 前缀匹配，sender（websockets `send`）/waiter（`Event.wait`）都不在被追踪集。但无真实泄漏机制（finally cancel + 外层 gather），且 H0 全部实测无挂起任务残留 | Q1：无真实触发路径；Q2：n/a → 不过 P1。是否要扩夹具覆盖 sender/waiter 属可选加固，不阻塞 |

## 其他审查记录

- 静默出错扫描（diff 全量）：无 `except: pass/return None`、无 `return_exceptions=True` 新增滥用（既有 `gather(..., return_exceptions=True)` 在 finally 回收属 #65 已接受结构，非本 diff 新增）；新测试无吞断言。
- 熵增维度：本 diff 无新抽象/新状态/新配置项（两处改写与 idle_watch 同构，未抽公共 helper——无第二消费者，符合反过度设计红线）。
- 红验注入确认：两个新测试文件来自 `git show 44394ce:`，grep 留痕；base 命中行号 360/516 与卡面预测一致；venv 未出树、主仓 shebang 无污染。
- 实现 diff 体量 +322/-14：超 Diff-Lines-Target(250)、未超 Hard(600)。
- 未做的事（边界）：未读实现方 report/推理链；未 cherry-pick 实现提交进本卡分支（本分支相对基线只新增本 verdict 文件）；未动实现树；未标 ready/合并/关 issue。

## 判定

PR #70 满足 I1–I6，红验与双解释器实测证据链完整，**无 P1**；1 条 P2（finding 2，一行 glob 可修，可记 backlog 不阻塞）；findings 1/3/4 按上表处置。建议：合并前把 3.11 维 `pytest-targets` 改为 `tests/test_sdk_*.py`，其余可按现状合并。
