<!-- delegate-outcome: succeeded -->
failure-visibility: p2-only

# C2 修后第二独立冷审：最终 verdict

## 裁决

**P2-only；没有经 internal 两问成立的 P1。** 本卡的冷审与要求的真实消费验证均已完成。观察到一个低频 SIGTERM/fatal 交错：明确收到 SIGTERM 停机时，已报告的 HTTP fatal 可能没有变成进程非零退出；fatal 先于 SIGTERM 时进程非零退出，但两条 `HttpServer.stop()` 可并发，日志出现一次 HTTP 收尾异常。两个路径都没有留下探针子进程；fatal 日志、源文件和 SQLite 任务/结果数据仍在。由于这一异常只落在显式停机窗口，服务管理器本来就在停止服务，且未见数据丢失或假存活，按 internal 风险档为 P2，不挡本轮完成。没有改源码或测试。

冻结审查范围为 `820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..e2fa535d1daa03a1491084a749d0c6e2aa2e1c55`。初判提交曾提出「损坏 SQLite 可能让 I/O 线程挂住进程」P1 候选；本轮真实消费实验否定了该候选，以下记录为最终结论，初判保留在前一提交历史。

## P1 两问与交错发现

internal P1 两问：真实使用方式下会触发吗？触发后果能否接受？

1. **已报告 fatal 后接 SIGTERM：有真实可达路径，但很窄。** 在指定源的真实 `os.unlink` 调用处注入 `PermissionError`，探针先调用原始 `HttpServer._mark_fatal`，再向自己的 PID 发真实 SIGTERM；没有篡改 `is_alive`、事件循环状态或 `start/stop`。裸 `env -i` 和 systemd unit 两次均记录 `HttpServer.fatal=PermissionError`，随后 `app_stop_entered`，再有 fatal 监督报告；最终进程退出码为 0。路径是 `http_server.py:383-387` 先置 fatal/event，信号回调在 `app.py:108-121` 调 `stop()`，其 done callback 在 `app.py:84-90` 停 loop，随后 `start()` 的 `RuntimeError` 分支在 `app.py:157-165` 因 `is_alive=False` 按正常信号返回。HTTP fatal 日志仍有记录。
2. **后果在本项目情境可接受，未达 P1。** 复现需要 SIGTERM 恰好落在 worker fatal callback 与父 `_serve_all()` 消费 task exception 之间。此时 SIGTERM 已明确要求停止服务；unit 会退出，应用不再假存活，损坏源文件仍在，SQLite `DONE/COMMITTED`、结果载荷仍保留。若 systemd 正在执行 stop/restart，是否重启由这次明确的管理动作决定，不靠这个退出码。因此“0 退出码掩盖已记录的清理异常”记为 P2 语义歧义，不升级为 P1。

反向顺序也实际运行：真实 unlink fatal callback 完成后才发 SIGTERM。裸环境与 systemd 均退出 1，符合 fatal 路径；但 app fatal drain 和 `HttpServer.serve()` 的 `finally` 能并发进入 `HttpServer.stop()`，两次调用共用已拆解的 aiohttp runner，日志出现 `HTTP 收尾失败：'NoneType' object has no attribute 'pre_shutdown'`。进程仍以非零退出。该交错的资源回收错误也是上述 P2 收尾歧义的一部分，没有扩大修复范围。

P1 候选——损坏 SQLite 启动时线程池 worker 存活——用相同 22 字节损坏数据库在裸 `env -i` 和 systemd 实测。异常点确实看到 `sqlite3.DatabaseError: file is not a database`、`HttpServer` 尚未发布、`http-io_0` 仍活着、Manager 仍活着；两个父进程都自然以退出码 1 结束，没有超时，之后 Manager 与 worker PID 均消失。异常边界的线程存活没有造成真实进程挂住，故撤销 P1 候选。

## 生命周期路由核对

