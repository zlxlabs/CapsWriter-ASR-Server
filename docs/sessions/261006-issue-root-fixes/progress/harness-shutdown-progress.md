# 卡 C（#85）harness 受控子进程回收 — 进度存档

Base：`e849c21`（master）。设计真身：`8e93f7e`（`docs/sessions/261006-issue-root-fixes/design.md` 卡 C）。

## 阶段一：实测定位（不采信工单推断的停止顺序）

结论先行：**工单与设计推断的「pytest 挂死」在当前代码上不成立**；当前代码真实存在的
缺陷是「owner 不回收自己 fork 出来的解码子进程，导致 teardown 退化成 10s 慢收尾 +
误导性二次断言」。定位到的精确等待点是服务主进程的 `websockets` `wait_closed()`：
被 SIGSTOP 的 ffmpeg 读不动 stdin → 写侧 `_feed_compressed` 与读侧互等 → 接收协程
永不退出 → 主进程等不到「全部连接关闭」。

实测矩阵（探针 `probe/test_repro85.py`、`probe/test_counterfactual_owner.py`，
真 harness / 真 websocket / 真 ffmpeg / 真 SIGSTOP）：

| 形态 | 做法 | 结果 |
|---|---|---|
| A | ffmpeg 刚进 T 态主体即断言失败，`finally` 先 `_force_kill_ffmpeg` 再 `stop()` | pytest 退出码 1，1.3s |
| B | `upload_idle_seconds=100000`（纯测试侧参数让看门狗本窗口内到不了点）→ 主体等终态超时失败，现场与工单红验形态逐字相同 | pytest 退出码 1，13.3s，ffmpeg 已回收，无残留 |
| C（隔离实验） | 同 B，但**不**预杀 ffmpeg，只留 owner 收 | `stop()` 耗时 **10.02s**，抛 `AssertionError('服务主进程未在 5 秒内响应 worker 停止信号')`，服务主进程 exitcode **-15** |

形态 C 的「before」事实（`/tmp/facts_before.json`，pid 为实测值）：

```
server_pid=1370146  worker_pid=1370164  ffmpeg_pid=1370198
ffmpeg_before_stop = {comm: ffmpeg, state: T, ppid: 1370146}   ← 本 owner 的直接子进程
stop_seconds = 10.02     stop_error = AssertionError(服务主进程未在 5 秒内响应 worker 停止信号)
server_exitcode = -15
```

反证「挂死」：形态 C 的 pytest 主进程本身**有界退出**（退出码 1，19.6s）。
早期一次 `timed_out=True` 是探针自身缺陷——用管道收输出，孤儿进程继承管道写端导致
`communicate()` 永不等 EOF；改为写文件 + 轮询进程存亡后不成立。**不把探针故障当被测故障。**

## 阶段二：owner 侧根治

改 `tests/harness/server.py` 的 `ManagedFakeServerHarness`：新增 `stop()` 第一步
`_reclaim_decoder_children()`，在请求服务主进程收尾之前，先按 **ppid 所有权**
（服务主进程的直接 ffmpeg 子进程）SIGKILL 解码子进程，并 wait 确认它们不再是
T/运行态。SIGKILL 对 T 态进程同样生效，不先发 SIGCONT。

删除的非法状态：「回收本 owner fork 出来的解码子进程」这件事散落在每个测试的
`finally` 里，谁忘了写就退化成 10s 慢收尾 + 与故障无关的二次断言；正常收尾路径
是否还能走，取决于测试作者记不记得写那一行。

不碰 `tests/test_ws_progress_watchdog.py`：设计卡 C 明确它是消费方、非根治点，
且不得与卡 A 同时改。

after 实测（同一探针，`/tmp/facts_after.json`）：

```
stop_seconds = 0.07      stop_error = null      server_exitcode = 0
pytest 退出码 1，唯一失败是主体原断言「等待任务 … 终态超时 (8.0s)」
```

回归：`tests/test_ws_progress_watchdog.py` 5 passed in 49.31s（无退化）。

## 阶段三：跨进程回归（`tests/test_harness_shutdown.py`）

见提交记录；红验（撤回修复）与 5 轮稳定性结果见最终报告。
