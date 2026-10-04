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

## 里程碑 4：复核纠偏（本轮）

- 阶段：reviewing → fixing
- 本段结论：
  - 撤回上一轮的「final 优先」裁决：它会把同轮的上传失败一起吞掉，与原卡「不丢上传失败」相悖。
    改为「按 upload → receive → idle 固定顺序先上抛任一已完成子任务的异常，全部无异常才返回」，
    只把 `set` 遍历顺序的不确定性变成确定的，不改语义。
  - 上一轮写进 design 的「upload/deadline_watch 吞取消后会自终止」**不成立且自相矛盾**（取消已被
    消费，下一轮没有待投递的取消）。真实解释器三形态有界测量推翻该断言：3.10/3.11 全部挂死，
    3.12 全部正常。已删除该断言，后两者改记为「可达性未证、存量另作追踪」。
  - getter 只 cancel 不 await：注入实验（只删那一行）证明无收益，两侧退出码与 stderr 完全一致、
    destroyed-pending 均为 0，不加那次 await；测试里收进 `Queue.get` 的断言转不红（恒真），撤掉。
  - 纠正两处曲解：生产版本只写「3.11 大次版本构建线索」，不把本机小版本当生产精确版本；
    「删除 idle_watch」写明是把计时归回 `_receive`、保留上传后 idle 语义，不是删掉超时能力。
  - 定位并归档卡面 Narrow-Verify 退出码 2：命令依赖清单漏了 `soundfile`，`tests/test_sdk_client.py`
    顶层 import 它 → 收集期报错 → `Interrupted: 1 error during collection` → 退出 2。
    用 base commit 的测试文件复现同样退出 2，判定为**继承问题**。
  - 修掉自己新加的两处会飘的测试：「同拍完成」构造换成顺序确定的版本；同步入口子进程的
    handler 补上 30s 上界（原先无上限，外层取消时 `Server.__aexit__` 会把它等穿，子进程的
    20s 上界形同虚设），形成 30/45/90 三层硬截止。
- 关键决策：
  - 模拟旧 stdlib 的 fixture 保留（让 3.12 CI 守住生产才有的边界），但**不再拿它当唯一证据**：
    真实 3.11 的修前修后对照才是主证据。
  - 未修 3.10 的 `TimeoutError` 别名缺陷、未修 `upload`/`deadline_watch` 同形态隐患，按卡面另作追踪。
- 否决方案：
  - 保留「同拍」测试并标 xfail：会飘的用例即使标了也会污染信号，不如换成确定性的。
  - 给 getter 补 await：注入实验已证无收益。
- 下一步唯一动作：push、开/更新 draft PR、写完整回执。

## 里程碑 5：最终验证与交付

- 阶段：verifying → delivered
- 本段结论（全部为实际退出码）：

  | 运行 | 解释器 | 结果 |
  | --- | --- | --- |
  | 修前 A/B（真实解释器 + 真实 websockets + 真实 ffmpeg） | 3.10 / 3.11 / 3.12 | 3.10 exit=4（裸 `asyncio.TimeoutError`）、3.11 exit=3（`AsrError(timeout)`）、3.12 exit=0 |
  | 修后 A/B（同脚本同输入） | 3.10 / 3.11 / 3.12 | 全部 exit=0（`OK`，耗时 0.098/0.101/0.100s） |
  | 修前 pytest（真实 3.11，新回归） | 3.11 | `4 failed, 24 deselected`，全部是断言失败 |
  | 修后 pytest 竞态窄测 ×5 | 3.11 | 5 次全部 `7 passed` |
  | 修后 pytest 竞态窄测 ×5（与全量并发） | 3.12 | 5 次全部 `7 passed` |
  | 窄测整文件（补齐 soundfile 依赖后） | 3.12 | `34 passed`，EXIT=0 |
  | 全量 Verify-Command | 3.12 | `453 passed, 3 skipped`，EXIT=0 |
  | 卡面 Narrow-Verify 原文 | 3.12 | `EXIT=2`（缺 soundfile，继承问题，见 root-cause.md 第 8 节） |

- 关键决策 / 否决方案：见里程碑 4；本轮无新增否决。
- 下一步唯一动作：交主脑验收 PR #66（保持 draft）。
