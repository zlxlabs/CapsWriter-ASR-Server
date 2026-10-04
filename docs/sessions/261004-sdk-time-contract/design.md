# DESIGN-note：SDK 时间约束生产路径消灭 `asyncio.wait_for`，Python 地板 3.11

- 会话：`261004-sdk-time-contract`
- issue：#67 / #68（本批 Card 1）；#69 串行后续（Card 2，不并行）
- 咨询：Opus 5 `capswriter-sdk-python-floor-261004`，归档 `/home/zlx/.local/state/agent-config/consult/20261004-190749-claude-opus-09e2bb/`
- 基线：`origin/master` `b0818dc7859d1d8100e42f5c70cb75d34da422f7`（PR #66 已合，`idle_watch` 已改 `asyncio.wait`）

## 目标

在 Python 3.11（下游生产解释器）上，SDK 的上传与总时限监视不再调用会吞取消的 `asyncio.wait_for`；连接失败、取消、超时在秒级内以约定错误码返回，不再挂死。`requires-python` 与 CI 与声明一致：最低 3.11。

## 非目标

- 不 pin 下游 VideoTranscriptAPI，不改生产镜像，不 SSH。
- 不把 Python 地板升到 3.12（那会绑死下游 `python:3.11-slim` 迁移）。
- 不改自动预算公式（#69 / Card 2，等本卡进主干）。
- 不实现 #56 的跨 ffmpeg CI 维；本卡只给 `ci.yml` 加 Python 3.11 维。
- 不改服务端 / proxy / HTTP 里程碑；不与 PR #64/#63/#62 抢文件。
- 不新增 `sys.version_info` 双路径，不用 `asyncio.timeout()`。

## 为什么不是分区 / 删除 / 约定

- **分区**：不能给 3.11 用户发另一份 SDK，也不能让生产路径与测试路径用两套等待原语。缺陷就在公共 `client.py`。
- **删除**：不能删总时限 / idle 发送超时——#52 刚把「无限挂起」收成有界失败。要删的是有缺陷的等待 API，不是时间约束本身。
- **约定**：不能约定「请在 3.12 跑」或「连接失败时请传 `deadline_total=2`」。生产镜像是 3.11，默认预算路径才是用户入口。

## 方案要点与已否决方案

- **要点**：
  1. `sdk/capswriter_asr/client.py` 仅剩的两处 `asyncio.wait_for`（`upload` 约 360 行、`deadline_watch` 约 516 行）改为与现有 `idle_watch` 同构的 `asyncio.wait`；超时仍上抛既有 `AsrError("timeout", …)`。
  2. `sdk/pyproject.toml` `requires-python = ">=3.11"`；`sdk/README.md` 同步。诚实声明，不是靠升解释器让 bug 消失。
  3. CI：3.11 × `websockets==15.0.1`、3.11 × 最新 `websockets`、3.12 × 最新 `websockets`（三 job）。生产解释器必须出现在矩阵里。
  4. 锁 #67 的测试必须走**默认预算**（不传 `deadline_total`）：连接拒绝后 5 秒内 `AsrError.code == "connection_lost"`。显式 `deadline_total` 从不 `deadline_changed.set()`，用它锁不住 #67。
  5. AST 锁：`sdk/capswriter_asr/` 下禁止 `asyncio.wait_for` 调用。与解释器无关。测试夹具里的 `wait_for` 不在此列。
- **已否决**：
  - 现在把地板升到 3.12：下游仍是 `python:3.11-slim`，#65 还没 pin，会把 bugfix 绑死在镜像迁移上。
  - `asyncio.timeout().reschedule()`：3.12 才修了 uncancel 边界，咨询未在 3.11 实证；且会留下第二条等待原语。
  - `sys.version_info` 双路径：两套语义、测试矩阵翻倍，禁止。
  - 为 #68 保留 3.10 专项 `except TimeoutError` 测试：地板 3.11 后 `TimeoutError is asyncio.TimeoutError`，该测试随地板和删除 `wait_for` 的 `except TimeoutError` 一起消失。
  - 用现有 `deadline_total=2` 的连接失败测试充当 #67 锁：结构上走不到 `deadline_watch` 的默认预算重锚定。
  - 把 #69 自动预算并进本卡：同一 `client.py` 禁止并行；公式是 watchdog 不是 SLA，独立串行。
  - 进度续期当根因：服务端 progress 节奏未实证，不在本卡编码。

