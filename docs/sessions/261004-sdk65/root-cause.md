# issue #65 根因报告：SDK 收到 final 后不返回

- 派发：`dlg-20261004-044541-f474be` / `dlg-20261004-061926-9968e0`
- 分支：`card/sdk65-rootcause-261004`；Base commit：`820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2`
- 结论：**根因已实证，最小修复已落地，真实 3.10 / 3.11 / 3.12 上做了修前修后对照。**

## 1. 一句话根因

`client.py` 的 `idle_watch()` 用「无限循环 + 每轮 `asyncio.wait_for(queue.get())`」实现接收侧 idle
超时。CPython **≤3.11** 的 `asyncio.wait_for` 有一个吞取消分支——被等待对象在同一 tick 已完成、
外层同刻收到 `task.cancel()` 时，它返回结果而不是传播 `CancelledError`。`final` 到达恰好制造这个
同刻条件：取消被吞后 `idle_watch` 进入下一轮**全新**等待，而那次取消已被消费，于是永久阻塞；
`_transcribe_connected` 的 `finally` 里 `await asyncio.gather(...)` 等的就是它，`_operation` 不返回，
直到外层预算到点抛 `AsrError(timeout)`。Python 3.12 把 `wait_for` 改写成 `asyncio.timeout`，删掉了该
分支——所以只在 ≤3.11 复现；本仓 CI 只跑 3.12（`.github/workflows/ci.yml` 仅 `python-version: "3.12"`），
既有测试因此从未暴露。

## 2. 被测代码自证

A/B 对照用 `SDK_PATH` 指向两份 `capswriter_asr`，每份输出都带 `client_sha256`：

```
ff476ad7cd40401b7ed77c7606cb4fc14dc3d529043c29c4714b199c13423cdf  ← 修前
    与 issue #65 正文记录的运行 client.py SHA256 逐字一致（= pin 858c6b9 的原始代码）
eccec1a69b81c4a2360d33e15f0ddb8adffb85725dc93d41f8e3150a0863f6c7  ← 修后
```

## 3. 修前/修后对照（真实解释器，硬截止）

脚本 `/tmp/sdk65_repro_e2e.py`（真实 `websockets.serve` 随机端口 + 真实 `/health` + 真实 `ffmpeg`
转码，单帧 `is_final=true`，回完 final **保持连接打开**，按实际收到的 `task_id` 回帧），
`HARD_DEADLINE=8`，shell 再套 `timeout 45`。原始输出：

| 解释器 | 修前 | 修后 |
| --- | --- | --- |
| 3.10 | `RAISED: asyncio.exceptions.TimeoutError`，final@0.201s，elapsed 6.004s，exit=4 | `OK` final@0.097s，elapsed 0.098s，exit=0 |
| **3.11** | `TIMEOUT_AFTER_FINAL: AsrError(code=timeout)`，final@0.089s，elapsed 6.007s，exit=3 | `OK` final@0.100s，elapsed 0.101s，exit=0 |
| 3.12 | `OK` final@0.103s，elapsed 0.104s，exit=0 | `OK` exit=0 |

原始日志：`/tmp/sdk65_ab_prefix_3.10.log`、`/tmp/sdk65_ab_prefix_3.11.log`、`/tmp/sdk65_ab_prefix_3.12.log`、
`/tmp/sdk65_ab_postfix_3.10.log`、`/tmp/sdk65_ab_postfix_3.11.log`、`/tmp/sdk65_ab_postfix_3.12.log`；
退出码汇总 `/tmp/sdk65_ab_exitcodes.txt`。

3.10 修前那一格同时暴露第 5 节的继承缺陷（抛的是裸 `asyncio.TimeoutError`，不是约定的 `AsrError`）。

## 4. getter 清理：保留真实 Task 身份验证，不增加 await

`idle_watch` 每轮新建 `getter = ensure_future(idle_messages.get())`，`finally` 里只 `getter.cancel()`。
是否需要再 `await` 回收？做了注入实验：只删掉 `await asyncio.gather(getter, return_exceptions=True)`
这一行，其余不动，用同步入口子进程在真实 3.11 上跑：

