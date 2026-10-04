# SDK 收到 final 后不返回（issue #65）——根因与最小修复设计

- 派发：`dlg-20261004-044541-f474be`
- issue：<https://github.com/zlxlabs/CapsWriter-ASR-Server/issues/65>
- 分支：`card/sdk65-rootcause-261004`
- Base commit：`820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2`
- 阶段：根因已实证，进入最小实现

## 1. 现象

生产容器（下游 `VideoTranscriptAPI` commit `ff92a175`，`docker/Dockerfile` 第 1 行
`FROM python:3.11-slim`，仓库根 `.python-version` 同为 `3.11`）里，一次
`transcribe_file_sync` 调用：

| 时刻 | 事件 |
| --- | --- |
| T+0.000 | 调用开始 |
| T+0.089 | 单帧 `is_final=true` 发送成功（`samples_total=88747`） |
| T+0.257 | 底层 `recv` 收到同 `task_id` 的 `type=result`/`is_final=true` |
| T+120.152 | 调用以 `AsrError(code=timeout)` 结束，`Transcript` 始终未返回 |

即：**final 已经到达客户端，调用却不返回，直到自动总预算（120s）到点才以超时收场。**

## 2. 机制证据

### 2.1 版本矩阵（本地有界复现）

同一份代码、同一份输入，只有解释器不同：

| 解释器 | 结果 |
| --- | --- |
| CPython 3.10.21 | 挂住（见 2.4） |
| **CPython 3.11.16（= 生产版本）** | `AsrError(timeout)` @ 6.007s，final 在 0.135s 就已发出 |
| CPython 3.12.14 | 正常返回 @ 0.125s，`Transcript.text` 正确 |

复现脚本：`/tmp/sdk65_repro_e2e.py`（真实 `websockets.serve` 随机端口假服务端、真实
`/health`、真实 `ffmpeg` 转码、单帧 `is_final=true`、回完 final **保持连接打开**）。
命令：

```
uv run --no-project --python 3.11 --with websockets --with numpy --with httpx \
  python -u /tmp/sdk65_repro_e2e.py --budget 6
```

输出（3.11）：`{"verdict": "TIMEOUT_AFTER_FINAL: AsrError(code=timeout)", "python": "3.11",
"websockets": "17.2", "final_sent_at": 0.135, "elapsed": 6.007, "frames": 1,
"frame_is_final": [true], "samples_total_on_final": 88000}`

同一缺陷在本仓既有测试上也成立：`tests/test_sdk_client.py::test_flac_upload_matches_transcode_and_v2_frames`
在 3.10 上失败（挂满 120s 自动预算后抛错），在 3.12 上通过 —— 即 CI 只跑 3.12，所以从未暴露。

### 2.2 根因

`client.py` 的 `idle_watch()` 用**无限循环 + 每轮 `asyncio.wait_for(idle_messages.get())`**
实现「上传结束后 idle 超时」：

```python
async def idle_watch() -> None:
    await upload_done.wait()
    while True:
        try:
            await asyncio.wait_for(idle_messages.get(), timeout=idle_timeout)
        except TimeoutError as exc:
            raise AsrError("timeout", "上传结束后等待服务端消息超时") from exc
```

而 `_receive()` 每收到一条消息（含 final）就 `put_nowait` 一个令牌唤醒它。于是 final 到达时
**令牌到达与 `_transcribe_connected` 收尾的 `task.cancel()` 落在同一个事件循环 tick**：

1. `_receive` 收到 final → `idle_messages.put_nowait(None)`（`getter` future 被 `set_result`，
   `idle_task` 的 `__wakeup` 被 `call_soon` 排入就绪队列）→ 返回 `Transcript`。
2. `receive_task` 完成 → `_transcribe_connected` 的 `asyncio.wait(FIRST_COMPLETED)` 返回 →
   `return result` → 进入 `finally`：`task.cancel()` 取消 `idle_task`。此时 `idle_task` 已排入
   就绪队列但尚未恢复运行，`Task.cancel()` 无法取消那个**已经完成**的 `getter` future，
   只能置 `_must_cancel=True`。
3. 下一个 tick，`Task.__step` 把 `CancelledError` 抛进 `wait_for` 内部的 `await waiter`。
   **Python ≤3.11 的 `asyncio.wait_for` 在这里有一个吞取消分支**（`asyncio/tasks.py`）：

   ```python
   try:
       await waiter
   except exceptions.CancelledError:
       if fut.done():
           return fut.result()      # ← 取消被吞，wait_for 当作正常返回
       ...
   ```

   （3.10.21 与 3.11.16 的 `inspect.getsource(asyncio.wait_for)` 均含此分支；3.12 已改写成
   `async with timeouts.timeout(timeout): return await fut`，没有该分支。）
4. `wait_for` 返回令牌 → `idle_watch` 进入 `while True` 的下一轮 → 调用**全新的**
   `asyncio.wait_for(...)`。第 3 步那次取消已被消费（`_must_cancel` 已清），新的一轮没有任何
   待投递的取消，于是永久阻塞在空队列上。**`idle_task` 再也不会结束。**
5. `_transcribe_connected` 的 `finally` 里 `await asyncio.gather(*tasks, return_exceptions=True)`
   等的就是这个 `idle_task` → 永久挂起 → `_operation` 不返回 → `operation_task` 不完成 →
   `deadline_watch` 到 120s 自动预算 → `AsrError("timeout", ...)`。

### 2.3 为什么只有 `idle_watch` 会永久挂死

