# SDK 收到 final 后不返回（issue #65）——根因与最小修复设计

- 派发：`dlg-20261004-044541-f474be` / `dlg-20261004-061926-9968e0`
- issue：<https://github.com/zlxlabs/CapsWriter-ASR-Server/issues/65>
- 分支：`card/sdk65-rootcause-261004`；Base commit：`820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2`
- 阶段：根因已实证，最小实现已落地

## 1. 现象

生产一次 `transcribe_file_sync` 调用：T+0.089 单帧 `is_final=true` 发送成功，T+0.257 底层
`recv` 收到同 `task_id` 的 `type=result`/`is_final=true`，T+120.152 才以 `AsrError(code=timeout)`
结束，`Transcript` 始终未返回。

**生产解释器的确定程度**：下游 `VideoTranscriptAPI@ff92a175` 的 `docker/Dockerfile` 首行为
`FROM python:3.11-slim`，仓库根 `.python-version` 为 `3.11`——这是**构建线索**，证明生产大次版本
为 3.11。本机使用的具体小版本（3.11.15 / 3.11.16）**不等于**生产小版本，容器内的实际
`python --version` 未取证。任何结论都不得把小版本说成生产精确版本。

## 2. 机制证据

### 2.1 隔离判据（先证明机制，再看整链）

`/tmp/sdk65_min_waitfor_cancel.py`：只保留 `idle_watch` 骨架（`Queue(maxsize=1)` + `while True` +
`wait_for`），用 `shield` + 2s 硬上界判定 watcher 是否还能结束。

```
py3.10: HANG 复现 —— wait_for 吞掉 cancel，watcher 永不完成      (exit=3)
py3.11: HANG 复现 —— wait_for 吞掉 cancel，watcher 永不完成      (exit=3)
py3.12: cancel 正确传播                                          (exit=0)
```

判据自检：把 `put_nowait` 与 `cancel` 拆到不同 tick 后，3.10/3.11 立刻正常结束——红由「同刻」触发，
不是脚本恒红。

### 2.2 整链 A/B 对照（真实解释器 + 真实 websockets + 真实 ffmpeg）

`/tmp/sdk65_repro_e2e.py`：随机端口 `websockets.serve` + 真实 `/health` + 真实 `ffmpeg` 转码，单帧
`is_final=true`，服务端回完 final 后**保持连接打开**，按实际收到的 `task_id` 构造回帧。外层
`HARD_DEADLINE=8` 硬截止，shell 再套 `timeout 45`。被测代码用 `SDK_PATH` 指定，输出带
`client_sha256` 自证是哪份代码（`ff476ad7…` = issue pin 的原始 client.py，`eccec1a6…` = 修复后）。

| 解释器 | 修前（sha `ff476ad7`） | 修后（sha `eccec1a6`） |
| --- | --- | --- |
| 3.10 | `RAISED: asyncio.exceptions.TimeoutError`，final@0.201s，耗时 6.004s，exit=4 | `OK` final@0.097s，耗时 0.098s，exit=0 |
| **3.11** | `TIMEOUT_AFTER_FINAL: AsrError(code=timeout)`，final@0.089s，耗时 6.007s，exit=3 | `OK` final@0.100s，耗时 0.101s，exit=0 |
| 3.12 | `OK` final@0.103s，耗时 0.104s，exit=0 | `OK` exit=0 |

（3.10 修前那一格同时暴露了第 5 节的继承缺陷：`except TimeoutError` 抓不到
`asyncio.TimeoutError`，抛的是裸异常而非约定的 `AsrError`。）

服务端主动关连接（`--close-after-final`）时 3.11 修前同样复现——**该缺陷与「服务端是否关连接」无关**。

### 2.3 三种 `wait_for` 形态的真实结局（推翻早期推断）

早期版本在本文件断言「`upload` / `deadline_watch` 吞掉取消后会遇到仍待投递的取消，因而自终止」。
**该断言不成立且自相矛盾**：取消被吞的那一次已经把 `_must_cancel` 消费掉了，下一轮并没有待投递的
取消。真实解释器上的有界测量（`/tmp/sdk65_shapes_measure.py`，每形态 `shield` + 2s 上界）：

```
python=3.10
  A_idle_watch(队列+死循环): HANG 挂死
  B_upload(第1/3帧被吞)  : HANG 挂死
  C_deadline_watch(事件)  : HANG 挂死
python=3.11
  A_idle_watch(队列+死循环): HANG 挂死
  B_upload(第1/3帧被吞)  : HANG 挂死
  C_deadline_watch(事件)  : HANG 挂死
python=3.12
  A_idle_watch(队列+死循环): OK 取消已传播
  B_upload(第1/3帧被吞)  : OK 取消已传播
  C_deadline_watch(事件)  : OK 取消已传播
```