| 变体 | 退出码 | stdout | `Task was destroyed but it is pending!` 计数 |
| --- | --- | --- | --- |
| 带 `await` 回收 | 0 | `{"text": "子进程同步入口。", "task_id_matches": true, "frames": 1}` | 0 |
| 只 `cancel` 不 `await` | 0 | `{"text": "子进程同步入口。", "task_id_matches": true, "frames": 1}` | 0 |

两者完全一致：`_transcribe_connected` / `transcribe_file` 的 `finally` 里的 `gather` 会把事件循环驱动
到 getter 收尾。**结论：不加那次 `await`**。

前一轮把 `Queue.get` 按协程名塞进 `_pending_sdk_tasks()`，实际注入时断言转不红，已撤掉。
本轮改为包住 `asyncio.ensure_future`：仅当传入协程的代码对象是 `asyncio.Queue.get`，且调用来源
是 SDK 的 `client.py` 时，保存该次调用返回的真实 `Task`。final 正常返回、服务端 error 和调用方取消
三条路径都先等到该 Task 已创建，再断言追踪集合非空且每个 Task 已结束。把 `getter.cancel()` 单独删掉的
临时变异在取消路径明确失败：`AssertionError` 显示捕获到的 `Queue.get` Task 仍为 pending。

这验证的是当前 `cancel()` 已执行后 getter 能收尾；它不主张额外 `await gather(getter)` 有收益，前一节
注入实验仍说明本地同步入口没有可观察差异，因此不增加那次 await。

## 5. 继承红：3.10 上 `except TimeoutError` 抓不到 `asyncio.TimeoutError`（**本卡未修**）

3.10 里 `asyncio.TimeoutError` 尚未是内建 `TimeoutError` 的别名（3.11 才合并，实测
`asyncio.TimeoutError is TimeoutError` 在 3.10 为 `False`）。`client.py` 里三处 `except TimeoutError`
（`upload` / `idle_watch` / `deadline_watch`）因此抓不到它，所有超时路径在 3.10 上抛裸
`asyncio.exceptions.TimeoutError` 而非约定的 `AsrError(code="timeout")`。

SDK 套件在 3.10 上的有界对照（同一命令，只换被测代码）：

| 被测代码 | 结果 |
| --- | --- |
| 修前（sha `ff476ad7`） | `11 failed, 16 passed, 1 error in 642.78s` |
| 修后（sha `eccec1a6`） | `5 failed, 29 passed in 134.28s` |

修后剩余 5 个失败全部属于本缺陷（`test_blocked_send_uses_idle_timeout`、
`test_total_deadline_expires_despite_continuous_progress`、`test_explicit_deadline_kills_local_ffmpeg`、
`test_remote_stage_timeout_message`、`test_local_and_remote_timeout_messages_are_distinguishable`），
与 #65 的「收到 final 后不返回」不是同一根因（本卡根因在 3.11 上成立，而 3.11 的别名是好的），
因此**本卡不动**。建议单独收敛「SDK 声明 `requires-python >= 3.10` 但 CI 只跑 3.12」这个缺口。

## 6. 外部取消响应延迟：与 #65 final 收尾主缺陷分开记录（P2，接受本轮不修）

`/tmp/sdk65_shapes_measure.py` 在真实解释器上的有界测量（每形态 `shield` + 2s 上界）：

```
python=3.10 / python=3.11
  A_idle_watch(队列+死循环): HANG 挂死
  B_upload(第1/3帧被吞)  : HANG 挂死
  C_deadline_watch(事件)  : HANG 挂死
python=3.12
  A_idle_watch(队列+死循环): OK 取消已传播
  B_upload(第1/3帧被吞)  : OK 取消已传播
  C_deadline_watch(事件)  : OK 取消已传播
```

**这推翻了本报告早期版本「B/C 吞掉取消后会自终止」的断言**：那次取消已被消费，下一轮并没有待投递的
取消。隔离形态证明这些 `wait_for` 存在风险，但不单独证明每条真实调用都会永久挂起。

独立审查在真实 SDK 公共调用路径上确认 `upload` / `deadline_watch` 的取消竞态可达，观测结果为**有限取消
响应延迟**，不是 #65 的 final 已收到后永久卡在 `idle_watch` 收尾：