| 路径 | 当前路由 | 本轮实际结果 / 未覆盖处 |
| --- | --- | --- |
| Manager 创建前失败 | `CapsWriterServer.start()` 在 `app.py:142-156` 包住 `process_manager.start()`；BaseException 进 fatal drain。`ProcessManager.start()` 的 `check_model()` 位于 `Manager()` 之前。 | 路径按源码会进入同一 drain；本轮没有人为使模型检查/`Manager()` 构造失败，Manager 半构造时的 multiprocessing 内部回滚未实测，列为 unknown。 |
| Manager/worker 已启动，HTTP 装配失败 | `start()` 的 BaseException 分支设非零、调用 `_drain_after_fatal()`，最终重抛；`app.py:166-177`、`181-193`。 | 裸环境与真实 systemd 的启动故障测试都记录到真实非空 Manager PID、`created=true`、`alive=true`，随后 Manager/worker gone、unit cgroup 空、自然非零退出。损坏 SQLite 的特殊异常也已单独消费。 |
| 正常 SIGTERM | 注册回调走 `CapsWriterServer.stop()`；WebSocket 和 ProcessManager 先停，HTTP stop future 完成后 done callback 停 loop；HTTP disabled 时直接停 loop。 | 裸环境与 systemd 的真实服务进程都以 0 退出，Manager/worker gone。HTTP enabled 与 disabled 均覆盖。 |
| 运行期 HTTP fatal | worker done callback → `_mark_fatal()` → `serve()` 从 fatal event 醒来并抛原异常，`finally` 执行 `HttpServer.stop()`；`_serve_all()` 消费异常并标非零；app drain 等 HTTP future 完成后重抛。 | 裸环境与 systemd 两种真实消费者均自然非零退出；识别 worker、Manager、FFmpeg 和 unit cgroup 回收；源字节、任务状态、结果 payload 与上传状态守恒。 |
| fatal 与 SIGTERM 交错 | app 层 stop 有 `is_alive` 幂等门；但 `serve()` 的 `finally` 仍可独立调用 `HttpServer.stop()`。 | 已报告 fatal 后的 SIGTERM 路径实际退出 0；fatal 后的 SIGTERM 路径退出 1 但观察到重入 stop 收尾错误。其余 scheduler 微顺序未穷尽，作为同一 P2 的边界未知。 |
| HTTP disabled | `resolve_http_settings()` 返回 `None` 时不创建 `HttpServer`；stop 没有异步 HTTP future。 | 裸环境与 systemd 的实际 WebSocket 服务都正常 SIGTERM 0 退出，Manager/worker gone。 |

启动异常在 `HttpServer.prepare()` 内、`self.http_server` 赋值前发生时，app drain 看不到未完成的对象。对损坏 SQLite，原始异常没有被 `prepare()` 的 `HttpStoreError/OSError/RuntimeError` 分支捕获；它向上进入 app BaseException 路由。实测线程池线程当时活着，但解释器自然退出仍 join 并结束该线程。别的失败类型或 Manager 构造中途失败的内部资源行为没有从本轮结果外推。

## 清理不变式与锁定证据

| 不变式 | 源码位置 | 锁定断言 / 外部消费 |
| --- | --- | --- |
| 只从 jobs→uploads 注册关系选 DONE/FAILED、`terminal_at IS NOT NULL` 且到达七天界线的源；恰好七天的等号按本卡明确要求可清理。 | `http_store.py:773-804` | `test_store_cleanup_uses_terminal_boundary_and_keeps_every_other_source`：等号 DONE 与过期 FAILED 删除，新鲜 terminal、陈旧 created_at、RUNNING/QUEUED、空 terminal_at、partial 和 junk 均保留。 |
| runner 持有引用时不 unlink；释放之后可清理。 | `http_server.py:281-294` 取 `runner.active_jobs` 快照；`http_store.py:796-802` 跳过快照内 job。 | `test_periodic_cleanup_waits_for_real_runner_reference_then_keeps_result` 使用真实 HTTPX 上传、runner、FFmpeg decoder 和阻塞的 `decoder.close()` 窗口；引用释放后源才删。 |
| 只 unlink 对应 source；jobs、uploads、results、失败语义保留；容量按实际文件存在与大小计算。 | `http_store.py:788-804`；source presence/计费见 `job_record`、`_reserved_source_bytes`。 | 上述 store/periodic 测试断言 DONE 结果 payload 字节、FAILED 的 `error_code`、上传 replay 不增 Job、过期 partial 仍计 source-presence，`EXPIRED` 查询 410，清理后容量减少恰好源字节数。 |
| 一个有界 mailbox 和一个 I/O 线程串行执行 SQLite、写文件及清理；未知异常沿监督链传播。 | `HttpIoWorker` 与 `HttpServer._mark_fatal`；`http_server.py:383-387`。 | `test_upload_io_and_cleanup_share_one_worker_five_times`；`test_cleanup_storage_failure_uses_fatal_serve_chain`；真实进程 fatal probe 的日志与退出码。 |
| stop 等实际在途 cleanup I/O 结束后再拆 worker/store，不能丢 callback。 | `http_server.py:303-350`。 | `test_shutdown_waits_for_inflight_cleanup_io` 用屏障卡住实际 worker I/O，验证 stop 未提前结束，释放后 pending 清空且 worker 关闭。 |

