# C2 fresh-review3 冷审初判（实验前）

- 审查对象：`b0818dc7859d1d8100e42f5c70cb75d34da422f7..35439fe5b20ca1e8c425fd6137a32b2f6ec31c55`
- 工作树 HEAD：`35439fe5b20ca1e8c425fd6137a32b2f6ec31c55`
- 本文件只记录代码对照 spec 的冷读结论。本轮新实验、OCR、红验与最终 `failure-visibility` 写在后续进度与 verdict，不把仓内旧实验/旧 verdict 当本轮已测。
- 未读作者报告、旧 review/progress/evidence、agent-worklog/handoff。diff 里那些文档只当文件清单存在，不当推理输入。
- 主干已合 SDK 修复不重审。

## 产品 diff 范围

生产代码三处：`core/server/app.py`、`core/server/http_server.py`、`core/server/http_store.py`。测试新增 `tests/test_http_cleanup.py`、`tests/fixtures/http_fatal_exit_probe.py`。其余为文档，本冷审不采信其实验叙述。

## spec 溯源（本轮锁死的不变式）

来源仅 `docs/sessions/261001-http-files/design.md`、`qa.md`、`docs/sessions/261003-http-completion/m4-plan.md`、项目 AGENTS/测试说明。

| 不变式 | spec | 代码落点（冷读） |
|---|---|---|
| 终态源按 `jobs.terminal_at` 起算 7 天，等号满 7 天可清 | design R7；m4 §5 T5/T6；m4 决策(4) | `SOURCE_RETENTION_SECONDS`；`terminal_at <= now - 7d` |
| 只清已登记 DONE/FAILED 源 | m4 §5；qa#12 | SQL `state IN (DONE, FAILED)` + JOIN uploads |
| runner 仍持有引用不删 | m4 T8；design「活跃引用」 | 网络 loop 快照 `runner.active_jobs` 后交给单 worker |
| 在途 I/O 不与 cleanup 重叠 | design R5；m4 T3 | 单 `HttpIoWorker` 串行；`stop()` 在 inflight 时不 cancel |
| partial 物理文件不自动删；EXPIRED 410；元数据留 | m4 决策(3)(4)；T2；design 上传 TTL | 只把 UPLOADING→EXPIRED；不 unlink partial |
| jobs/results/FAILED error 保留；重放不新建 | m4 T6/T7；design 幂等 | cleanup 无 DELETE；`get_result` FAILED 仍 409+error_code |
| 容量只按源文件实际存在 | m4 §3 source-presence | `_iter_present_sources` `os.stat`；ENOENT 退出预留 |
| 未登记残留不删 | m4 T11；design「未登记残留不自动删除」 | 不扫目录，只按 uploads 行 unlink |
| 单 worker，不第二事实源 | m4 §5；design R5 | cleanup 投到既有 I/O worker；预留不另开账本 |
| 关键失败非零退出并回收 | design R6；qa#11 | `start()` 把装配放进 try；`_drain_after_fatal()` 复用 `stop()` |

m4 §3 公式写成 `terminal_at + 7d < now`，§5 T6 写成「满 7 天」。实现与 T5/T6 测试锁的是 `<=`（恰好 7 天可清）。冷审按 T6/R7「满 7 天」采信等号，不单凭 §3 的 `<` 造 P1。

m4 §3 T9「unlink 与释放记录两步崩溃窗」：C2 选用「文件存在性即账本」（spec 允许不强制列标记）。unlink 成功即 ENOENT 不再计费，不存在「先记释放再 unlink」的漏记方向。两步窗口本身不存在，列为实验后复核，不据此造 P1。

m4 曾写「app.py 暂不改」针对的是清理任务挂在 `HttpServer.serve/stop`。本 diff 改 `app.py` 是 R6 监督（fatal/启动失败先回收再非零退出），与清理消费链不是同一条机制。

## 新增机制必要性四问

### 1. 周期清理任务 + inflight/stopping 标志

1. 违反的不变式：没有周期任务则到期源永不释放，16 GiB 预留会静默永久满（m4 更正 #3）。
2. 触发路径：`HttpServer.serve()` 在 listener 就绪后 `create_task(_source_cleanup_loop)`；`stop()` 先停生产者。
3. 局部 guard 不够：清理必须发生在真实网络 loop 生命周期内，不能靠请求惰性路径删终态源。
4. 替代：没有第二套扫描器/账本；只把 `cleanup_terminal_sources` 投进既有单 worker。
5. 锁死测试（仓内已有、本轮实验后才采信绿）：周期引用窗口、单 worker 五轮、停机等 inflight。

### 2. `_drain_after_fatal` 与把 `process_manager.start()` 移进 try

