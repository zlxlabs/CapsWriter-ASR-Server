# C2 P1：运行期 fatal 非零退出与资源回收 —— 关键证据

Base：`da854b2`（`card/http-m4-c2-fatal-exit-v2-261003` 冻结基线）。
提交：`76d58e5`（先红：真实进程边界测试）、`e43d782`（修复）、本文件所在提交（证据）。
派发：`dlg-20261004-020729-1b9614`。root_cause_group：`app_fatal_skips_process_cleanup`。

## 1. 不变式与它在代码/测试中的位置

**新不变式**：`CapsWriterServer.start()` 从「拉起子进程」到「监听循环结束」之间的
任何异常（启动期装配失败、运行期 listener/监督 fatal），都必须先按既有 `stop()`
顺序回收识别子进程、共享 Manager、ffmpeg 解码进程与 I/O 线程，再让进程以非零状态
真正退出。进程不得停在「监听已关、子进程仍活」的状态——监督看不到进程退出，也就没有
重启，真实的不可用会被报成存活。

| 不变式 | 代码 | 锁死的测试 |
|---|---|---|
| fatal 走完整 `stop()`，异步收尾观察到完成 | `core/server/app.py::start` 的 `except BaseException` → `_drain_after_fatal()` → `stop()` → `self.loop.run_forever()`（HTTP 收尾挂在 loop 的 done callback 上，不回循环就只算发起） | `tests/test_http_cleanup.py::test_fatal_cleanup_exits_process_and_reaps_children`（naked-shell + systemd-unit） |
| 进程真正非零退出 | 同上，回收后**原样重抛**，traceback 仍由解释器打到 stderr，退出码非零 | 同上，断言 `code != 0`；systemd 侧另断言 `ExecMainStatus != 0` |
| 子进程被回收而非留在后台 | `stop()` → `ProcessManager.stop()`（`queue_in.put(None)` + join + Manager shutdown） | 断言 `worker_pid`/`manager_pid` 从 `/proc` 消失、unit cgroup `cgroup.procs` 为空 |
| 正常 SIGINT/SIGTERM 语义不变 | `except RuntimeError` 分支在 `is_alive` 已为 False 时不重复收尾 | `test_normal_sigterm_still_exits_zero`（两种启动器，断言 exit 0 + 子进程消失） |
| HTTP disabled 与默认 WS 不变 | 未提供 `CW_HTTP_PORT` 时 `resolve_http_settings()` 返回 None，不装配 `HttpServer` | `test_http_disabled_keeps_default_websocket_lifecycle`（两种启动器） |
| 启动失败同 root：不得挂住已拉起的 worker | `start()` 把 `process_manager.start()` 与 HTTP 装配一起纳入同一 `try` | `test_http_startup_failure_exits_nonzero_without_hanging_worker`（两种启动器） |
| 已登记源、Job 终态、结果 payload 与上传元数据在 fatal 后原样保留 | `HttpStore.cleanup_terminal_sources` 只在 `os.unlink` 抛错时中止事务外动作；`http_server.py::stop` 只关连接与线程 | 同 fatal 用例：源字节 sha256/长度、SQLite `DONE`/`COMMITTED`、result payload sha256 与 JSON 全量比对 |

## 2. 真实 producer fixture

`tests/fixtures/http_fatal_exit_probe.py`（入库，非 /tmp 临时脚本）。在**自有进程**里跑
真实 `CapsWriterServer.start()`：真实 `SocketManager` / `HttpServer` /
`HttpFileRunner` / multiprocessing 识别子进程 / `Manager` / ffmpeg / SQLite。
按卡面只 stub ASR 引擎与权重初始化（`check_model` 与 `start_worker` 的引擎，
换成 `tests.harness.worker.run_recording_worker`——就绪协议、`active_http_jobs`
边界、TaskHandler、pipeline 全是生产代码）。

合成输入：2.0 s / 16 kHz 单声道 WAV（64044 字节，≤3 s、≤1 MiB），真实 ffmpeg 解码。