反向变异用新 pytest 子进程、`-s -vv` 和插件读取测试进程真实加载的函数指纹：

- `http_store.py` 的到期条件从 `terminal_at <= cutoff` 改为 `<`：准确的七天边界测试在 `assert not exact_done[2].exists()` 处变红。加载函数源码哈希 `83933fcd4e28f96c591f81efcb5fc75e1df799176914d38a2590a244b1167de6`，模块文件哈希 `1b7471a5408f9244b5e4ad4ae34960d1bc5d833be7dda7823414c67ee474cb82`。
- `HttpServer._source_cleanup_loop` 的活跃 Job 快照改为空集合：`test_periodic_cleanup_waits_for_real_runner_reference_then_keeps_result` 在 `decoder.close()` 尚未释放时因 source 已删而变红。加载函数源码哈希 `99090524ab1882acb7864eaf0193fe1604a90bb60757f7c9b11dada73348362f`，模块文件哈希 `8ab8bb64cb5703b56854a3eac47c3d460d89495d9e5b15ff65ba2fdaed30a072`。

两处变异均在 `finally` 中恢复；随后重载的 10 个关键函数 source hash 全部匹配独立 producer golden。源码和测试没有被变异留改。

## 实际消费者与测试结果

- 独立 producer 生成 2 秒、16 kHz、单声道、16 bit PCM WAV，64,044 字节，SHA-256 `31c1732c042424fc5367e5baac58067e00c4f476e2790a785f464cf929197e10`。真实 HTTPX 上传、SQLite、aiohttp、单 I/O worker、识别 Manager/worker、FFmpeg 与随机 loopback 端口参与；仅按卡面 stub ASR 引擎和权重初始化。fatal 前后的 source 字节和结果 JSON 均从真实 consumer 中读取并比对。
- 真实系统消费测试：8 项（fatal 清理、正常 SIGTERM、HTTP 启动失败、HTTP disabled，各裸 shell/systemd 两路）`8 passed`。systemd 启动失败断言 Manager 的真实 PID 大于 1、不同于 app/worker、已创建且存活，再断言 Manager/worker gone 与 unit cgroup 为空。
- 五个指定窄测试在 `websockets 17.2` 实际消费环境连续五轮；每轮 `5 passed, 8 deselected`。执行器 `Python 3.12.3`，本窄测隔离依赖补齐后实际解析 `pytest 9.1.1`、`pytest-asyncio 1.3.0`。隔离环境首次运行因 pytest-asyncio 只装在用户 site 而无法导入，已保留失败日志；将包安装到专用 venv 后重跑，五轮通过。
- 全量测试仅跑两次：`websockets 15.0.1`：`459 passed, 3 skipped, 149 warnings`（215.38 秒）；`websockets 17.2`：`459 passed, 3 skipped, 149 warnings`（210.51 秒）。两环境记录的 Python 均为 3.12.3、`aiohttp 3.14.3`、`httpx 0.28.1`、`pytest 9.0.3`、`pytest-asyncio 1.3.0`。三条 skip 的具体测试身份没有留在 `-q` 输出中，未猜测其身份或原因。
- 第一轮 ws15 全量曾因 fixture 子进程的 `HOME` 隔离隐藏用户 site 中的 NumPy 而有一个环境型失败；完整失败输出已留档。对应测试在专用 venv 装入 NumPy 后单项通过，随后 ws15 和 ws17 两次全量结果如上。没有把原冻结 head 的历史红说成已定位或已修复。

实际加载函数当前 hash（全部与 producer golden 匹配）：