1. 违反的不变式：R6「关键任务异常非零退出」；「端口已关、识别子进程还在」时监督看不见退出。
2. 触发路径：`start()` 里 `check_model`/`Manager`/`Process.start`/`HttpServer.prepare`/`_serve_all` 任一抛 `BaseException`。
3. 另写第二套回收顺序不够：`stop()` 已是唯一回收顺序；缺的是异常根上也要真正跑完它（HTTP 路径还要 `run_forever` 等到 done callback）。
4. 替代：复用 `stop()`，不为 fatal 新开回收状态机。
5. 锁死：进程边界探针的 fatal / HTTP 装配失败 / SIGTERM / HTTP disabled。本轮必须重新跑，不引用旧输出。

## App.start / stop / drain / serve-finally / callback 分支（冷读）

`CapsWriterServer.start()`：

- `is_alive` 已真：直接 return（防重入）。
- try：`process_manager.start()` → 可选 HTTP 装配 → `loop.run_until_complete(_serve_all())`。
- `except RuntimeError` 且 `is_alive`：listener 运行期失败；设 `exit_code`、drain、原样再抛。
- `except RuntimeError` 且非 `is_alive`：正常信号已走 `stop()`；不重复 drain；若 `exit_code` 则 `SystemExit`。
- `except BaseException`：启动/运行失败；设 `exit_code`、打日志、drain、原样再抛（含 `SystemExit`）。
- try 正常结束且 `exit_code`：`SystemExit(exit_code)`。

`_drain_after_fatal()`：`stop()`；仅当 `http_server is not None` 才 `run_forever()` 等待 HTTP done callback。HTTP 未装配时 `stop()` 同步 `loop.stop()`，无 future。

`stop()`：`is_alive` 已假则 return。否则关 WS、`process_manager.stop()`（含 Manager.shutdown）、HTTP 则 `ensure_future(http_server.stop())` + done callback 里读异常并 `loop.stop()`。

`HttpServer.serve()`：起清理任务 → 等 `_fatal_event` → fatal 则 raise → `finally: await stop()`。

`HttpServer.stop()`：置 stopping；非 inflight 才 cancel 清理任务；`gather(..., return_exceptions=True)` 后按既有顺序停 runner / listener / 换准入计数桩 / 关 store+worker。`_on_source_cleanup_done` 在任务非取消且有异常时 `_mark_fatal`。因此 `return_exceptions=True` 不会把清理失败变成静默成功：回调已经把异常送进监督链。

`ProcessManager.start()` 顺序：`is_alive=True` → **真实** `check_model()` → `Manager()` → `Process.start()` → `_wait_for_models()`。`check_model` 缺文件或不支持类型走 `sys.exit(1)`，此时 Manager/worker 尚未创建。`_handle_unexpected_exit` 抛 `SystemExit(1)`，应被 `start()` 的 `BaseException` 接到并 drain。

## 静默出错扫描（本 diff 生产文件）

- `http_store.py`：`FileNotFoundError: continue` 两处（cleanup 幂等 unlink；`_iter_present_sources` ENOENT 不计费）。其它 `stat` 错误上抛。符合 source-presence，不是吞成成功。
- `http_server.stop` / `_serve_all`：`return_exceptions=True` 只用于等取消/收尾；清理失败另有 `_on_source_cleanup_done` → `_mark_fatal`。
- 未发现 `except: pass` / 空 catch / 失败改返回空容器。

## 熵

新增常量 `SOURCE_CLEANUP_INTERVAL_SECONDS`（1h，无配置项）、三枚任务标志、一个 drain 辅助方法。都有第二消费者（serve/stop 与 start 两条失败根），不是单实现接口或镜像状态。

## 仓内测试结构（尚未当本轮绿）

`tests/test_http_cleanup.py` 9 个测试函数：store 边界、周期引用窗口、单 worker 五轮、cleanup PermissionError→serve fatal、停机等 inflight、以及 naked/systemd 两个 launcher 的 fatal / SIGTERM / HTTP 装配失败 / HTTP disabled。周期测试里的解码器是测试替身；进程探针走真实 ffmpeg + stub ASR/权重。裸 launcher 继承调用方 `os.environ`（本轮新消费者改用 `env -i`）。

创建边界缺口（冷读）：现有 HTTP 装配失败发生在 **Manager 与识别进程已经拉起之后**（数据目录父路径是普通文件，真实 `mkdir` 失败）。`check_model` 成功创建之前、以及 `Process.start` 边界的真实 OS 失败，仓内没有对应生产者。本轮必须用自有 subprocess/cgroup 限额或真实 `check_model` 消费路径去量；不能 stub raise、不能假 `is_alive`。量不到就 unknown，不造 P1。

## 冷审暂不裁定

- 不把「测试没写到」自动升级为 P1。
- 不修代码、P2/P3、不引入状态/重试/fallback。
- 最终 `failure-visibility` 等本轮实验、OCR、红验之后写进 verdict。
