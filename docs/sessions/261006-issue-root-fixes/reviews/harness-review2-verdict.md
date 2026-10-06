# #85 测试 owner 资源回收：修后审查 2

- 冻结范围：`e849c21748392ad848131e07ff17d32e4cc83a8b..e2755ed8a8e9a663b0021f38ded8ab7ea67b6777`；H0=`e2755ed8a8e9a663b0021f38ded8ab7ea67b6777`。
- 专项增量先审：`482cf9ae720efb512d5c42b79943c3f4bdacc7f1..e2755ed8a8e9a663b0021f38ded8ab7ea67b6777`；随后完整固定 diff，共 948 insertions / 11 deletions。旧 `harness-review1-verdict.md` 内容未读；仅核对它在源 `bdba4fa51095b6659bac3f91a2e54799025a1c92` 与 H0 的 blob 都是 `9f757303ccbeabff95ef926a738ff1c403fddd9d`。
- OCR 调用：`ocr-review --repo <本卡工作树> --from e849c21748392ad848131e07ff17d32e4cc83a8b --to e2755ed8a8e9a663b0021f38ded8ab7ea67b6777 --audience agent --concurrency 4 --background-file <保留的 spec-summary.md>`；仓内公开 verdict 省略本机路径，完整实参在本地 dispatch report。
- OCR stdout JSON envelope：`status=reviewed_fallback`、`coverage=complete`、`profile=deepseek`、两条候选均已核验。Primary 在工具内部 900.109 秒后 `leg_timeout`，DeepSeek 备链完成；OCR 用时不计入本卡 20 分钟调查预算。首次 nohup 调用无 stdout/stderr、无 envelope，不作为完成证据。
- 本机为 Linux `/proc` 环境、Python 3.12.3。非 Linux 测试标记为 skip；`tests/harness/server.py:293-295` 也明确 `/proc` 不存在时不枚举子进程。未在非 Linux 环境验证。
- 实际消费者审查：`ManagedFakeServerHarness` 由 `tests/test_error_contract.py`、`tests/test_e2e_sdk_server.py`、`tests/test_health.py`、`tests/test_ws_progress_watchdog.py`、`tests/test_segmentation_contract.py` 等测试调用；新增 owner、正常收尾、bystander、helper 故障及独立 pytest 生产者均在本轮范围内。未发现生产调用点。
- 窄测：`pytest -q tests/test_harness_shutdown.py` → `6 passed, 10 warnings in 6.54s`。未跑全量 suite 或 CI。

failure-visibility: p2-only

## Findings

### P2 — helper 失败时 teardown 会覆盖原错误并留下暂停的解码子进程

- Spec：helper 异常后仍回收 owner 资源并保留主错误；服务/ffmpeg 等 owned 资源均须回收。
- 位置：[tests/harness/server.py:208] 中 `finally` 的停止顺序，重点是 `:220-227`；当前失败测试位于 [tests/test_harness_shutdown.py:364]。
- 证据：在临时探针中先造真实 T 态 ffmpeg，再令 owner helper 在执行前抛 `RuntimeError`。实际 stdout：`{"context_type":"RuntimeError","ffmpeg_state_before_probe_cleanup":"T","manager_alive":false,"root_exitcode":-15,"stop_error":"服务主进程未在 5 秒内响应 worker 停止信号","stop_error_type":"AssertionError"}`。因此 stop 最终报告的是次级断言，原始 helper 错误只在 context；服务主进程被 SIGTERM 结束时，ffmpeg 仍是 T 态，需探针外部精确 PID 清理。
- 当前 `test_reclaim_failure_still_runs_the_original_cleanup_channels` 只注入空服务的 helper 错误，断言 Manager 和服务进程退出，没有活跃 ffmpeg，不能锁住此失败分支。
- 后果：/proc 查询或信号步骤出错时，错误定位会指向服务停止超时，且 owner 的 ffmpeg 可能成为孤儿并继续占用资源。按 internal 测试 harness 的真实范围判 P2；未判 P1。

### P2 — `/proc/<pid>/stat` 解析失败被当成进程已退出

- Spec：进程查询错误与进程确实退出必须分开；只有路径消失/进程不存在才可返回 `None`。
- 位置：[tests/harness/server.py:268]，特别是 `:283-290`。新增文档明确说只有路径消失才返回 `None`，但 `ValueError` / `IndexError` 仍返回 `None`；`_still_running()` 随即把它折叠成 `False`。
- 证据：临时探针令 `/proc/123456789/stat` 的读取返回 `malformed`，观察到 `{"proc_facts":null,"still_running":false}`。这证明解析失败不是 fail-loud。未观察到真实 Linux 内核为存活进程返回畸形 stat；因此不推断触发频率或判 P1。新增测试文件的独立 `_proc_row()` 也将解析错误转成 `None`，缺少针对该负样本的持久回归断言。
- 后果：一旦 proc 内容无法解析，回收循环可能把仍存活的子进程认作已回收，外层观测也会同样误报。

## 不变式与证据

| 不变式 | 代码 / 测试锁 |
|---|---|
| 先回收当前 owner 的直接 ffmpeg 子进程，再停服务；不按名字全局杀 | `tests/harness/server.py:208-265`；`tests/test_harness_shutdown.py:302-361`。真实 T 态 owner 与不同 PPID 的 bystander 同时在场。 |
| 正常空服务、正常上传均不退化 | `tests/test_harness_shutdown.py:261-297`。 |
| 主体失败在独立 pytest 中有界非零退出；pytest 已退出与捕获管道 EOF 分开判断 | `tests/test_harness_shutdown.py:388-445` 使用文件输出和 `Popen.wait()`，分别检查退出码、主体断言、stop 事实及 server/worker/ffmpeg PID。 |
| 跨进程实际 argv 与唯一 marker env 来自真实 producer | `tests/fixtures/harness_shutdown_inner.py:157-162, 205` 写入 `sys.argv` 和白名单 env；父进程在 `tests/test_harness_shutdown.py:390-407, 447-457` 读取 marker 文件并逐字段对照实际传入参数与路径。 |
| helper 撤回、无 PPID 过滤、弱信号变异能触发失败 | 临时进程内变异探测：helper 撤回 → `AssertionError`、root `-15`、ffmpeg `T`；PPID 过滤去掉并将 bystander 纳入候选 → bystander `-9`；SIGKILL 改 SIGTERM → `AssertionError`、root `-15`、ffmpeg `T`。三次均在探针 finally 中按精确 pid 清理。 |

## 限制

- OCR 为 reviewed_fallback，不是 primary reviewed；其 finding 只作候选，以上均由冻结源码和临时探针独立确认。
- 只运行相关测试文件；没有 CI、非 Linux/proc 环境、真实 PermissionError/EIO 或 D 态样本。本 verdict 不推断这些未验证环境。
- 输入隔离偏差：一次宽泛 `rg -C 2` 检索在公开 progress 文件中同时显示了旧阶段诊断文字；之后仅将最新 producer 数据作为运行证据，两项 finding 均从冻结源码和临时探针复核。未打开实现报告或旧 verdict 正文，但本轮的输入隔离纪律有偏差。
- 两项 P2 未扩成生产影响或通用进程管理方案；被审实现未修改。
