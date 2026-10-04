# 261004-sdk-time-contract 进度存档

会话：`261004-sdk-time-contract`。Card 1 = 消灭 SDK 剩余 `asyncio.wait_for` + Python 地板 3.11（Fixes #67, #68）。
设计真身：`docs/sessions/261004-sdk-time-contract/design.md`（执行器不得重开已锁定决策）。

## 里程碑 1：现场核查与设计落盘

- 阶段：implementing（起步）
- 本段结论：
  - 工作树 `/home/zlx/projects/oss/CapsWriter-Offline-with-AI-worktrees/sdk-time-contract-261004`，分支 `card/sdk-time-contract-261004`，基线 `b0818dc`（PR #66 已合），`git status` 干净，无他人占用。
  - 卡面「已证事实」复核成立：`sdk/capswriter_asr/client.py` 生产路径仅剩两处 `asyncio.wait_for`——`upload` 的 `ws.send(frame)`（约 360 行）与 `deadline_watch` 的 `deadline_changed.wait()`（约 516 行）；`idle_watch` 已是 `asyncio.wait`。
  - `sdk/pyproject.toml` 确为 `requires-python = ">=3.10"`；`.github/workflows/ci.yml` 只有单一 `python-version: "3.12"` 与 `websockets` 两维笛卡尔积，无 Python 版本维。
  - DESIGN-note 已一字不改写入 `docs/sessions/261004-sdk-time-contract/design.md`（唯一偏差：咨询归档路径的本地家目录前缀按 pre-push 公开内容扫描脱敏为 `~/`，未绕过守卫；决策内容零改动）。
- 关键决策与否决：
  - 否决「先改代码后补测试」：卡面要求先红后绿，红必须是行为断言失败。
  - 否决把 #69 自动预算公式并进本卡（同一 `client.py` 串行）。
- 下一步唯一动作：新增默认预算连接拒绝用例与 AST 锁测试，在 3.11 上取到红。

## 里程碑 2：先红已取到

- 阶段：implementing
- 本段结论：
  - AST 锁红（行为断言失败，非 import/syntax）：命中 `sdk/capswriter_asr/client.py:360` 与 `:516`，与卡面已证事实一致。
  - 默认预算连接拒绝红（3.11，uv 装 3.11.15）：`AssertionError: 连接拒绝耗时 120.103s，超过 5s 说明挂到了自动预算`。错误码断言先过（确实是 `connection_lost`），挂的是自动预算 120s——与 `261004-sdk65/design.md` 2.3 节记录的 120.093s 同一现象。
  - 先红后提交（`406befc`），再动生产代码。
- 关键决策与否决：
  - 否决用 shell 超时包住红测：会把它变成“无输出挂死”而非可读断言失败，掩盖真实耗时证据。
- 下一步唯一动作：把 `upload` / `deadline_watch` 两处改成 `asyncio.wait`，同步地板与 CI。

## 里程碑 3：实现 + 地板 3.11 + CI 3.11

- 阶段：verifying
- 本段结论：
  - `upload` 与 `deadline_watch` 改为 `asyncio.ensure_future(...)` + `asyncio.wait({task}, timeout=...)` + `finally: task.cancel()`，与已有 `idle_watch` 同构；超时仍抛 `AsrError("timeout", …)`，默认路径消息仍含「自动预算」（`timeout_error()` 未动）。发送失败走 `sender.result()` 上抛。未抽通用等待辅助函数（无第二消费者）。
  - 绿：同一用例 3.11 上 120.103s → 0.02s；连跑 5 次全绿。3.11 Narrow 37 passed；3.12 Narrow 37 passed；3.12 全量 `tests/` 456 passed / 3 skipped（exit 0）。
  - `sdk/pyproject.toml` `requires-python = ">=3.11"`；`sdk/README.md` 首段改 3.11；`git grep 3.10` 在这两个文件零命中。
  - `ci.yml` 矩阵三行（3.11+pin、3.11+latest、3.12+latest），`setup-python` 用 `${{ matrix.python-version }}`。3.11×pin 实测 37 passed。
- 关键决策与否决：
  - **3.11 维只跑 SDK 三个测试文件，3.12 维跑全量 `tests/`**。理由（实测，非推测）：全量套件在 3.11 上有 2 个红——`tests/test_http_file_tasks.py::test_concurrent_http_commit_respects_budget` 与 `::test_concurrent_mixed_admission_respects_shared_total`；在临时 worktree 的基线 `b0818dc` 上连跑 3 次同样 2 红，判定为**继承红**，与本卡 SDK 改动无因果关系（那两个文件本卡未改）。HTTP 里程碑文件在本卡禁止修改边界内，故不能在本卡修。
  - 该取舍与设计不变式 4「CI 在 Python 3.11 上跑 SDK 相关测试」一致；`ci.yml` 已写明理由，避免后人读成藏红。
  - 否决“把 3.11 维也跑全量然后留着红”：会让本卡 PR 的 gate 永久红，把一个边界外的继承红绑到 bugfix 上。
  - 否决改 `tests/test_http_file_tasks.py` 让它在 3.11 过：既超边界，又会用放宽断言掩盖真实并发原子性问题。
- 下一步唯一动作：小步 commit+push，开 draft PR（`Refs #67, #68`），不标 ready、不合并。