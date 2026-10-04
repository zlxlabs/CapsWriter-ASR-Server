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

## 8. 尚属未知的部分

- 未在真实 GPU/CPU 生产负载与真实模型权重下验证；ASR 引擎与权重按卡面 stub。
- 未做 systemd `Restart=on-failure` 的端到端重启实测；本卡验证的是「进程以非零状态
  真正退出 + 子进程被回收」，这正是重启能被触发的前提。
- `Manager` 进程在 `http_init_failure` 模式下由 `ProcessManager.stop()` 关闭，
  该模式下没有单独断言其 PID 消失（fatal 与 sigterm 两条都断言了）。
- 主干基线 API 派发时即不可用（`gh api request failed`），继承红未能判定。
