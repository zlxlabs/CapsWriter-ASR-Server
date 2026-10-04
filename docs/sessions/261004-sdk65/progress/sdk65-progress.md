# sdk65 进度存档（issue #65：SDK 收到 final 后不返回）

## 里程碑 1：现场核查与有界复现

- 阶段：investigating
- 本段结论：
  - 工作树 `sdk65-rootcause-261004` 位于 base `820c3a2`；`sdk/capswriter_asr/client.py` 的
    SHA256 与 issue 记录的 pin 一致，缺陷代码确实在最新主干上。
  - 用真实 `websockets.serve` 假服务端 + 真实 `ffmpeg` 在本地复现：final 帧在 T+0.135s 到达，
    `transcribe_file` 直到预算到点才抛 `AsrError(timeout)`（脚本 `/tmp/sdk65_repro_e2e.py`）。
  - 版本矩阵：3.10 挂、3.11 挂（= 生产）、3.12 正常。
- 关键决策：
  - 先定位后修复；不预设 `idle_watch` 是根因，只把它当候选。
  - 决定对下游只做只读取证（最多 6 次 `gh`），不写入、不接触生产。
- 否决方案：
  - 直接删 `idle_watch`（前序主脑的候选）：当时无实证支撑，仅登记为待查。
- 下一步唯一动作：把挂死定位到具体的 task / await 点。

## 里程碑 2：根因实证

- 阶段：root-causing
- 本段结论：
  - 根因 = CPython ≤3.11 `asyncio.wait_for` 的吞取消分支
    （`except CancelledError: if fut.done(): return fut.result()`）与 `idle_watch` 的
    「无限循环 + 每轮 wait_for」结构叠加，使 `_transcribe_connected` 的 `finally` gather 永久挂起。
  - 隔离判据：`/tmp/sdk65_min_waitfor_cancel.py`（只留 idle_watch 骨架）3.10/3.11 挂、3.12 通过。
  - 生产解释器定位为 3.11：下游 `VideoTranscriptAPI@ff92a175` 的 `docker/Dockerfile` 首行
    `FROM python:3.11-slim`，`.python-version` = `3.11`；且 issue 记录的是 `AsrError` 而非裸
    `asyncio.TimeoutError`，排除 3.10。
  - 只有 `idle_watch` 会永久挂死：`upload` / `deadline_watch` 吞掉取消后下一步就会遇到仍待投递的
    取消，会自终止。
  - CI 只跑 3.12（`.github/workflows/ci.yml`），所以仓库既有测试从未暴露该缺陷。
- 关键决策：
  - 修复点锁定 `idle_watch` 一处；`upload` / `deadline_watch` 不动（改了也证明不了新行为）。
  - 不用 `sys.version_info` 分叉，不用 `asyncio.timeout`（SDK 声明 `requires-python = ">=3.10"`）。
- 否决方案：
  - 删掉 `idle_watch`：实证表明它是故障承载点，删掉等于删功能。
  - 给 `finally` 的 `gather` 加超时兜底：掩盖症状且会静默漏回收。
- 下一步唯一动作：写 `design.md`，再落最小实现。

## 里程碑 3：设计、最小实现与回归（先红后绿）

- 阶段：implementing
- 本段结论：
  - `design.md` 已落盘（现象 / 机制证据 / 最小方案 / 不变式与检测点 / 非目标 / 已否决方案）。
  - 实现落地两处（均在 `sdk/capswriter_asr/client.py`）：
    1. `idle_watch()` 改用 `asyncio.wait({getter}, timeout=...)` + `finally: getter.cancel()`；
    2. `_transcribe_connected` 的同时完成裁决改为确定性的「final 优先」，其余按
       upload → receive → idle 固定顺序上抛。
  - 回归测试加在 `tests/test_sdk_client.py`（7 个）：final 到达即返回且不依赖服务端关连接、
    同拍失败时 final 优先、idle 超时仍生效、上传期间不被接收预算截断、调用方取消仍上抛并回收、
    同步入口子进程验收、以及一条不装旧语义的对照用例。
  - **红→绿（Python 3.12 + 装回 ≤3.11 的 `wait_for` 语义的 `legacy_wait_for_semantics` fixture）**：
    旧码 3 红（`test_final_result_returns_without_server_close` 断言失败、
    `test_final_wins_when_upload_fails_in_same_tick` 上抛 `connection_lost`、
    `test_sync_entrypoint_returns_transcript_in_subprocess` 子进程挂到 60s 超时），
    新码 7 全绿。
- 关键决策：
  - 3.12 上复现不到该缺陷，因此在测试里用 `_legacy_wait_for`（逐行复刻 CPython ≤3.11 的
    `wait_for`）把生产语义装回去，让 CI 也能守住这条边界；真实 3.11 另有独立运行佐证。
  - 不动 3.10 上 `except TimeoutError` 抓不到 `asyncio.TimeoutError` 的另一处缺陷（见
    `root-cause.md` 第 5 节），它是继承红且与本卡根因不同。
- 否决方案：
  - 只在 3.12 上加 skipif 版本门：CI 唯一版本上会变成永远跳过，等于没锁。
  - 手工伪造一个「假 wait_for」：改用逐行复刻 stdlib 真实实现，避免自造语义偏差。
- 下一步唯一动作：跑 3.10 / 3.11 / 3.12 对照 + 全量 Verify-Command，随后开 draft PR。

## 里程碑 4：跨版本验证与交付

- 阶段：verifying → delivered（draft PR #66，未标 ready、未合并、未关 issue）
- 本段结论（验证矩阵）：

  | 运行 | 解释器 | 结果 |
  | --- | --- | --- |
  | 全量 Verify-Command（`tests/`） | 3.12 | `453 passed, 3 skipped` |
  | Narrow-Verify 连续 5 次 | 3.12 | 每次 `34 passed` |
  | 既有 SDK 套件（修前基线） | 3.11 | `4 failed, 23 passed`（挂满 120s 预算） |
  | 既有 SDK 套件 + 新回归（修后） | 3.11 | `34 passed` |
  | 旧码 + `legacy_wait_for_semantics` | 3.12 | `3 failed, 4 passed`（红） |
  | 新码 + `legacy_wait_for_semantics` | 3.12 | `7 passed`（绿） |
  | SDK 套件（修前基线） | 3.10 | `11 failed, 16 passed, 1 error`（继承红） |
  | SDK 套件 + 新回归（修后） | 3.10 | **待补**（运行中，完成后填入实际输出） |

- 关键决策：
  - 不在本卡修 3.10 的 `except TimeoutError` / `asyncio.TimeoutError` 别名缺陷（属继承红，
    且与本卡根因不同），只实证、归档、上报，另开单。
  - PR 保持 draft，不标 ready、不合并、不关 issue，验收权留给主脑。
- 否决方案：
  - 为了让 3.10 变绿而在本卡顺手改 `except (TimeoutError, asyncio.TimeoutError)`：越出本卡根因，
    会把两个缺陷混在一个 diff 里，反而让主脑难判。
- 下一步唯一动作：等主脑验收 PR #66。

### 里程碑 4 补记：Python 3.10 修后

**待补**：修后 3.10 的实测输出尚未产生，此处不预填结论。