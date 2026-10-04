# issue #65 根因报告：SDK 收到 final 后不返回

- 派发：`dlg-20261004-044541-f474be`
- 分支：`card/sdk65-rootcause-261004`
- Base commit：`820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2`
- 结论：**根因已实证，最小修复已落地并在 3.10/3.11/3.12 上对照验证。**

## 1. 一句话根因

`client.py` 的 `idle_watch()` 用「无限循环 + 每轮 `asyncio.wait_for(queue.get())`」实现接收侧
idle 超时。CPython **≤3.11** 的 `asyncio.wait_for` 有一个吞取消分支：当被等待对象在**同一 tick**
已完成、同时外层收到 `task.cancel()` 时，它返回结果而不是传播 `CancelledError`。final 到达恰好
制造这个同刻条件，于是 `idle_watch` 吞掉取消后进入下一轮**全新**等待（那次取消已被消费），
永久阻塞；`_transcribe_connected` 的 `finally` 里 `await asyncio.gather(...)` 等的就是它，
于是 `_operation` 不返回，直到外层 120s 自动预算到点抛 `AsrError(timeout)`。
Python 3.12 把 `wait_for` 改写成 `asyncio.timeout`，删掉了这个分支——所以只在 ≤3.11 复现。

## 2. 生产版本定位（只读证据）

| 证据 | 来源 | 结论 |
| --- | --- | --- |
| issue 记录调用以 `AsrError(code=timeout)` 收场 | issue #65 正文 | 若生产是 3.10，`except TimeoutError` 抓不到 `asyncio.TimeoutError`，调用方会看到裸 `asyncio.TimeoutError`（本地 3.10 实测如此）。**故生产不是 3.10** |
| 3.12 不复现（本地矩阵） | `/tmp/sdk65_repro_e2e.py` | **故生产是 3.11** |
| 下游容器基础镜像 | `VideoTranscriptAPI@ff92a175` 的 `docker/Dockerfile` 第 1 行 `FROM python:3.11-slim`；仓库根 `.python-version` = `3.11` | **直接确认生产解释器为 3.11** |

说明：只对下游做了 4 次只读 `gh` 请求（仓库树、`.python-version`、`docker/` 列表、`Dockerfile`），
未读任何凭据、未读原始生产日志、未写入他仓。issue 中 pin 的下游 commit 就是 `ff92a175`，与本次
读取的 commit 一致。

## 3. 复现证据链

### 3.1 隔离判据（先证明机制，再看整链）

`/tmp/sdk65_min_waitfor_cancel.py`——只保留 `idle_watch` 骨架（`asyncio.Queue(maxsize=1)` +
`while True` + `wait_for`），用 `shield` + 2s 上界判定 watcher 是否还能结束：

```
$ for v in 3.10 3.11 3.12; do uv run --no-project --python $v python /tmp/sdk65_min_waitfor_cancel.py; done
py3.10: HANG 复现 —— wait_for 吞掉 cancel，watcher 永不完成      (exit=3)
py3.11: HANG 复现 —— wait_for 吞掉 cancel，watcher 永不完成      (exit=3)
py3.12: cancel 正确传播                                          (exit=0)
```

判据自检：把 `put_nowait` 与 `cancel` 拆到不同 tick 后，3.10/3.11 立刻正常结束——说明红由
「同刻」触发，不是脚本恒红。

### 3.2 整链复现（真实 websockets 假服务端 + 真实 ffmpeg）

`/tmp/sdk65_repro_e2e.py`：随机端口 `websockets.serve` + 真实 `/health` + 真实 `ffmpeg` 转码，
单帧 `is_final=true`，服务端回 final 后**保持连接打开**，回帧按实际收到的 `task_id` 构造。

```
$ uv run --no-project --python 3.11 --with websockets --with numpy --with httpx \
    python -u /tmp/sdk65_repro_e2e.py --budget 6
{"verdict": "TIMEOUT_AFTER_FINAL: AsrError(code=timeout)", "python": "3.11",
 "websockets": "17.2", "final_sent_at": 0.135, "elapsed": 6.007, "frames": 1,
 "frame_is_final": [true], "samples_total_on_final": 88000}

$ uv run --no-project --python 3.12 ... python -u /tmp/sdk65_repro_e2e.py --budget 6
{"verdict": "OK", "python": "3.12", ..., "final_sent_at": 0.125, "elapsed": 0.125,
 "text": "本地复现文本。", "task_id_matches": true}
```

