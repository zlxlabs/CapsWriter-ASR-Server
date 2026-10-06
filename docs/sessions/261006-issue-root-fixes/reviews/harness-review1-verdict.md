# #85 测试 owner 资源回收：独立审查 1

冻结对象：`e849c21748392ad848131e07ff17d32e4cc83a8b..482cf9ae720efb512d5c42b79943c3f4bdacc7f1`。风险档 internal；仅审上述新增 diff，不含后续提交。

failure-visibility: p2-only

## 结论

发现 3 项 P2 和 1 项非行为性 P3 验证问题。新测试在本机 Linux/Python 3.12 上通过，三种指定代码变异均由相关断言转红；这些结果不覆盖下列查询错误与子进程参数契约缺口。没有 P1。

## Findings

### P2：解码子进程回收失败会跳过服务主进程和 Manager 清理

- **Spec**：主体失败不能被 teardown 二次失败覆盖；服务主进程、ffmpeg 和其他 owned 资源必须回收。
- **位置**：`tests/harness/server.py:210`，回收超时抛错处在 `tests/harness/server.py:255`。
- **证据与后果**：`stop()` 在发送服务停止信号、join/terminate、关闭队列和 `manager.shutdown()` 之前直接 await 回收 helper。helper 在 SIGKILL 后仍看到存活 PID 会抛 `AssertionError`；`os.kill` 的其他 `OSError` 也会直接上抛。该异常使剩余 owner 清理全部跳过。已有消费者如 `tests/test_ws_progress_watchdog.py:385` 和 `tests/test_error_contract.py:198` 在裸 `finally` 中调用 `stop()`，没有第二层 owner 清理。
- **判级**：P2。此轮没有观察到 SIGKILL 后进程仍存活；触发后果限于测试 harness 的 teardown 和资源残留，未证实生产服务受影响。

### P2：/proc 查询错误与进程已退出被折叠

- **Spec**：Root_PID ownership 必须来自实际进程事实；查询错误和进程已退出须分开。
- **位置**：`tests/harness/server.py:263`，相同判据也复制在 `tests/test_harness_shutdown.py:53` 与 `tests/fixtures/harness_shutdown_inner.py:42`。
- **证据与后果**：三处均把所有 `OSError`（包括 `PermissionError`、I/O 错误）变为 `None`；`_still_running()` 因而把查询失败当作已停止，`_decoder_children()` 会跳过无法读取的条目，测试里的回收断言也会把无法查询当作 PID 消失。scratch 探针将 `/proc/<pid>/stat` 读取注入已知 `PermissionError`，实际得到 `AssertionError: query error collapsed into process-gone value: None`，证明这不是恒真判据。
- **判级**：P2。当前真实测试环境可读 Linux `/proc`，自然发生权限/I/O 错误未测得；但错误输入下的判定已实证错误，并可能漏杀、过早返回或假报回收。

### P2：跨进程测试未断言子进程实际 argv/env

- **Spec**：跨进程回归须断言 producer 实际 argv/env 与 marker 文件 payload，不能只靠同进程状态。
- **位置**：`tests/test_harness_shutdown.py:369`、`tests/test_harness_shutdown.py:375`、`tests/test_harness_shutdown.py:399`。
- **证据与后果**：父进程确实通过 `Popen` 传入 pytest argv 和 marker env；子进程也把 JSON 写到磁盘，父进程读取并断言事实字段。因此跨进程执行与 marker 内容有覆盖。但 marker 不记录子进程实际 `sys.argv`/相关 env，测试也不比较实际 argv/env payload；这些参数之后即使漂移，只要仍偶然完成主体与 marker 流程，用例没有直接契约断言。
- **判级**：P2。属于本卡明确要求的回归证据缺口，不表示当前 `Popen` 调用已观察到错误。

### P3：冻结 diff 的空白检查未通过

