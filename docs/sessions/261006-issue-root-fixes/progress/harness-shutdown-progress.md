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

两件不同的事，分开记：

1. **pytest 进程本身**：形态 C 下它有界退出（退出码 1，19.6s）。这是对「进程挂死」的直接反证。
2. **外层收输出的管道**：早期一次 `timed_out=True` 是探针自身缺陷——管道模式下跑砸留下的
   孤儿进程继承管道写端，`communicate()` 永远等不到 EOF。这是「收不到输出」，
   **不构成**对第 1 点的证据；改成写文件 + 轮询 `/proc` 判存活后两者不再混淆。

结论只到第 1 点：当前代码下 pytest 进程不会因为这个路径挂死；工单描述的「7 分钟以上
挂住」在当前代码上没有对应现场。

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

新增两个文件（都不改生产代码）：

- `tests/fixtures/harness_shutdown_inner.py`：内层 pytest（文件名不匹配 `test_*.py`，
  不进常规收集，只被外层显式执行）。主体断言必然失败、失败瞬间持有被 SIGSTOP 的
  解码子进程；**刻意不在 finally 预杀 ffmpeg**；把实测 pid / T 态 / 退出码 / 耗时
  写进 marker JSON 供外层断言；兜底 kill 在写 marker 之后，不掩盖回收结果。
- `tests/test_harness_shutdown.py`：5 个用例（owner 回收、正常上传不退化、空服务不退化、
  对照进程零信号、E2E 非零退出）。

### 现场形态的两次修正（都是实测打脸，不是推测）

1. **第一版用例是空洞的**：只发头一段就断开连接，`stop()` 即使没有 owner 回收也很快。
   第一次变异（删掉 reclaim 调用）4 passed —— 判据对已知坏输入不变红，按 Unknowns
   纪律作废重写。
2. **真正卡住的条件是「服务端写侧卡在被停住的 ffmpeg 的 stdin 上」**：只发头一段时
   服务端在读侧空闲，客户端断开就能解开；客户端把剩下的音频推上去之后（上传途中停滞），
   连接关闭**解不开**互等（接收协程回不到 `recv()`，finally 跑不到），
   `_decoder_children` 在连接关闭后仍能读到 T 态的解码子进程。实测三组参数
   （30s/HOLD=1、30s/HOLD=8、120s/HOLD=3）稳定复现 stop()=10.01s、exitcode=-15、
   且 stop() 返回后仍有一个 T 态 ffmpeg 被 init 收养（pid 1240）——**资源遗留**。
   「客户端 send 被堵住」不是可用的判据：3.9MB 上行量下 transport 全部吸收，pump 总是完成。

### 红验 / 绿验与变异检查

| 构建 | `tests/test_harness_shutdown.py` |
|---|---|
| 修复撤回（删掉 reclaim 调用） | **3 failed, 2 passed**，37.2s（失败原因恰是三条约束） |
| 修复在位 | **5 passed**，6.6s |

三次变异各自打红对应的断言（每次只还原改坏处，修复本体先存于 commit）：

| 变异 | 结果 |
|---|---|
| 删掉 `await self._reclaim_decoder_children()` | 3 red；失败原因：`AssertionError: 服务主进程未在 5 秒内响应 worker 停止信号`（×2）、`teardown 仍在服务故障之外二次失败` |
| `_decoder_children` 放弃 ppid、改成按名字全局杀 | bystander red：`owner 误杀了不属于它的 ffmpeg（pid=1601973，exitcode=-9）` |
| reclaim 里 SIGKILL 改 SIGTERM | owner reclaim red 且有界（11.95s）：`解码子进程 [1751694] 在 SIGKILL 后 5.0s 内仍未停止：[('ffmpeg', 'T', 1751569)]` |

5 轮连续：round 1..5 全部 `exit=0`，5 passed，6.57–6.67s。
窄测：`tests/test_harness_shutdown.py + tests/test_ws_progress_watchdog.py` → **10 passed in 55.84s**。

### 踩到的探针故障（两度把「管道等不到 EOF」误判成「pytest 挂死」）

用 `subprocess.PIPE` 收内层输出时，跑砸留下的孤儿进程继承管道写端，`communicate()`
永远等不到 EOF。改写文件 + 轮询进程存亡后，pytest 主进程两次都被证明**有界退出**。
E2E 用例因此也改成写文件 + `Popen.wait(timeout=...)`，判据落在进程本身而不是管道。

## 阶段四：第一次有限收尾轮（原 owner / 查询 / producer 契约）

固定 H0=`482cf9a`。独立首审 verdict（`bdba4fa5`，58 行）按原样 pick 进本分支，逐字未改。

1. `stop()` 里 reclaim 包进 `try/finally`：reclaim 上抛时，原有的服务停止/join、
   `info_queue.close()` 与 `manager.shutdown()` 通道仍走完；错误仍 fail loud
   （finally 里不吞、不重试、不加超时配置）。
2. 三处广捕 `OSError -> None` 缩窄为 `(FileNotFoundError, ProcessLookupError)`：
   PermissionError/EIO 等未知读失败上抛。实测三态：有效 pid 返回事实、
   不存在 pid 返回 None、注入 PermissionError 上抛（errno 13）。
3. 内层 producer 把**真实 `sys.argv`** 与**白名单单个 `CW_HARNESS_SHUTDOWN_MARKER` 值**
   写进 marker（不 dump 整个 environ）；父进程按真实 marker 字节比对 argv 与父进程
   实际传入的实参、env 路径等于实际目标。变异：少写 argv 首项 -> exit=1（1 failed，
   2.70s）；写错 marker env -> exit=1（1 failed，2.54s）；两次都是断言红，不是 ImportError。
4. 未跟踪探针脚本（5 个，非卡面点名的 2 个）按原文件名/字节/sha256 精确移到本轮
   report 的 evidence 目录，未删除、未 commit；`probe/` 只剩被 gitignore 的 `__pycache__`。
5. 本轮不加进程组、不加看门狗、不加重试、不改生产/HTTP；没有真实 /proc 权限错误或
   SIGKILL 后 D 态不可杀的现场，不升级 P1、不穷举畸形对象。
