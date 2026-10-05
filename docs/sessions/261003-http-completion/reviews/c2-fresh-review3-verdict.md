# C2 fresh-review3 verdict

failure-visibility: clean

- 审查对象：`b0818dc7859d1d8100e42f5c70cb75d34da422f7..35439fe5b20ca1e8c425fd6137a32b2f6ec31c55`
- 风险等级：internal
- spec：`docs/sessions/261001-http-files/design.md`、`qa.md`、`docs/sessions/261003-http-completion/m4-plan.md`、项目 AGENTS/测试说明
- 未读旧 review/progress/evidence/handoff；不重审已合主干 SDK 修复
- 本轮实验原始输出：`/tmp/dlg-20261004-114236-2c324e/`（外目录 700）
- 历史 CI 基线本次 `gh api` 不可用：继承红未能判定；本卡本地两次全量无新红

## OCR

status: fallback

reason: primary=`leg_timeout`（minimax，elapsed_s=900.016）；backup:deepseek=success（elapsed_s=320.271）。envelope `status=reviewed_fallback`，`cli_status=complete`，`coverage=complete`，`findings=[]`。`verify.verify_status=skipped`（`verifier=none`，counts.total=0）。zero-finding 且 verifier skipped 不说 passed。无 finding，故无 P1 两问条目。

## 代码结论

生产 diff 三处实现与 C2 不变式对齐：

- 终态源按 `jobs.terminal_at` 满 7 天（`<=`）且仅 DONE/FAILED、已登记源；`created_at` 不是年龄。
- 单 I/O worker 串行；`runner.active_jobs` 快照保护引用；inflight 清理在 `stop()` 里等完再拆 store。
- partial 只标 EXPIRED、不 unlink；jobs/results/FAILED `error_code` 保留；ENOENT 幂等；未登记残留不扫。
- 容量只 `os.stat` 实际存在的已登记源；无第二账本。
- `App.start` 把装配放进 try，fatal 复用 `stop()` 经 `_drain_after_fatal` 回收后再非零退出；正常 SIGTERM 仍 0。

m4 §3 的 `terminal_at + 7d < now` 与 T6「满 7 天」略有文案差；实现与 T5/T6 测试锁 `<=`。T9 两步释放记录：C2 选用文件存在性当账本（spec 允许），不存在「先记释放再 unlink」漏记窗。m4「不改 app.py」约束的是清理挂载点；`app.py` 的 drain 服务 R6 监督，四问成立。

未发现吞错当成功、也没有为本 P2 新造状态/重试。

## 真实消费者

独立 WAV producer（sha256 `8731…3e21`，64044 B）经 SDK HTTPX（retries=0）走真实 TCP/ffmpeg；识别引擎按卡面 stub。systemd 与 naked `env -i` 两路：DONE → 周期任务清源 → 停本 unit → 新实例读同一 SQLite。

重启后：结果 sha 不变、sqlite payload sha 不变、`source_available=false`、commit 重放同一 job、EXPIRED 410、FAILED `decode_failed` + 409 `job_failed`、EXPIRED partial 物理文件仍在（21 B / 2 文件）。加载函数 SHA 与审查树源码一致。

创建边界：真实 `check_model()` 消费 `CW_MODEL_TYPE=not-a-supported-engine`，在 Manager 创建前 `SystemExit(1)`，drain 后 leftover=[]。`Process.start` + TasksMax 未形成可归因失败（unit 被 INT、无子进程报告）→ unknown，不造 P1。

## 运行与红验

- pytest 全量 pin `websockets==15.0.1` 与 latest `17.2` 各一次，其余钉死 pytest 9.1.1 / pytest-asyncio 1.4.0 / aiohttp 3.14.3 / httpx 0.28.1 / Python 3.12.3。两次皆 466 passed, 3 skipped。
- skip 精确 ID：`tests/test_aligner_integration.py:53`、`tests/test_aligner_integration.py:62`、`tests/test_segmenter.py:208`。
- 有效小红 2：`_drain_after_fatal` 变 no-op 后启动失败探针 `AssertionError`（进程未退出且 Manager 当时仍活着）；cleanup 改 `created_at` 后 store 边界 `AssertionError`。scratch base `35439fe`，注入行已 grep。恢复后工作树产品文件与固定对象一致。

## 不变式索引

| 项 | 代码 | 测试 | 本轮真实消费者 |
|---|---|---|---|
| terminal_at 7 天等号 | `http_store.cleanup_terminal_sources` | `test_store_cleanup_uses_terminal_boundary_and_keeps_every_other_source` | e2e 老化后周期 unlink |
| DONE/FAILED 已登记源 | 同上 SQL | 同上 + 周期测试 | e2e remaining_exist=0 |
| runner 引用 / 在途 I/O | `active_jobs` 快照；单 worker | 周期测试；`test_upload_io_and_cleanup_share_one_worker_five_times`；`test_shutdown_waits_for_inflight_cleanup_io` | 调度真实触发；未穷尽 I/O 竞态窗 |
| partial/EXPIRED 410 | EXPIRED 更新不 unlink | store + 周期 | e2e 410 + 磁盘 21 B |
| FAILED 409 | `get_result` | store + 周期 | 真实垃圾文件 `decode_failed` |
| 重放不变 | 无 DELETE | 周期 replay | 重启后 create/commit 200 同 id |
| 容量=stat | `_iter_present_sources` | store reserved 减少 | e2e file_count/stat_bytes |
| 启动失败非零+回收 | `_drain_after_fatal` | HTTP 装配失败探针 | 真实 check_model；红验 1 |
| SIGTERM 0 / HTTP disabled | `stop()` / 不装配 | 对应探针 × 两 launcher | 含在两次全量 |

## 局限

- `Process.start` 真实 OS 限额失败未建立。
- e2e 老化把全部 UPLOADING 标过期，live 未到期 partial 未在该条链路单独保留（store 单测仍覆盖）。
- 周期测试的解码器是测试替身；进程探针与 e2e 用真实 ffmpeg。
- OCR fallback（主路超时、DeepSeek 备路成功、0 finding、verifier skipped，不说 passed）。
- 主干 CI 基线未能拉取，继承红未能判定。