## 关键不变式

1. [实测] `sdk/capswriter_asr/` 生产代码不含 `asyncio.wait_for` 调用。锁：AST 测试（新建，解析该包全部 `.py`）。
2. [实测] 默认预算下，WebSocket 连接拒绝必须在 5 秒内上抛 `AsrError(code="connection_lost")`，不得挂到 120s 自动预算。锁：`tests/test_sdk_client.py` 新增用例，**禁止**传 `deadline_total`。建议连续 5 次。入口是 `transcribe_file`，不是内部 helper。
3. [实测] `upload` 发送超时、`deadline_watch` 总时限到达，仍上抛 `AsrError(code="timeout")`，消息语义与现网一致（默认路径称「自动预算」）。锁：既有 `tests/test_sdk_deadline_stage.py` + 现有 timeout 用例；若改写导致红，修实现而不是放宽断言。
4. [实测] CI 在 Python 3.11 上跑 SDK 相关测试（含上述两锁）。锁：`.github/workflows/ci.yml` 矩阵含 `python-version: "3.11"` 的 job，且该 job 不是 skip。
5. [实测] 包装元数据与运行时一致：`requires-python = ">=3.11"`。锁：`sdk/pyproject.toml`；README 不得再写 3.10。

## 待验证前提

1. [推断] GitHub hosted 的 3.11 与生产容器小版本可能不同。本卡只锁大版本 3.11 的 `wait_for` 缺陷面；不把 hosted 小版本说成生产精确版本。
2. [推断] `asyncio.wait` 在 3.11 上对 Future 完成+取消同 tick 会向上抛取消（#65 `idle_watch` 已在 3.11 整链实证）。本卡把同一原语扩到 `upload` / `deadline_watch`，用默认预算连接拒绝锁可达路径，不重复 #65 的隔离探针。

## 验收路径

1. 入口：`transcribe_file`（异步；同步入口 `transcribe_file_sync` 不作为本卡新锁，但不得回归挂死）。
2. 步骤：随机端口假服务 + monkeypatch `websockets.connect` 立刻 `OSError("connection refused")`；调用方**不传** `deadline_total`；计时。
3. 预期：<5s 得到 `AsrError(code="connection_lost")`。随后 AST 扫描包内无 `wait_for`；`uv` 3.11 与 3.12 各跑 Narrow-Verify；全量 Verify-Command 在 3.12 绿。

## 拆卡

| 卡 | 范围 | 依赖 |
| --- | --- | --- |
| Card 1 | 消灭剩余 `wait_for` + 地板 3.11 + CI 3.11 + 默认预算连接失败锁 + AST | 无；先派 |
| Card 2 | `_auto_budget(duration)` 纯函数，`duration*4+120` 并留余量；文档写明 watchdog 不是 SLA；超时消息带预算秒数与音频时长 | Card 1 进 `origin/master` 后才能派；禁止并行改 `client.py` |

## 失败可见性

| 失败 | 用户看到 | 禁止 |
| --- | --- | --- |
| 连接拒绝 | `AsrError(code="connection_lost")`，秒级 | 挂到自动预算 120s+ |
| 发送 / 总时限超时 | `AsrError(code="timeout")`，消息区分自动预算 vs `deadline_total`、阶段名 | 裸 `TimeoutError` / 静默返回 |
| 调用方取消 | `CancelledError` 向上传播，finally 回收任务 | `wait_for` 吞取消后死循环 |
| 有人把 `wait_for` 加回来 | AST 测试红 | 只靠 3.12 CI 假绿 |

## 主干基线（派发时刻）

- 主干基线不可用：gh api request failed

- 本次与基线作业名、首个失败步骤名都相同的红属于「继承红」，不是本卡责任。
- 修复报告必须分开列出「继承红」与「新红」；没有基线时将继承红标为未能判定。