服务端主动关连接（`--close-after-final`）时 3.11 同样复现——**该缺陷与「服务端是否关连接」无关**，
仓库既有测试之所以没抓到，是因为 CI 只跑 3.12（`.github/workflows/ci.yml` 仅 `python-version: "3.12"`）。

### 3.3 仓库既有测试在 3.10 上的既有红（继承红，非本卡引入）

`tests/test_sdk_client.py::test_flac_upload_matches_transcode_and_v2_frames`（未改动的既有测试）
在 3.10 上挂满 120s 自动预算后失败，在 3.12 上通过。

## 4. 最小修复

见 `design.md` 第 3 节。改动只有两处，都在 `sdk/capswriter_asr/client.py`：

1. `idle_watch()`：每轮的 `asyncio.wait_for(idle_messages.get(), timeout=...)` 换成
   `asyncio.wait({getter}, timeout=...)` + `finally: getter.cancel()`；语义等价，取消一定传播。
2. `_transcribe_connected` 的任务裁决：`receive_task` 在 `done` 里时直接返回其结果（**final 优先**）；
   其余任务报错时按 `upload → receive → idle` 的固定顺序上抛，不再依赖 `set` 的遍历顺序。

diff：`sdk/capswriter_asr/client.py | 34 +-`（含注释）。

### 已否决方案

见 `design.md` 第 3 节表格（删 `idle_watch` / 三处 `wait_for` 全换 / `gather` 加超时兜底 /
`sys.version_info` 分叉 / `asyncio.timeout`）。

## 5. 本卡范围外但已实证的另一处 3.10 缺陷（**未修，需另开单**）

`client.py` 里三处 `except TimeoutError`（`upload` / `idle_watch` / `deadline_watch`）在
**Python 3.10 上抓不到 `asyncio.TimeoutError`**——3.10 里 `asyncio.TimeoutError` 尚未是内建
`TimeoutError` 的别名（3.11 才合并）。后果：所有超时路径在 3.10 上抛裸
`asyncio.exceptions.TimeoutError`，而不是约定的 `AsrError(code="timeout")`。

实测（未改动的基线代码）：

```
$ uv run --no-project --python 3.10 ... pytest tests/test_sdk_client.py tests/test_sdk_deadline_stage.py -q
11 failed, 16 passed, 1 error in 642.78s
```

失败项：`test_flac_upload_matches_transcode_and_v2_frames`、`test_raw_f32le_frames_are_at_most_sixty_seconds`、
`test_progress_is_received_before_upload_finishes`、`test_server_error_code_and_retryable_are_preserved`、
`test_idle_timeout_is_independent_of_incoming_messages`、`test_blocked_send_uses_idle_timeout`、
`test_total_deadline_expires_despite_continuous_progress`、`test_cli_writes_srt_txt_and_json_with_legacy_srt_layout`、
`test_explicit_deadline_kills_local_ffmpeg`、`test_remote_stage_timeout_message`、
`test_local_and_remote_timeout_messages_are_distinguishable`（+1 error）。

这些是 **3.10 上的继承红**，与 issue #65 的「收到 final 后不返回」不是同一根因（本卡的根因在
3.11 上同样成立，而 3.11 的 `TimeoutError` 别名是好的），因此本卡**没有**动它。SDK 声明
`requires-python = ">=3.10"`，CI 却只跑 3.12——这个支持面与验证面的缺口建议单独收敛。

## 6. 尚未验证的边界（不得当作已验）

- 生产**尚未**升级到本修复；本卡不接触生产、不部署、不重启。
- 未做下游 `VideoTranscriptAPI` 的端到端验收（不在本卡授权范围）。
- 生产容器内的 `websockets` 具体小版本未取证（本地下游解析到 17.2；SDK 声明 `websockets>=15.0.1`）。
  根因在 `asyncio.wait_for`，与 websockets 版本无关，但未在生产版本上跑过。
- `transcribe_file` 的 `deadline_watch` / `upload` 仍用 `asyncio.wait_for`。它们在 ≤3.11 上
  也可能被吞取消，但按 `design.md` 2.3 的分析，吞掉之后下一步就会遇到仍待投递的取消，
  **会自终止、不挂死**；本卡未改，也未为它们单独造用例。若将来有人把这两处改成
  `asyncio.wait`，需重新评估取消语义。