`upload()`（`wait_for(ws.send(...))`）和 `deadline_watch()`（`wait_for(deadline_changed.wait())`）
同样用了 `wait_for`，同样可能被吞取消，但它们吞掉之后**下一步就会遇到仍待投递的取消**，
因此下一轮 `await` 立刻收到 `CancelledError` 并正常退出，只是多发一帧/多转一圈——
**不会挂死**。`idle_watch` 的「下一步」恰好是另一个不带任何待投递取消的阻塞等待，所以只有它
变成永久挂起。这一点决定了修复必须落在 `idle_watch`，而不是把三处 `wait_for` 一起改。

### 2.4 隔离判据（不依赖任何整链猜测）

`/tmp/sdk65_min_waitfor_cancel.py` 只保留 `idle_watch` 的骨架（队列 + `while True` + `wait_for`），
用 `asyncio.shield` + 2s 上界判定「watcher 是否还能结束」：

```
py3.10: HANG 复现 —— wait_for 吞掉 cancel，watcher 永不完成   (exit=3)
py3.11: HANG 复现 —— wait_for 吞掉 cancel，watcher 永不完成   (exit=3)
py3.12: cancel 正确传播                                        (exit=0)
```

判据自检：把 `put_nowait` 与 `cancel` 拆到不同 tick（不制造同刻竞态）时，3.10/3.11 同样立刻结束，
说明红确实由「同刻」触发，而不是脚本恒红。

## 3. 最小方案

只改 `sdk/capswriter_asr/client.py` 的 `idle_watch()`，把「带超时的等待」从
`asyncio.wait_for` 换成 `asyncio.wait`：

```python
async def idle_watch() -> None:
    await upload_done.wait()
    while True:
        # 用 asyncio.wait 而不是 asyncio.wait_for：后者在 Python ≤3.11 上会在
        # 「令牌到达与 task.cancel() 同刻」时吞掉取消（asyncio/tasks.py 的
        # `except CancelledError: if fut.done(): return fut.result()`），
        # 使本函数进入下一轮无限等待、_transcribe_connected 的 finally gather
        # 永久挂起（issue #65）。asyncio.wait 的 _wait 没有这个分支。
        getter = asyncio.ensure_future(idle_messages.get())
        try:
            done, _ = await asyncio.wait({getter}, timeout=idle_timeout)
            if not done:
                raise AsrError("timeout", "上传结束后等待服务端消息超时")
        finally:
            getter.cancel()
```

- 语义完全等价：令牌到达即重置 idle 计时；`idle_timeout` 内无消息仍抛同样的
  `AsrError(code="timeout")`、同样的中文消息。
- 取消可靠：外层 `task.cancel()` 时 `asyncio.wait` 的 `CancelledError` 直接向上抛，
  `finally` 负责回收 `getter`。
- 不加预算、不加重试、不加 fallback、不引入新框架、不改协议字段。

### 已否决方案

| 方案 | 否决理由 |
| --- | --- |
| 直接删掉 `idle_watch`（前序主脑的候选） | 实证显示它不是「多余代码」而是**故障承载点**；删掉会丢掉「上传结束后长时间无消息」的检测能力，等于删功能，不是修 bug |
| 把 `asyncio.wait_for` 全局换成 `asyncio.wait`（含 `upload`/`deadline_watch`） | 这两处吞取消后自终止，不构成挂死（2.3）；改了也证明不了新行为，属于超范围改动 |
| 给 `finally` 的 `gather` 加超时兜底 | 掩盖症状；一旦挂死仍要等超时，且会静默吞掉未回收任务 |
| 给 SDK 加 `if sys.version_info < (3, 12)` 分支 | 把解释器差异扩散进业务代码；`asyncio.wait` 写法在各版本语义一致，无需分叉 |
| 用 `asyncio.timeout`（3.11+）上下文管理器 | SDK 声明 `requires-python = ">=3.10"`，3.10 没有该 API，会破坏已声明的支持面 |

## 4. 不变式与检测点

| # | 不变式 | 锁它的测试 |
| --- | --- | --- |
| I1 | 收到合法 final 后立即返回正确 `Transcript`，**不依赖服务端关连接** | `test_final_result_returns_without_server_close`（3.11 上旧码红、修后绿） |
| I2 | `_transcribe_connected` 收尾不会无限等待：不留悬挂 task、不留未关闭连接 | 同上 + `asyncio.all_tasks()` 快照断言 |
| I3 | 上传结束后真的没有消息，仍按 `idle_timeout` 抛 `AsrError(code="timeout")` | `test_idle_timeout_still_fires_after_upload` |
| I4 | 服务端 `error` 帧、发送失败、总预算超时、调用方取消仍按原契约上抛并回收 | 既有 `test_server_error_code_and_retryable_are_preserved` / `test_blocked_send_uses_idle_timeout` / `test_total_deadline_expires_despite_continuous_progress` + 新增取消用例 |
| I5 | 发送与接收并行：上传期间不因接收 idle 预算被提前终止，上传完成后 idle 才生效 | `test_receive_idle_budget_waits_for_upload` |
| I6 | 跨序列化契约：fake server 只按**实际收到的帧**回 final（同 `task_id`、单帧、末帧带 `samples_total`） | 新测试内 `frames` 断言 |

## 5. 非目标

- 不动服务端 / proxy / 配置 / 依赖 / CI workflow。
- 不动 `VideoTranscriptAPI` 或任何他仓（只读查证 Dockerfile 与 `.python-version`）。
- 不推进本仓 HTTP 里程碑。
- 不顺手修 3.10 上 `except TimeoutError` 抓不到 `asyncio.TimeoutError` 的另一处缺陷（见
  `root-cause.md` 第 5 节，已实证但不在本卡范围）。
- 不宣称生产已修复：本卡只交付 SDK 侧代码与本地回归，生产升级与端到端验收由下游执行。