即：**隔离形态在 ≤3.11 上都会挂死**。这证明这些 `wait_for` 的取消语义风险，不单独证明每条真实
SDK 调用都会永久挂起。

- `idle_watch`：已在整链上实证可达并复现（2.2），本卡修它。
- `upload` / `deadline_watch`：独立审查在真实 SDK 公共调用路径上确认取消竞态可达，观察到的是有限响应
  延迟：3.11.15 上调用方取消时的 `deadline_watch` 首次未在 300ms 内结束；发送 Future 同拍取消耗时
  0.252s（`idle_timeout=0.25`），之后启动下一帧 send 并关闭连接。相同发送探针在 3.12.3 为 0.001s。
- 本轮 3.11.15 整文件首跑中，连接拒绝映射用例用了默认预算并耗时 120.093s；单测复跑 120.09s，
  改成显式 2s 预算后同断言 0.07s 通过。第二轮独立复核（`reviews/independent-review2-verdict.md`）已把该
  归因升级为 async Task 栈级实证：默认预算 120.145s 后正确交付 `AsrError(connection_lost)`；t+2s 时
  `transcribe_file` 停在 client.py:538 `gather`，`deadline_watch` 停在 client.py:516
  `wait_for(deadline_changed.wait())`，`cancelling=1`。用例已设显式短预算，只验证连接错误映射。
- 最终 SDK 任务和连接都已收尾；未观察到错误结果、数据损坏或崩溃。这条外部取消路径与 #65 final 已收到后
  `idle_watch` 永久挂起的主缺陷不同。按 `internal` 风险档判为 **P2，接受本轮不修**，不新增防御逻辑；
  见 `root-cause.md` 第 6 节和 `reviews/independent-review1-verdict.md`。

## 3. 最小方案

只改 `sdk/capswriter_asr/client.py` 两处：

### 3.1 `idle_watch()`：带超时的等待不再走 `wait_for`

```python
getter = asyncio.ensure_future(idle_messages.get())
try:
    done, _ = await asyncio.wait({getter}, timeout=idle_timeout)
    if not done:
        raise AsrError("timeout", "上传结束后等待服务端消息超时")
finally:
    getter.cancel()
```

`asyncio.wait` 的内部 `_wait` 没有「`fut.done()` 就返回结果」的分支，取消一定向上抛。语义等价：
令牌到达重置 idle 计时，`idle_timeout` 内无消息仍抛同样的 `AsrError(code="timeout")` 与同样的中文消息。

**关于 `getter.cancel()` 后要不要再 `await` 回收**：做过注入实验（把 `await gather(...)` 那行删掉，
其余不动），用同步入口子进程在真实 3.11 上跑，`exit` 与 stderr 完全一致，`Task was destroyed but
it is pending!` 计数为 0。另有 `sdk_queue_getter_tasks` fixture 按 `Queue.get` 代码对象和 SDK `client.py`
调用来源保存真实 getter Task，在 final 返回、服务端 error、调用方取消后断言集合非空且任务均 `done`。
单独去掉 `getter.cancel()` 的取消路径变异使这条断言明确转红。因此保留现有 cancel，不增加没有可观察
收益的 `await gather(getter)`。

### 3.2 同时完成的裁决：先上抛异常，再谈成功

```python
for task in ordered:          # ordered = (upload_task, receive_task, idle_task)
    if task not in done:
        continue
    if task.cancelled():
        raise asyncio.CancelledError
    error = task.exception()
    if error is not None:
        raise error
if receive_task in done:
    return receive_task.result()
tasks.difference_update(done)
```

原实现 `for task in done: task.result()` 遍历 `set`，同时完成多个任务时上抛哪一个取决于哈希顺序。
新实现只做一件事：**把这个不确定性变成确定的**，且保持原契约——**任何一个已完成子任务的异常都优先
上抛**（上传失败不能因为之后收到了 final 就被改判成成功）。只有全部无异常时才返回 `Transcript`。

**同轮场景的确定性屏障**：`test_upload_failure_is_not_masked_by_final_when_both_tasks_done` 让 fake server
先收到 SDK 实际序列化帧，再按帧内 UUID 回合法 final；send 包装器等 `_receive` 真正解析 final 后才抛
`OSError`。测试保留 SDK 创建的 upload Task 与接收 Task 身份，测试用 `asyncio.wait` 包装器等两者实际结束后
一次性把这两个已完成 Task 交给裁决逻辑，断言同一 `done` 集合同时含两者。它验证混合终态的裁决，不宣称
自然 socket 时序必然同拍。把错误优先逻辑变异成 final 优先后，该测试产生明确 `AssertionError`。

