# 261004-sdk-time-contract 进度存档

会话：`261004-sdk-time-contract`。Card 1 = 消灭 SDK 剩余 `asyncio.wait_for` + Python 地板 3.11（Fixes #67, #68）。
设计真身：`docs/sessions/261004-sdk-time-contract/design.md`（执行器不得重开已锁定决策）。

## 里程碑 1：现场核查与设计落盘

- 阶段：implementing（起步）
- 本段结论：
  - 工作树 `/home/zlx/projects/oss/CapsWriter-Offline-with-AI-worktrees/sdk-time-contract-261004`，分支 `card/sdk-time-contract-261004`，基线 `b0818dc`（PR #66 已合），`git status` 干净，无他人占用。
  - 卡面「已证事实」复核成立：`sdk/capswriter_asr/client.py` 生产路径仅剩两处 `asyncio.wait_for`——`upload` 的 `ws.send(frame)`（约 360 行）与 `deadline_watch` 的 `deadline_changed.wait()`（约 516 行）；`idle_watch` 已是 `asyncio.wait`。
  - `sdk/pyproject.toml` 确为 `requires-python = ">=3.10"`；`.github/workflows/ci.yml` 只有单一 `python-version: "3.12"` 与 `websockets` 两维笛卡尔积，无 Python 版本维。
  - DESIGN-note 已一字不改写入 `docs/sessions/261004-sdk-time-contract/design.md`。
- 关键决策与否决：
  - 否决「先改代码后补测试」：卡面要求先红后绿，红必须是行为断言失败。
  - 否决把 #69 自动预算公式并进本卡（同一 `client.py` 串行）。
- 下一步唯一动作：新增默认预算连接拒绝用例与 AST 锁测试，在 3.11 上取到红。