- Python 3.11.15 上 `deadline_changed` 等待者与 `transcribe_file` 调用方取消落在同一调度窗口，首次取消
  300ms 内未结束；任务快照含 `deadline_watch`（`cancelling=1`）和 `Event.wait`，再次取消后才结束。
- 另一个真实发送 Future 同拍取消探针在 `idle_timeout=0.25` 下耗时 0.252s，随后启动下一帧 send 并关闭
  连接；Python 3.12.3 同一探针耗时 0.001s。
- 最终 SDK 任务和连接均已收尾；没有观察到错误结果被当成功、数据损坏或崩溃。

原始输出：`/tmp/sdk65-review1-boundaries311.log`、`/tmp/sdk65-review1-boundaries312.log`、
`/tmp/sdk65-review1-send-cancel.log`（审查 verdict 见 `reviews/independent-review1-verdict.md`）。按本仓
`internal` 风险档的评审两问，这条路径真实可触发，但当前证据只显示有限响应延迟且最终清理，判为 **P2，
接受本轮不修**。本轮不加防御逻辑；不把该路径写成不可达，也不把它与 #65 final 主缺陷合并为一个
根因。

本轮 3.11.15 首次两文件整测中，`test_websocket_connection_failure_maps_to_connection_lost` 用默认预算耗时
120.093s；单测复跑为 120.09s，设置 `deadline_total=2` 后同一错误映射断言 0.07s 通过。它与 `transcribe_file`
重置远端预算后在 `finally` gather `deadline_watch` 的路径吻合，最可能是该 timer 的取消被 `wait_for` 吞掉后
等到默认预算结束；两次现场都只取得 selector 空等的线程栈，没有拿到 async Task 栈，所以此归因仍是推断，
不能排除 fixture 收尾。用例现显式设 2s，只验证错误映射；独立 review 已记录的公共取消延迟仍按 P2 接受不修。

## 7. 同轮错误与 final：从偶然并发改为屏障证明

早期用例依赖真实 socket 时序让最后一帧 send 与 final 偶然并发；它在 3.12 修前红、3.11 修后绿，不能
稳定保证两个 SDK 子任务进入同一个 `asyncio.wait` 的 `done` 集合，因此不能证明 I4。

`test_upload_failure_is_not_masked_by_final_when_both_tasks_done` 现在使用屏障：

1. fake server 先收到 SDK 实际序列化的 final 帧，保存帧内 `task_id`，再按同 UUID 发合法 final；
2. send 包装器先把原帧实际送到服务端，等 `_receive` 真正解析完 final 后才抛 `OSError`；
3. 测试在任务创建时保存 SDK upload Task 与接收 Task 身份；包装的 `asyncio.wait` 等两者实际结束后一起交给
   裁决逻辑，并断言返回的 `done` 同时包含两者；这是受控的混合终态测试，不声称自然 socket 时序必然同拍；
4. 把错误优先判据单独变异成「先返回 final」，测试以明确 `AssertionError` 转红。

修后 Python 3.12.3：该用例 `1 passed`。final 优先变异红日志：
`/tmp/sdk65_final_priority_red_20261004_dlg-20261004-074109-52b55e.log`。
这条测试证明同轮已有 send 异常时不返回 Transcript；它不把“send 尚未失败、只是客户端在取消它”的情形当成上传错误。

### 慢上传与上传后 idle 的屏障

`test_receive_idle_budget_does_not_fire_during_slow_upload` 用五帧、每次 send 延迟 0.5s、`idle_timeout=1s`。
第四帧实际到达服务端且最后一帧仍被屏障挡住时，已经超过 idle 预算；测试断言调用仍活着、SDK 尚未收到
服务端消息、idle getter 尚未创建。释放最后一帧后，服务端继续保持静默，测试再断言上传后 getter 已创建、
调用以 `AsrError(code="timeout")` 结束，且五次 send 各自仍低于 send timeout。

把 `idle_watch` 中的 `await upload_done.wait()` 单独移除后，屏障用例以 `AssertionError` 转红：上传尚未
抵达最终帧就被 idle 结束。红日志：
`/tmp/sdk65_idle_before_upload_done_red_20261004_dlg-20261004-074109-52b55e.log`。

