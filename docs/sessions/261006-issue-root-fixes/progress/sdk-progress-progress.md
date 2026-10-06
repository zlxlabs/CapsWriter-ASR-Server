# 卡 B（#76 SDK 双向进展判据）执行存档

- 卡：B（#76），root_cause_group `sdk-upload-progress-watchdog`
- 分支：`card/caps-76-sdk-261006`，Base `e849c21748392ad848131e07ff17d32e4cc83a8b`
- 设计来源（只读）：`8e93f7e49b07c8a25d199d0942dd7145b48f339b` 的 `docs/sessions/261006-issue-root-fixes/design.md`
- 本 scratch：`/tmp/capswriter-261006-probe-backpressure/`

---

## 单元一：真实背压复现（先证被测条件成立）

设计卡的探针 B 没能造出 send 阻塞，本卡按要求先证明真实发送背压存在，再动手改代码。

### 探针 C（`probe_c_real_backpressure.py`）：回环吞吐正常，但读速决定上限

- 真实 `transcribe_file` + 600 秒噪声 WAV（19.2 MB，s16le，10 帧，每帧 wire 2.56 MB）。
- 本地 `websockets.serve(max_queue=1)` + 每 1.5 秒读一帧。
- 结果：15 秒内服务端读到 9/10 帧，读速与节流一致 —— 但这是**读速**决定的，不是内核背压。

### 探针 D（`probe_d_buffer_absorb.py`）：`websockets.serve` 永远造不出真实背压

直接量「服务端读 2 帧后停止读取，客户端还能连发多少」：

```
{'rcvbuf': None,     'sent': 12, 'blocked': False, 'elapsed': 0.05, 'server_read': 2}
{'rcvbuf': 262144,   'sent': 12, 'blocked': False, 'elapsed': 0.07, 'server_read': 2}
{'rcvbuf': 65536,    'sent': 12, 'blocked': False, 'elapsed': 0.05, 'server_read': 2}
```

12 × 2.56 MB = 30 MB 在 0.05 秒内「发完」，`SO_RCVBUF` 降到 64 KB 也无效。原因：`websockets`
的 `Assembler` 会把**未读完整的帧**无限缓冲进用户态（只按「已完成消息条数」限流），
所以 socket 读得再慢也轮不到内核接收窗口关闭。**结论：拿 `websockets.serve` 当假服务端
断言背压是恒真断言。**

### 卡 B 的做法：最小 raw-socket WebSocket 对端

`tests/test_sdk_progress_watchdog.py` 里的 `FakeRemoteServer` 自己完成 `/health` 与 RFC6455
握手，自己解析帧，用 `read_gate` 控制「读到哪一帧为止」：

- `read_gate` 一关，对端不再从 socket 取数据 → StreamReader 缓冲填满 → `pause_reading` →
  内核接收窗口关闭 → 客户端 `ws.send` 在**真实内核背压**下阻塞。
- 被测条件从 SDK 自己的超时消息里取证：`已发送 N/10 帧`，`N < 10` 才算背压成立；
  连续多轮观察 `frames_read` 不增长作为旁证。

（同一形态的探针脚本保留在 scratch，测试内的 `FakeRemoteServer` 是它的测试化版本。）

### 附带定位：idle 失败后的收尾会挂死（探针 E）

第一次跑矩阵时 3 条「发送阻塞」用例全部 `assert caller in done` 失败。`probe_e_stall_teardown.py`
沿 `cr_await` 链打出真实等待点：

```
client.py:583  transcribe_file.<locals>.operation
client.py:516  _operation
client.py:390  _transcribe_connected          ← async with 的 __aexit__
websockets/asyncio/client.py:586   connect.__aexit__
websockets/asyncio/connection.py:221  Connection.__aexit__
websockets/asyncio/connection.py:636  Connection.close
contextlib.py:217  _AsyncGeneratorContextManager.__aexit__
```

`Connection.close()` → `send_context()` → `send_data()` + `await self.drain()`，
`drain()` 等的是 `resume_writing()`，而写缓冲要等对端读才会掉到低水位。对端已停读 → 永久挂起，
`close_timeout` 只兜 `connection_lost_waiter`，兜不住 `drain()`。

这条是**本卡之前就存在的缺陷**（旧的逐帧 send 超时同样会走进这里），但只有真实背压才能碰到；
它直接违反本卡完成条件 1（上传未完成即有界失败）与完成条件 5（取消后全部回收），
因此在 `_transcribe_connected` 里改为自管连接进入/退出：成功路径仍优雅关闭，
异常/取消/停滞路径 `ws.transport.abort()`。