| 函数 | SHA-256 |
| --- | --- |
| `CapsWriterServer.start` | `d57deb15ed6c4f0316128ab6d9e072ffa55275f7ad8df88fecb17dcea3ff9f82` |
| `CapsWriterServer.stop` | `6125757c1662d8a701268576b2d10decd54c7bef8dffa73701f7531ebf1ceafb` |
| `CapsWriterServer._drain_after_fatal` | `075e5615436c956fd5ade16f8b5bb5dceecc03c979513de55ecd688add8d6ca2` |
| `HttpServer.serve` | `793f98918dfc1dc8702d0ad3e96b2451ba345e5d839fde5dea9f3545862dd374` |
| `HttpServer._source_cleanup_loop` | `bfbd29c2e873865147c415678ee4d75688d1c806eb3d9ec64b53faa789358813` |
| `HttpServer._on_source_cleanup_done` | `622d4eaa2974ef2fc7274313c8b3bd95d63647faabfe1b35e2fd199e049846db` |
| `HttpServer.stop` | `c42f475af5f391e67dadd00c73b0868f345a7d67025a1b689b2cdcd0c08921e7` |
| `HttpStore.cleanup_terminal_sources` | `a0099a8d90ff2d0c6d6cd2042f7cdb06eed676a83889923eb1403478a8a7cc98` |
| `HttpStore.job_record` | `783374898a16b8930f8ef0e61a56b723133f41c2c583b7a11d68869920cc6f24` |
| `HttpStore._reserved_source_bytes` | `3487fab571cf50929e7fb5da8abbc759954f69b507be4b422171d7d015ca7f45` |

## OCR、未知项、熵增

- OCR envelope 为 `reviewed_fallback`，`coverage=complete`、`findings=[]`；主腿因 `leg_timeout`（900.111 秒）失败，DeepSeek 备腿成功（350.952 秒）。OCR 的 verifier 是 `none`、`verify_status=skipped`，因为没有 finding 可验证；这不替代本轮完整 review。三个状态按 envelope 读取，没有将 CLI 的退出码代替状态。
- 主干基线 `gh api request failed`，无法判定继承红。冻结 head 历史两条非零运行只有末行摘要，具体失败断言和根因仍未知；本轮绿结果不宣称修复了它们。
- unknown：`check_model()`/`Manager()` 创建之前或 Manager 构造中途失败未由新外部 producer 覆盖；Manager 已创建后的 listener 启动失败已在裸环境及 systemd 覆盖。全量的 3 个 skip 身份未知。fatal 与信号所有可能微顺序未穷尽；本轮覆盖正常 SIGTERM、fatal 单独、fatal 已报告后 SIGTERM、unlink raise 前请求 SIGTERM 四个实际路由。
- 熵增四问：新增 `start` fatal 路由和 `_drain_after_fatal` 各只有当前单一实现，但理由是已发生的端口关闭后 worker/Manager 留存失败，以及“只发起 stop future 后 loop 就退出”的已发生时序风险；第二消费者不存在，抽取成通用抽象无必要。HTTP cleanup callback/worker 不新增可选配置、重试或 fail-open；其异常进入 fatal 监督链。
- 收尾采样中，pickup 输出与一次宽范围进程命令曾意外显示本任务无关的旧提示/命令行内容。它们未参与判断、未被复制进仓库文档、也未发送给任何外部对象；本报告只引用本轮 scoped 源码、测试和上述私有临时证据。

## 提交与证据索引

冷初判提交：`3f4baef5cdccf78a5dbc766773bf320e2dbb5e8f`（当时已 push 并核对远端）。本轮正式写入仅限本 verdict 与 `docs/sessions/261003-http-completion/progress/c2-fixed-review2-progress.md`；代码、测试零正式写。验证命令：`git diff --check HEAD^ HEAD`。

全量 argv/env/stdout/stderr/timeline、进程 producer 报告、真实 argv/env、四个交错子目录、SQLite 裸环境/systemd 汇总、窄测每轮、两处变异前后指纹、当前 hash 与 OCR envelope 均保存在 `/tmp/dlg-20261004-064201-913fd4/`。报告白名单化引用摘要；不把凭据/整个环境或无界日志正文放进仓库。
