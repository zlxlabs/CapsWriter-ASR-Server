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

## 4. getter 只 cancel 不 await —— 实测无收益，故不加

`idle_watch` 每轮新建 `getter = ensure_future(idle_messages.get())`，`finally` 里只 `getter.cancel()`。
是否需要再 `await` 回收？做了注入实验：只删掉 `await asyncio.gather(getter, return_exceptions=True)`
这一行，其余不动，用同步入口子进程在真实 3.11 上跑：

| 变体 | 退出码 | stdout | `Task was destroyed but it is pending!` 计数 |
| --- | --- | --- | --- |
| 带 `await` 回收 | 0 | `{"text": "子进程同步入口。", "task_id_matches": true, "frames": 1}` | 0 |
| 只 `cancel` 不 `await` | 0 | `{"text": "子进程同步入口。", "task_id_matches": true, "frames": 1}` | 0 |

两者完全一致：`_transcribe_connected` / `transcribe_file` 的 `finally` 里的 `gather` 会把事件循环驱动
到 getter 收尾。**结论：不加那次 `await`**。

同时把测试里的 `_pending_sdk_tasks()` 断言范围改回只收 SDK 自己的协程名：先前把 `Queue.get`
也收进去，注入实验显示**它转不红**（恒真断言），按纪律撤掉而不是留着装样子。

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

## 6. 存量另作追踪：`upload` / `deadline_watch` 的同形态隐患

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

**这推翻了本报告早期版本「B/C 吞掉取消后会自终止」的断言**——那次取消已被消费，下一轮并没有待投递的
取消，B/C 与 A 一样会挂死。已在本卡删除该断言。

未决问题（留给后续单）：

- `upload`：形态会挂死，但在本 SDK 里需要「`ws.send()` 完成与 `_transcribe_connected` 收尾的
  `task.cancel()` 同刻」才触发。本次整链复现是**单帧**上传，未覆盖多帧中途收尾，**可达性未证**。
- `deadline_watch`：形态会挂死，但其取消来自 `transcribe_file` 的 `finally`，而 `deadline_changed.set()`
  只在 `set_deadline` 里发生一次、且在建连之前；要同刻需要远端调用在建连瞬间就结束，**可达性未证**。

两者都**未改**，也不在报告里断言它们无害。

## 7. 「同拍完成」不可确定性构造（一个被扬弃的测试构造）

曾构造「upload 与 receive 在同一个事件循环批次里收尾」用来验证裁决顺序：服务端一发出 final，
客户端卡在最后一帧上的 `send` 就立刻失败。**实测该构造不可靠**——upload 是否恰好停在最后一帧的
`ws.send()` 上取决于真实 socket 时序：

| 运行 | 被测代码 | 结果 |
| --- | --- | --- |
| 3.12 修前 | sha `ff476ad7` | 红：`Failed: DID NOT RAISE AsrError`（返回了 Transcript，上传失败被吐掉） |
| 3.11 修前 | sha `ff476ad7` | 红：同上 |
| 3.12 修后 | sha `eccec1a6` | 绿 |
| 3.11 修后 | sha `eccec1a6` | **红**：`Failed: DID NOT RAISE AsrError`——同一场景两种结果 |

因此该用例**不能当断言**，已换成顺序完全确定的 `test_upload_failure_is_not_masked_by_final`
（`send` 一律失败、`recv` 始终挂起），锁的仍是「上传失败不被改判成成功转录」这条契约。
原始日志：`/tmp/sdk65_py311_PREFIX_red.log`、`/tmp/sdk65_py311_POSTFIX_green.log`。
从 3.11 修后那一格能看出：final 先到、upload 仍挂在真实 send 上时，返回 Transcript 是**正确**行为
（此时上传不是失败，是我们自己取消的），不能拿来当缺陷证据。

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
- `upload` / `deadline_watch` 的可达性未证（第 6 节）。
- 3.10 的超时分类缺陷未修（第 5 节）。