---

## 单元二：idle 判据 TDD

`tests/test_sdk_progress_watchdog.py`（14 条，全部走真实 `transcribe_file` 与真实上传帧）：

| 用例 | 覆盖 | 关键断言 |
| --- | --- | --- |
| `test_blocked_upload_with_silent_server_fails_on_idle_before_upload_done` | 矩阵 1 | `上传连续 3 秒没有进展：已发送 N/10 帧` 且 `N < 10`（背压前提自证） |
| `test_successful_sends_keep_upload_alive_past_one_idle_window` | 矩阵 2a | 上传耗时 > idle 仍活着；上传结束后按「等待结果」失败，`已发送 10/10 帧` |
| `test_idle_fires_after_upload_completes_without_any_result` | 矩阵 2b | 短音频单帧，已发满 1/1 |
| `test_backpressure_with_continuous_results_survives_and_finalizes` | 矩阵 3a | 背压 9 秒不死；`frames_read < 10` 且 `results_sent >= 5`；松闸后拿到 final |
| `test_messages_that_are_not_task_progress_do_not_refresh_idle[unknown/foreign]` | 矩阵 3b | 在 idle（<15s）暴露而非等 90s 总预算 |
| `test_server_error_frame_during_upload_is_propagated[decode_stalled/audio_too_long/inference_failed]` | 矩阵 4a | code 原样透传，未被改写成 timeout/成功 |
| `test_connection_closed_without_error_frame_reports_connection_lost` | 矩阵 4b | `connection_lost` |
| `test_error_frame_wins_over_final_sent_in_the_same_tick` | 矩阵 4c | 同轮 error+final 时 error 胜出 |
| `test_explicit_deadline_total_still_wins_with_continuous_results` | 矩阵 5a | 连续结果下 `转录超过deadline_total` 仍生效 |
| `test_cancellation_under_backpressure_reclaims_everything` | 矩阵 5b | CancelledError + 无遗留内部任务 |
| `test_scenario_constants_match_the_real_frame_layout` | 反熵自检 | 场景帧数必须等于 SDK 真实帧布局 |

生产改动（`sdk/capswriter_asr/client.py`）：

- `idle_watch` 从连接建立就启动，删掉 `upload_done` 前置门（该 Event 已无消费方，整体删除）。
- 删掉逐帧 `asyncio.wait({sender}, timeout=idle_timeout)`，改为直接 `await ws.send(frame)`；
  发送异常仍由 upload 任务原样上抛，外层 `FIRST_COMPLETED` + `ordered` 裁决不变。
- 新增 `_audio_frame_bytes` / `_audio_frame_count`：停滞消息要报「已发/总帧」，
  分母必须在发送前算出（不物化整个切片列表，避免整份音频再复制一份）。
- `_receive` 收窄：只有 `type ∈ {result, error}` **且** `task_id` 等于本次任务的帧才刷新 idle；
  未知 type 与陌生 task_id 一律忽略且不刷新（`core/protocol.py` 里两种消息都必带 task_id）。
- 停滞消息只报 SDK 掌握的事实：阶段 / 已发帧 / 总帧 / 中间结果条数 / 距最近进展秒数，
  不推断网络或服务端责任。

既有测试随语义变更同步（不是放宽断言）：

- `test_sdk_client.py`：假服务端回帧补 `task_id`（协议必带）；
  `test_receive_idle_budget_does_not_fire_during_slow_upload` → 改名为
  `..._while_uploads_keep_succeeding` 并把「上传期未建 idle getter」翻转成「上传期已在监视」；
  `test_blocked_send_uses_idle_timeout` → `test_blocked_send_with_silent_server_reports_idle_stall`，
  断言从「发送音频帧」改为新的停滞事实消息；四个连接替身补 `transport` 出口。
- `test_sdk_deadline_stage.py` / `test_sdk_samples_total.py`：假服务端回帧补 `task_id`。

预算与默认值一字未动：自动预算仍是 `duration*4+120`，默认 `idle_timeout` 仍是 300，
显式 `deadline_total` 仍是整次调用的绝对墙钟（含本地准备阶段），由
`test_sdk_deadline_stage.py` 原有的公式锁与两段计时用例继续看守。

---

## 单元三：异常、取消与文档

（待补：红验与文档）