- **位置**：`docs/sessions/261006-issue-root-fixes/progress/harness-shutdown-progress.md:105`。
- **证据**：`git diff --check e849c21748392ad848131e07ff17d32e4cc83a8b 482cf9ae720efb512d5c42b79943c3f4bdacc7f1` 输出 `new blank line at EOF`。这是文档尾部空白，不影响运行；本卡只允许新增 verdict，故未改被审文件。

## 不变式与测试锁定

- owner 子进程只按 `/proc` 实读的 `comm=ffmpeg` 与 `ppid=server_pid` 选取：`tests/harness/server.py:283`。暂停子进程、同名旁观进程、正常上传和空服务对照由 `tests/test_harness_shutdown.py` 的 4 项对应测试覆盖。完整文件基线 `5 passed`。
- 回收边界有效性实测：移除 helper 后 `3 failed, 2 passed`，失败为具体 `AssertionError`；取消 PPID 条件后 `1 failed, 4 passed`，报旁观 ffmpeg `exitcode=-9`；将 SIGKILL 弱化为 SIGTERM 后 `3 failed, 2 passed`，断言实际仍为 `('ffmpeg','T',ppid)`。均未以导入失败或脚本崩溃作红验。
- 独立 pytest 主体失败、marker 事实和服务/worker/ffmpeg PID 回收由 `tests/test_harness_shutdown.py:361` 锁定。基线 marker 为 267 字节；记录到 ffmpeg 的真实 T 态及 owner PPID、`stop_error=null`、`stop_seconds=0.07`、服务退出码 0，且测试结束后三个精确 PID 均不在 `/proc`。stdout/stderr 写文件并用 `inner.wait()` 判断 pytest PID，未把管道 EOF 当进程存活。
- Linux/proc 范围由回收函数的非 Linux 空结果说明及测试 `skipif(sys.platform != "linux")` 明示；本机运行的是 Linux/Python 3.12。查询错误区分目前没有有效回归测试，见第二项 finding。

## OCR 与验证

- OCR envelope：`status=reviewed`、`profile=minimax`、`model=MiniMax-M3.1-Flash-Preview`、`coverage=complete`、2 条 finding 均经工具子验证标为 confirmed；我只把它们当候选，按上文独立核对并均判 P2。
- OCR 严重度复判：

  | OCR 候选 | 工具标注 | 本仓判定 | 本机真实触发及后果 |
  |---|---|---|---|
  | helper 异常跳过其余清理 | high | P2 | 本机 Linux/真实 pytest 路径已跑；回收异常未自然触发。触发后可能遗留测试子进程与 Manager，不影响已证实的生产服务路径。 |
  | /proc 查询错误折叠 | medium | P2 | 当前 /proc 可读；注入 PermissionError 后判据错误已实测。自然触发未测得，影响限于 harness 回收与测试判定。 |
- 实际命令：`ocr-review --repo "$PWD" --from e849c21748392ad848131e07ff17d32e4cc83a8b --to 482cf9ae720efb512d5c42b79943c3f4bdacc7f1 --audience agent --concurrency 4 --background-file /tmp/capswriter-harness-review1-dlg-20261006-042521-3e0f74/spec-summary.md`。摘要 1,115 字节；OCR 主腿 elapsed 699.216 秒，未设置外层 timeout。
- 实际窄测：`python3 -m pytest -q tests/test_harness_shutdown.py --basetemp=/tmp/capswriter-harness-review1-dlg-20261006-042521-3e0f74/pytest-basetemp` → `5 passed, 8 warnings in 7.08s`。未运行本机全量 suite 或 CI。
- 查询错误已知坏态探针在补入仓库 `PYTHONPATH` 后得到上述预期 `AssertionError`；首次从 scratch 直接运行时因 Python 搜索路径不含仓库而报 `ModuleNotFoundError`，不是被测结果，随后用真实仓库路径重跑。
- 基线 GitHub 查询在派发时不可用（`gh api request failed`），继承红未能判定；未据此推断 CI 状态。未动态制造真实 `/proc` I/O 故障或 SIGKILL 后 D-state 进程。
