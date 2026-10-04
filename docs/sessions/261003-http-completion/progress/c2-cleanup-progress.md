# M4-C2 进度

## 当前阶段

reviewing（最新一段见下方「2026-10-04 P1 修复」）。C2 本体实现、行为证据与双版本全量
验证已完成；review2 提出的 P1 已在 `card/http-m4-c2-fatal-exit-v2-261003` 修复。
PR #62 保持 draft。

## 本段结论（C2 本体，已完成）

真实 HTTP listener、单 I/O worker、runner 和 TCP 客户端已证明：DONE 落库后 runner 仍持有 decoder 引用时源文件保留；runner 释放后周期任务删除源文件，HTTP 结果仍可领取。七天边界、DONE/FAILED、terminal_at/任务状态、partial、未登记文件、幂等重复清理、append/commit/终态写入各五轮并发 I/O、后台 fatal 与 shutdown 在途 I/O 均有断言。定向测试 `5 passed in 1.74s`。固定 `websockets==15.0.1` 与最新 `websockets==17.1` 两轮全量均 `451 passed, 3 skipped`。

## 2026-10-04 P1 修复（dispatch `dlg-20261004-020729-1b9614`，Base `da854b2`）

- 新不变式：`CapsWriterServer.start()` 从拉起子进程到监听循环结束之间的任何异常
  （启动期装配失败与运行期 fatal 同一条 root）都先按既有 `stop()` 回收识别子进程、
  共享 Manager、ffmpeg 解码进程与 I/O 线程，再让进程以非零状态真正退出。
- 针对的 finding：review2 的 P1「运行中 cleanup fatal 只关监听、进程与 worker 仍存活」。
- 根因不止「异常路径没走 stop」：`_register_exit_signals()` 装的是 asyncio 的
  `_sighandler_noop`，fork 出的识别子进程继承后 SIGTERM 失效，解释器退出时的
  `terminate()+join()` 永久阻塞——实测 app 停在 `do_wait`、worker 停在 `do_poll`。
- 修法：fatal 时先 `stop()`，HTTP 已装配时再回事件循环跑一次 `run_forever()`
  （HTTP 收尾挂在 loop 的 done callback 上，不回循环就只算发起），然后**原样重抛**，
  traceback 仍走 stderr、退出码非零。正常 SIGINT/SIGTERM 与 HTTP disabled 语义不变。
- 真实边界 fixture 入库 `tests/fixtures/http_fatal_exit_probe.py`：自有进程跑生产
  `CapsWriterServer`（真 SocketManager/HttpServer/HttpFileRunner/worker/Manager/ffmpeg/
  SQLite，只 stub ASR 引擎与权重初始化），2 s 合成 WAV，systemd 瞬态 unit 与裸 shell
  两个真实消费环境各跑一次；env 白名单逐项传入，日志只取白名单行。
- 红：回移 `core/server/app.py` 到 `da854b2` 后 fatal 与 HTTP 初始化失败四条红
  （parent active / worker alive / 30 s 不退出），SIGTERM 与 disabled 四条仍绿。
- 绿：定向 `24 passed`；全量固定 `websockets==15.0.1` 与最新 `websockets==17.2`
  各 `459 passed, 3 skipped`（skip 身份与 C2 原证据一致，HTTP decode 未 skip）。
- 未动已接受的两条 P2（主动 stop 重入漏观察、周期重复物化历史到期行）；未新增
  state/账本/池/retry/fallback；未改 `http_store`、runner、SDK；未部署。
- 证据：`docs/sessions/261003-http-completion/c2-fatal-exit-evidence.md`。

## 2026-10-04 补交一轮（dispatch `dlg-20261004-041532-14a6d3`，Base `9ef0e52`）

- 本轮 `core/server/app.py` 与 `9ef0e52` 逐字一致（diff 0 行），业务源码零新改。
- 包 Scope 正式追加 `tests/fixtures/__init__.py`：相对 `da854b2` 的实际文件集是
  **6 个不是 5 个**（原报告记账少算一个）。原 envelope / card 历史不改写。
- 启动失败模式补真实 Manager 回收契约：探针在真实 HTTP 装配点记录 Manager 的真实
  PID 与 `/proc` 痕迹（分开记「建过」与「活过」），测试断言它是与 app/worker 都不同
  的非空 PID 且退出后从 `/proc` 消失。`prepare()` 本体照旧执行并照旧抛真实异常。
- 红验：单处把 `app.py` 回移到 `da854b2`，两条启动失败用例以目标 AssertionError 转红
  （日志里 manager 非空且 alive=true），还原后转绿。
- 定向真实五轮：8-case 进程边界用例 `8 passed` ×5；cleanup+supervision 24 case
  `24 passed` ×5。不再用「两 whole + 定向」冒充五轮。
- 双版本全量：固定 `websockets==15.0.1` 与 `websockets==17.2` 各 `459 passed, 3 skipped`，
  skip 身份与前轮一致，HTTP decode 未 skip。
- **如实记录两次未复现的间歇红**（早期定向一轮、`17.2` 全量第一轮），断言输出未捕获，
  其后 61 轮未复现；已定位的薄弱点是端口选取的 bind-and-release TOCTOU（本卡按卡面
  不加重试式防御，选择报告）。详见证据文档 §9.5。
- 本轮预算：相对 `9ef0e52` 为 2 文件 add=63 / del=2；相对 `da854b2` 累计 6 文件
  add=1230 / del=19。

## 决策与否决

- 年龄只读 `jobs.terminal_at`，候选条件为 DONE/FAILED 且 `terminal_at <= now - 7 天`；不增加 schema、账本或配置项。
- 每轮在网络 loop 只读 `HttpFileRunner.active_jobs` 快照，SQL/unlink 与现有 I/O worker 操作串行。
- 周期同时将逾期 UPLOADING 持久化为 EXPIRED；partial 文件保留并继续 source-presence 计费，GET 返回 410。
- 不加源释放标记或第二账本；文件存在性本身是 C1 的计费真源，ENOENT 后自然释放额度，重复清理幂等。
- 两轮 suite skips 都只有 ForceAligner 两项和缺少 Silero VAD/ONNX 的一项；HTTP 测试全收集、无 HTTP decode skip。
- PR #62 以 PR #60 为 base，保持 draft；C1 合并前不 ready/merge，不部署生产。
- 上传状态、任务、结果与元数据保留；未登记文件与 UPLOADING/EXPIRED partial 不进入终态候选。
- 仅 unlink 的 ENOENT 按幂等处理，其他错误继续进入 fatal 监督链。

## 下一步唯一动作

由 Pi 主脑独立审查 PR #62；PR #60 合并后再将 #62 base 切到 master 并完成其 gate。