`fatal` 模式时序（全部是真实发生的事实，探针以 JSONL 落盘）：

1. 真实 HTTP `POST /v1/uploads` → `PATCH` → `POST .../commit`（走生产 TCP 路由）。
2. 真实 ffmpeg 解码 → 分段 → 投进真实 multiprocessing 队列 → 识别子进程回 Result →
   `HttpResultSink` 落库，Job 终态 `DONE`。
3. 等 `job_id not in app.http_file_runner.active_jobs`——**终态引用释放时序**的真实证据
   （报告里 `released_runner_jobs`）。
4. 在真实 SQLite 上把 `terminal_at` 改成 `now - 8 天`。
5. 对**该具体源路径**替换 `os.unlink`，命中即写 `probe-denial.jsonl`
   （真实痕迹：`{"event":"unlink_denied","path":…,"job_id":…,"pid":…}`），
   然后抛 `PermissionError`。
6. 报告 `pre_fatal`（PID/cgroup/argv/源字节/结果 sha/upload 状态），随后 `post_fatal`
   （`http_server.fatal` 的类型与消息、源字节仍在）。

环境与观测：两个真实消费环境各跑一次——`systemd-run --user` 瞬态 unit（`Type=exec`、
`--wait`、`KillMode=control-group`）与裸 shell（`start_new_session=True` 自成进程组）。
env 只按白名单逐个 `--setenv` / 传入，不整体继承；日志只取白名单行，不过滤环境变量、
凭据与原始响应体。

回收只按自己拿到的句柄：naked 走自己 `setsid` 出来的进程组，systemd 走自己起的那个
unit 名；没有名字通配，也不碰父进程或别的进程组。

## 3. 红（修复前，HEAD=da854b2 的生产代码 + 本卡最终测试）

`uv run --no-project … python -m pytest tests/test_http_cleanup.py -k "fatal_cleanup_exits or startup_failure or sigterm or ws_lifecycle or disabled"`
→ **4 failed, 4 passed**：

```
E  AssertionError: 探针主进程在 30.0s 内没有退出（pid=1863743 alive=True）；…
E  AssertionError: 探针主进程在 30.0s 内没有退出（{'ExecMainStatus': '0',
   'ControlGroup': '/user.slice/…/app.slice/cw-http-fatal-1863074-bf3ca70a.service',
   'LoadState': 'loaded', 'ActiveState': 'active'}）；…
4 failed, 4 passed, 5 deselected in 153.20s
```

四条红分别是 fatal / HTTP 初始化失败 × naked / systemd：`before` 的具体事实是
「unlink PermissionError 之后 parent active、worker alive、30 s 内不退出」，
systemd 侧 unit 一直是 `ActiveState=active`。正常 SIGTERM 与 HTTP disabled 四条为绿。

红不是导入/fixture 错误：同一批测试里 sigterm 与 disabled 两组通过，说明 fixture 装配、
端口、ffmpeg 与回收路径本身是通的。

`post_fatal` 报告里的 `worker_alive` **不是**回收判据（它在 fatal 被标记后、收尾开始前
就可能写出，取决于调度顺序；实测同一份代码下有 True 也有 False）。回收的权威判据是
测试对 `/proc/<pid>` 消失与 unit cgroup `cgroup.procs` 为空的断言。

## 4. 绿（修复后）

```
tests/test_http_cleanup.py + tests/test_http_supervision.py → 24 passed in 18.85s
```

全量（卡面 Verify-Command）：

| 依赖 | 结果 |
|---|---|
| `websockets==15.0.1`（固定） | `459 passed, 3 skipped, 149 warnings in 216.39s` |
| `--with websockets`（解析到 `17.2`） | `459 passed, 3 skipped, 149 warnings in 220.43s` |

三次 skip 身份与 C2 原证据一致：`test_aligner_integration.py` 的 ForceAligner
后端/模型两项、`test_segmenter.py` 缺 Silero-VAD 模型或 onnxruntime 一项。
pytest 未报告 HTTP decode skip，HTTP 用例全部收集执行。