## 8. 卡面 Narrow-Verify 命令退出码 2 的实际原因（继承问题，非本卡引入）

卡面 Narrow-Verify：

```
uv run --no-project --python 3.12 --with numpy --with websockets --with pytest==9.1.1 \
  --with pytest-asyncio==1.4.0 --with httpx==0.28.1 \
  python -m pytest tests/test_sdk_client.py tests/test_sdk_deadline_stage.py -q -p no:cacheprovider
```

实测 `EXIT=2`，pytest 原文：

```
tests/test_sdk_client.py:21: in <module>
    import soundfile as sf
E   ModuleNotFoundError: No module named 'soundfile'
=========================== short test summary info ============================
ERROR tests/test_sdk_client.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.11s
```

原因：该命令的依赖清单**漏了 `soundfile`**，而 `tests/test_sdk_client.py` 在模块顶层 import 它
（收集阶段就炸 → pytest 报 `Interrupted: 1 error during collection` → 退出码 2，不是 1）。

**继承判定**：把测试文件换回 base commit `820c3a2` 的版本（`git show 820c3a2:tests/test_sdk_client.py`
第 20 行同样是 `import soundfile as sf`）再跑同一条命令，仍是 `EXIT=2`。所以这是**卡面命令本身的缺陷**，
不是本卡引入。补上 `soundfile`（并与 Verify-Command 的依赖对齐）后窄测 `EXIT=0`。

## 9. 生产版本取证（只读，4 次 `gh` 请求）

| 证据 | 来源 | 能证明什么 |
| --- | --- | --- |
| `FROM python:3.11-slim` | `VideoTranscriptAPI@ff92a175` 的 `docker/Dockerfile` 第 1 行 | 生产镜像的**大次版本构建线索**为 3.11 |
| `.python-version` = `3.11` | 同仓根目录 | 开发侧大次版本与之一致 |
| issue 记录的是 `AsrError(code=timeout)` 而非裸 `asyncio.TimeoutError` | issue #65 正文 | 结合第 5 节可排除 3.10 |

**不能证明的**：生产容器内 `python --version` 的具体小版本。本报告出现的 3.11.15 / 3.11.16 都是
本机 uv 解析结果，不得当作生产精确版本。未取证项：生产容器内 `websockets` 的实际小版本。

## 10. 尚未验证的边界

- 生产**尚未**升级到本修复；本卡不接触生产、不部署、不重启、不改配置。
- 未做下游 `VideoTranscriptAPI` 的端到端验收（不在本卡授权范围）。
- Python 3.11.15 公共取消路径存在有限响应延迟，本轮按 P2 接受不修（第 6 节）；这不是 #65 final 收尾主缺陷。
- 3.10 的超时分类缺陷未修（第 5 节）。

## 11. 本轮最终验证

- Python 3.11.15 两文件整测最终 `34 passed in 17.63s`；首跑的 `1 failed, 33 passed in 137.80s` 是新测试把
  `wait_for(ws.send())` 子任务错认作 upload Task，修正身份跟踪后全绿。连接拒绝用例的 120 秒归因限制见第 6 节。
- 同一 7 个 final / 错误 / 取消 / 慢上传关键用例，Python 3.11.15 与 3.12.3 各连续 5 轮全部 `7 passed`。
- Python 3.12.3 全量 `tests/`：`453 passed, 3 skipped, 149 warnings in 222.54s`，EXIT=0；原始日志
  `/tmp/sdk65_py312_full_tests_20261004_074109_52b55e.log`。
- 最终代码树三条变异分别产生行为 `AssertionError`：final 优先、取消路径漏掉 `getter.cancel()`、上传未完先启 idle；
  日志分别为 `/tmp/sdk65_final_priority_red_20261004_dlg-20261004-074109-52b55e.log`、
  `/tmp/sdk65_skip_getter_cancel_red_20261004_dlg-20261004-074109-52b55e.log`、
  `/tmp/sdk65_idle_before_upload_done_red_20261004_dlg-20261004-074109-52b55e.log`。