**慢上传屏障**：`test_receive_idle_budget_does_not_fire_during_slow_upload` 发五帧、每次 send 延迟 0.5s、
`idle_timeout=1s`。第四帧已到服务端、最终帧仍在屏障上时，总上传已超过 idle 预算；测试断言调用仍活着、
SDK 没收到消息、idle getter 尚未创建。放行最后一帧后服务端保持静默，断言上传完成后才启动 idle 并抛
`AsrError(code="timeout")`。把 `await upload_done.wait()` 单独移除后，用例以 `AssertionError` 转红；日志
见 `/tmp/sdk65_idle_before_upload_done_red_20261004_dlg-20261004-074109-52b55e.log`。

### 已否决方案

| 方案 | 否决理由 |
| --- | --- |
| 把 `idle_watch` 删掉 | 删掉后接收侧就没有计时了：`_receive` 变成无界 `recv()`，接收侧 idle 预算消失，而「上传结束后长时间无消息」正是要检测的情况。正确的删法是**把计时归回 `_receive`**（在 recv 循环里按最后一条消息的时间判超时），保留上传后 idle 语义——那是另一个实现，不是本卡的最小改动 |
| 三处 `wait_for` 一起换成 `asyncio.wait` | 独立审查已确认外部取消响应延迟路径真实可达，但判为 P2 并接受本轮不修；本轮任务只收紧测试契约与披露，不扩大到生产机制改动 |
| 给 `finally` 的 `gather` 加超时兜底 | 掩盖症状；挂死后仍要等超时，还会静默漏回收 |
| 用 `sys.version_info` 分叉 | 把解释器差异扩散进业务代码；`asyncio.wait` 写法各版本语义一致 |
| 用 `asyncio.timeout`（3.11+） | SDK 声明 `requires-python = ">=3.10"`，3.10 无此 API |
| `getter.cancel()` 后补 `await` 回收 | 同步子进程注入实验无可观察收益；本轮直接追踪 Task 身份证明当前 cancel 后能 done，故不加 |

## 4. 不变式与检测点

| # | 不变式 | 锁它的测试 |
| --- | --- | --- |
| I1 | 收到合法 final 后立即返回正确 `Transcript`，**不依赖服务端关连接**，不遗留 SDK 任务 | `test_final_result_returns_without_server_close`（3.11 真实解释器上旧码红、修后绿） |
| I2 | `_transcribe_connected` 收尾不无限等待；真实 getter Task 在终态已完成 | final 返回、server error、调用方取消用例追踪非空 Task 身份并断言 `done`；final 主路径另有 10s 上界 |
| I3 | 上传结束后真的没有消息，仍按 `idle_timeout` 抛 `AsrError(code="timeout")` | `test_idle_timeout_still_fires_after_upload` |
| I4 | 服务端 `error`、发送失败、总预算超时、调用方取消仍按原契约上抛并回收 | 既有 `test_server_error_code_and_retryable_are_preserved` / `test_blocked_send_uses_idle_timeout` / `test_total_deadline_expires_despite_continuous_progress` / `test_close_without_error_frame_maps_to_connection_lost` + 新增 `test_caller_cancellation_propagates_and_reclaims` |
| I5 | 同一 done 集合中的合法 final 不掩盖 send 异常 | `test_upload_failure_is_not_masked_by_final_when_both_tasks_done`；屏障断言真实 upload/receive Task 同轮完成 |
| I6 | 上传耗时远超 idle 预算期间不提前终止；上传结束且无消息后 idle 生效 | `test_receive_idle_budget_does_not_fire_during_slow_upload`；五帧每帧 send 均小于 idle timeout，总上传大于 1.8 倍预算 |
| I7 | 跨序列化契约：fake server 只按**实际收到的帧**回 final（同 `task_id`、帧顺序、`is_final`、`samples_total`） | I1/I6 两例内的 `frames` 断言 |
| I8 | `transcribe_file_sync` 走独立进程时同样及时返回 | `test_sync_entrypoint_returns_transcript_in_subprocess` |

## 5. 非目标

- 不动服务端 / proxy / 配置 / 依赖 / CI workflow。
- 不动 `VideoTranscriptAPI` 或任何他仓（只读查证 Dockerfile 与 `.python-version`，4 次 `gh` 请求）。
- 不推进本仓 HTTP 里程碑。
- 不修 3.10 上 `except TimeoutError` 抓不到 `asyncio.TimeoutError` 的继承缺陷（`root-cause.md` 第 5 节）。
- 本轮不修独立审查确认的外部取消响应延迟（P2，接受不修，见第 2.3 与 `root-cause.md` 第 6 节）；不将其描述为不可达。
- 不宣称生产已修复：本卡只交付 SDK 侧代码与本地回归，生产升级与端到端验收由下游执行。