一次真实 fatal 采样（`websockets==15.0.1`，两条分别对应裸 shell 与 systemd unit）：

```
pre_fatal  app_pid=1929553 worker_pid=1929585 manager_pid=1929576 worker_alive=true
           http_port=59949 ws_port=46549 released_runner_jobs=[]
           source={exists:true,bytes:64044,sha256:31c1732c…e10} upload_state=COMMITTED
post_fatal fatal_type=PermissionError fatal_message=injected source unlink denial
           source sha256 与 pre 完全一致（PermissionError 没有删源）
probe-denial.jsonl: {"event":"unlink_denied",
  "path":"…/httpdata/sources/c19a8cd9-36b5-40a4-b665-384bf6e18acf.bin",
  "job_id":"49c2065d-454f-4356-9d88-e83df179b96c","pid":1929553}
systemd 侧：Main processes terminated with: code=exited/status=1
```

源文件字节与上传字节 sha256 相同（`31c1732c…e10`，64044 字节），SQLite 里 Job 仍是
`DONE`、upload 行仍是 `COMMITTED`、`results.payload` 的 sha256 与 JSON 全量与报告一致。

## 5. 为什么原实现连「进程退出」都做不到

`start()` 的 try 只包了 `run_until_complete(self._serve_all())`，fatal 直接抛出，
`stop()` 从未执行。更关键的是：`_register_exit_signals()` 用
`loop.add_signal_handler(SIGTERM, …)`，asyncio 在主进程里把 SIGTERM/SIGINT 换成
`_sighandler_noop`；识别子进程是 `fork` 出来的，**继承**了这个 no-op handler，
于是 SIGTERM 对它无效。解释器退出时 `multiprocessing.util._exit_function` 的
`terminate() + join()` 就永远等不到子进程退出。实测 `/proc/<app>/syscall` 停在
`do_wait`（join），识别子进程停在 `do_poll`（仍在读队列），两者都不再前进。

这也解释了为什么「异常已经抛了」不等于「进程会退出」：唯一能让识别子进程退出的
`queue_in.put(None)` 就在 `ProcessManager.stop()` 里，也就是只在 `stop()` 里。

## 6. 与已接受 P2 的边界

- C2 review1 的 P2「主动 stop 重入时第二个 stop 绕过清理 task drain」**未修**：本卡
  只保证 fatal 与启动失败走一次完整 `stop()`，正常 SIGTERM 路径与 `serve()` finally
  的双入口重入行为保持原样，`test_shutdown_waits_for_inflight_cleanup_io` 与
  `test_normal_sigterm_still_exits_zero` 仍绿。
- review1 的 P2「周期重复物化并 unlink 全部历史到期 Job」属性能问题，**未修**。
- 未新增 state、释放账本、线程池、retry 或 fallback；未改 `http_store`、runner、SDK。

## 7. 环境依赖验证

`systemd-unit` 参数组的 skip 条件是「本机有 ffmpeg」且「`systemd-run --user --wait
--collect` 真的能跑通」——判据来自实际消费命令本身，不是「装了 systemctl」。
本卡在真实 systemd（255.4）与裸 shell 两个消费环境各跑过一轮 fixture：绿在上面，
红（回移 `app.py` 到 `da854b2`）也在两个环境各跑过一轮。伪造环境（伪造
`systemctl`/journalctl）没有被当作证据。

观测到但**不属于本卡**的现象：fatal 路径上 `core/tools/daemon_executor.py` 的
wrapper 线程在 future 已取消时 `set_exception` 抛 `InvalidStateError`。这是
`_serve_all` 取消 WS task 的既有行为，修复前的红跑同样出现，未改动。

## 9. 补交一轮（dispatch `dlg-20261004-041532-14a6d3`，Base `9ef0e52`）

补交卡点三项：包 Scope 正式追加、启动失败模式的 Manager 回收契约、报告卫生。本轮
**`core/server/app.py` 与 `9ef0e52` 逐字一致**（`git diff 9ef0e52 HEAD -- core/server/app.py`
输出 0 行），业务源码零新改。

