# PR82 原始 EOF 节点身份与实测

## 原始收据身份

- 入口核验时 PR82 仍为 open draft，head 为 `fce9131a256a7a8e26a48a0c0882b81444f9ee59`；该对象与本卡固定源码提交一致。
- 原件指针为 `ws15.junit.xml` 与 `std-ws15.json`。收据 `name=ws15`、`rc=1`、`rc_source=process_marker`、执行时长约 262.739 秒。
- 原始 JUnit 实计 503 条：55 failures、24 errors、3 skips；失败/错误共 79 个身份，与 `orig-nodes.tsv` 的 79 个身份集合相等。
- 从原始 XML 的实际消息提取异常类别为 69 `EOFError`、9 `AssertionError`、1 `FileNotFoundError`。原收据版本字段给出 Python 3.12.3、pytest 9.1.1、websockets 15.0.1；原始环境变量收据缺失，不能回推变量值或来源。

## 被选原始节点与消费侧

- 实测候选来自原 JUnit 的真实失败节点：`tests.test_http_file_runner::test_running_job_result_is_not_ready_and_exposes_nothing`。XML `<failure>` 没有 `type` 属性，但 message 本身是 `EOFError`，因此按实际消息分类；不是把缺失类型记作未知异常。
- 该原始 testcase 的 `system-out` 与 `system-err` 均为空，只有 12 字节的异常消息，没有 child traceback 或首次 child 异常证据。
- 节点定义存在于固定提交 `fce9131a256a7a8e26a48a0c0882b81444f9ee59` 的 `tests/test_http_file_runner.py`。fixture `running_runner_server` 使用真实 `multiprocessing.Manager` 和真实 `HttpServer` / `HttpFileRunner`（`core/server/http_file_runner.py`），识别侧是测试用 `run_recording_worker` 子进程；它不启动真实模型，也没有独立服务 launcher 子进程。
- 该 fixture 手动把 fake worker 交给 `ProcessManager` 并调用 `_wait_for_models`；它没有走生产 `ProcessManager.start()` / `start_worker` 的真实模型启动段（`core/server/worker/process_manager.py:25`）。因此实测覆盖真实 manager/队列与 HTTP runner 路径，不覆盖模型子进程启动本身。

## 固定源码复测

- 在隔离 scratch 树上固定 `fce9131a256a7a8e26a48a0c0882b81444f9ee59`，两次有效运行前均记录源码 SHA 和洁净状态。使用冻结 Python 3.12.3 / pytest 9.1.1 / websockets 15.0.1；每次各用独立 `TMPDIR`。原收据的变量值缺失；本次为装载私有旁观插件设置了 `PYTHONPATH`，并设 `PYTHONDONTWRITEBYTECODE=1`，故不声称环境逐键相同。
- 原节点路径在本次同一次 pytest collection 中成功解析并运行：`tests/test_http_file_runner.py::test_running_job_result_is_not_ready_and_exposes_nothing`，1 passed、rc=0。真实 `SyncManager-1` 与测试 worker `Process-2` 均由 pytest 父进程启动、在 `call` 阶段 join、exitcode=0；父侧无首次异常。
- 隔离节点的 Manager 启动记录与 `BaseProcess.start` 的实际 child PID 关联一致。把记录中的 Manager child PID 加 100000 后，关联校验拒绝该证据（负控通过）。
- 因隔离节点为绿，按预算对所属 `tests/test_http_file_runner.py` 整文件、不带 `-k` 运行一次：JUnit 24 passed、0 failed/error/skip，约 60.222 秒、rc=0。记录到 38 次真实 Manager 启动与 38 个测试 worker 启动，Manager PID 关联 38/38；父侧首异常为 0。非零/信号退出只落在名称明确覆盖 crash、timeout、worker crash、未提交持久化与注入后台异常的通过用例中；不能把这些受控子进程退出等同所选原节点的 EOF。
- 测试 fixture 在 pytest 父进程内启动真实 HTTP listener / `HttpFileRunner`，Manager 与 worker 为进程间路径；识别 target 是测试用 fake worker，不是模型。它没有独立服务 launcher 子进程。被测模块的 JUnit `system-out` / `system-err` 合计均为空；旁观器能确认 PID、阶段、join/exitcode 与父侧首次异常，但没有拿到 child 原始 stderr。

## 因果结论与下一步

- 历史机制未复现：相同固定源码上的真实原失败节点单独绿，原所属模块序列也绿。原 JUnit 明确记录 EOFError，但缺少 traceback/child stderr；原收据环境变量来源也未知。当前的两次绿色结果不能解释历史 EOF，也不能宣称根因已修复或 M7 完成。
- 若同一 EOF 在后续受控运行重现，下一张取证卡的精确位置是 `tests/test_http_file_runner.py::running_runner_server`：围绕 `multiprocessing.Manager()` 创建、`worker.start()`、worker `join()` 与 `manager.shutdown()` 收集 Manager/worker 首次 child stderr、父侧实际 EOF 阶段及退出码；不要先改生产代码。当前完整交付验证应等三平台共同正式 SHA 和各自真实环境收据齐备后进行，不重复同一 fce 全量。