### 9.1 包 Scope：实际是 6 个文件，不是 5 个

原报告写「5 files changed」，少算了 `tests/fixtures/__init__.py`。相对 `da854b2` 的实际
文件集（本轮结束后复核）：

```
core/server/app.py
docs/…/c2-fatal-exit-evidence.md
docs/…/progress/c2-cleanup-progress.md
tests/fixtures/__init__.py
tests/fixtures/http_fatal_exit_probe.py
tests/test_http_cleanup.py
                                                     合计 6 个文件（add/del 见 §9.6）
```

`tests/fixtures/__init__.py` 是 fixture 包让 `python -m tests.fixtures.http_fatal_exit_probe`
成立的必要文件，有两个真实 consumer（探针自身以模块方式启动 + 测试按 Scope 引用）。
本卡把它正式追加进有效 Scope，文件保留不删。原 envelope 与历史 card 不做任何改写。

### 9.2 启动失败模式：Manager 回收契约补证

原测试只断言启动失败后 worker 消失，共享 Manager 的回收没有证据；且若 `manager_pid`
为 `None`，`/proc/<None>` 类断言会恒真。

补法（只用现 fixture 字段 + 最小新增观测，不引状态/池/重试）：
`_observe_manager_before_http_assembly()` 在真实 `HttpServer.prepare()` 之前包一层记录，
`prepare()` 本体照旧执行并照旧抛真实异常——没有改 factory 去不建 Manager。记录分开存
「确实建过」（`manager_process_created`）、「确实活过」（`manager_process_alive`）、
以及同一时刻从 `/proc` 读出的 `manager_argv` / `manager_cgroup`。

启动失败模式实测（`websockets==15.0.1`，两个真实消费环境各一条）：

| 字段 | 裸 shell（naked） | systemd 瞬态 unit |
|---|---|---|
| `app_pid` | 1563739 | 1563910 |
| `worker_pid` | 1563810 | 1563960 |
| `manager_pid` | 1563800 | 1563951 |
| `manager_process_created` / `_alive` | `true` / `true` | `true` / `true` |
| `manager_cgroup` | `…/claude.slice/delegate-dlg-20261004-041532-14a6d3.service` | `…/app.slice/cw-http-fatal-1563582-3127a8b7.service` |
| 退出后 `/proc/<manager_pid>` | 不存在 | 不存在 |

测试侧断言：`manager_pid` 是与 `app_pid`、`worker_pid` 都不同的真实非空整数；created 与
alive 都为 True；argv 与 cgroup 非空；退出后 Manager 与 worker 都必须从 `/proc` 消失；
unit cgroup `cgroup.procs` 为空。

**红验**（单处回移，测试与 fixture 保持最终版）：
`git show da854b2:core/server/app.py > core/server/app.py`（未动 index、未改历史），
跑 `-k startup` → `2 failed, 11 deselected in 75.91s`，两条都是目标 `AssertionError`
（`探针主进程在 30.0s 内没有退出（pid=… alive=True）` / systemd 侧
`ActiveState='active'`），日志里同时可见 `manager_pid` 非空且
`manager_process_alive=true`——即 Manager 确实活过而进程不退。还原后转绿。

### 9.3 定向五轮（真实五轮，不是「五轮级别」）

原报告用「两 whole + 定向」称「5 轮级别」，本卡不接受该替代。本轮实跑：

| 套件 | 轮次 | 结果 |
|---|---|---|
| 定向 8 case（4 个进程边界用例 × naked/systemd） | 5 轮 | `8 passed` ×5（3.69s / 3.73s / 3.75s / 3.86s / 4.48s） |
| `tests/test_http_cleanup.py` + `tests/test_http_supervision.py`（24 case） | 5 轮 | `24 passed` ×5（18.35s / 18.63s / 18.24s / 21.84s / 21.39s） |

### 9.4 双版本全量

| 依赖 | 结果 |
|---|---|
| `websockets==15.0.1`（固定） | `459 passed, 3 skipped, 149 warnings` |
| `--with websockets`（解析到 `17.2`） | `459 passed, 3 skipped, 149 warnings` |

skip 身份与前文一致（ForceAligner 两项 + Silero-VAD/onnxruntime 一项），HTTP decode 未 skip。
原两套 `459 passed, 3 skipped` 作为历史结论保留，本轮实测值与之一致。

### 9.5 两次未复现的间歇红（如实记录，不当绿灯）

本轮观察到 **两次** 间歇失败，都没能留下断言输出（当时只保留了输出末行），此后无法复现：

1. 定向 8-case 集合的早期一轮：`1 failed, 5 passed`（断言未捕获）。
2. `websockets==17.2` 全量第一轮：`1 failed, 458 passed, 3 skipped`（断言未捕获）。

其后累计 **61 轮**未复现：8-case 定向 38 轮、24-case 定向 8 轮、全量 15 轮
（latest 4 轮 + pinned 4 轮 + 本节之前 7 轮中已含的 3 轮）。因此不能宣称「零失败」，
也不能宣称已定位。

已知且**未修**的结构性薄弱点（本卡选择报告而不是加防御）：

- 端口选取是 bind-and-release 的 TOCTOU：本卡新增的 `_free_port()` 与既有
  `tests/test_http_supervision.py`、`tests/test_http_file_runner.py` 的同名 helper 同形。
  若端口在释放与探针 bind 之间被占，探针会以「端口被占用」非零退出，
  `test_normal_sigterm_still_exits_zero` / `test_http_disabled_…` 会转红。
  修它需要「重选端口」式重试，正是卡面禁止的自动 retry；且该假设未被证实。
- 真实 systemd user manager 的时序：`_wait_unit_loaded` 20s、`wait_exit` 30s、
  `wait_report` 120s 都已留足余量，纯超时不足以解释两秒级完成的失败。

本轮实际修掉的一处 run-to-run 干扰源：`ProbeRun.cleanup()` 在 systemd 分支不再遗留
自己起的 `systemd-run --wait` 子进程给 pytest。

### 9.6 本轮预算

稳定事实（不随提交自引用变化）：

- 累计相对 `da854b2` 是 **6 个文件**；本卡只动其中 4 个（两个测试 + 两份文档）。
- `core/server/app.py` 在本卡 diff 中为 **0 行**：`git diff --quiet 9ef0e52 HEAD --
  core/server/app.py` 返回 0，确认与 `9ef0e52` 逐字一致。
- 6 个文件逐一比对卡面 Scope-Globs，全部 IN-SCOPE，无越界文件。

add/del 逐行数会因「更正文档数字的那次提交自身也占行」而自引用，故只给复现命令，
不写死一个会立刻过期的数字：

```bash
git diff --numstat 9ef0e52145bc89610fb322724462955fb2fad15a HEAD   # 本卡
git diff --numstat da854b2 HEAD                                    # C2 累计，6 行 = 6 个文件
```

在提交 `8166b1b`（代码+测试）与首次文档提交之间测得本卡为 add=194 / del=4；本节这次
「把数字改成自引用安全表述」的提交会再改几行，属预期内误差，不影响上述三条稳定事实。
原报告「5 files」的记账错误在本卡按实际 6 文件更正；原报告正文保留不改写。

## 8. 尚属未知的部分

- 未在真实 GPU/CPU 生产负载与真实模型权重下验证；ASR 引擎与权重按卡面 stub。
- 未做 systemd `Restart=on-failure` 的端到端重启实测；本卡验证的是「进程以非零状态
  真正退出 + 子进程被回收」，这正是重启能被触发的前提。
- `Manager` 进程在 `http_init_failure` 模式下的 PID 消失断言由补交轮（§9.2）补上；
  仍未知的是它在真实生产部署下的 shutdown 耗时分布。
- 主干基线 API 派发时即不可用（`gh api request failed`），继承红未能判定。
- §9.5 记录的两次间歇红未能定位，属于本卡明确的未解决项。
