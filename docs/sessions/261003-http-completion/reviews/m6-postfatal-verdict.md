# M6 固定 pin 的 systemd `post_fatal` 缺失核实

failure-visibility: skipped

## 判定

原固定 WebSockets 15.0.1 完整套件有一条红：systemd fatal 清理用例在退出后没有可读到 `post_fatal` 阶段报告。现有证据把失败定位到测试的阶段报告断言，但不足以判断报告未出现是 fatal 等待窗口没观察到事件，还是 JSONL 写入链失败；也不足以把这次红归因为应用生命周期故障。结论是 **skipped**：不判 `clean`，也不判 `p1-found`。

## 对象与版本

- 核查基线：`492fe191e3f9568ea178b61970c732c9d37c4e29`；本 verdict 是该提交之上的唯一新增文档。
- 原运行 source `3d26d90b707003cbbc0b31d8d0e2e1f823f4d2a3` 与候选 `5db84d3f32a3e0530493410a9a8b80e7c6aff925` 的 Git tree 相同（`dc467353149784c39f7858780b5ad0afc34c50d0`）。当前基线的 `core/server/`、`tests/test_http_cleanup.py`、`tests/fixtures/http_fatal_exit_probe.py` 与 source 逐文件相同；代码范围内新增的只有无关的 `tests/test_http_baseline.py` 与 `tests/fixtures/http_baseline_producer.json`。因此没有把 HEAD 号差异当作原因。
- 原 Task09 私有派发记录是 `dlg-20261005-035443-9e4502`，执行器报告标记 `succeeded`；同一报告同时记录了固定 pin 套件 `481 passed, 3 skipped, 1 failed`。执行器任务成功与套件应用结果正交。原派发当时的主干基线不可用，故继承关系未能判定；本核实没有重刷完整套件，也没有把另一个工作树或 CI 结果当成本机应用通过。

## 原运行可证事实

- 保留的原执行器 stdout 仅提取了脱敏断言行：`AssertionError: 没有观察到 listener 监督链上的具体 unlink PermissionError`；源码 traceback 指向 `tests/test_http_cleanup.py:1249`。该行检查的是 `run.reports()` 中是否有 `phase == "post_fatal"`，不是 `denial_records()` 是否命中。
- 按同一测试从上到下的执行顺序，到该断言前已通过：unlink denial 记录非空、`systemd-run --wait` 返回码非零、识别 worker 与 Manager PID 在 15 秒窗口内消失、unit cgroup 无残留、源文件与已完成 Job 结果校验、HTTP/WS 端口拒绝连接。它证明这次退出和资源收尾发生了；它**没有**证明 listener 的 `fatal` 属性确实记录了该 `PermissionError`，因为 `post_fatal` 断言正是负责确认这一点的证据。
- `tests/fixtures/http_fatal_exit_probe.py:90` 的 `emit()` 先向 stdout 写 JSON 并 flush，再对 `CW_PROBE_REPORT` 创建父目录、追加 JSONL、flush 和 `fsync`。`run_fatal_scenario()` 只有在 30 秒窗口内观察到 `app.http_server.fatal` 后才调用 `emit(post_fatal)`；窗口超时的 `AssertionError` 被捕获后直接返回。因此仅凭 nonzero 退出或 stdout 不能区分“fatal 未在窗口内被观察到”和“报告文件追加/flush/fsync 未完成”。
- 测试启动器源代码构造的 argv 为 `systemd-run --user ... --working-directory=<repo> --setenv=<白名单项> <python> -m tests.fixtures.http_fatal_exit_probe`；环境由 `_probe_env()` 逐项构造，键和值都是字符串，包含 `PATH`、`PYTHONPATH`、`PYTHONUNBUFFERED`、`CW_ADDR`、`CW_PORT`、`CW_PROBE_MODE`、`CW_PROBE_LOG`、`CW_PROBE_WAV`、`CW_PROBE_REPORT`、`CW_PROBE_DENIAL_LOG`、`CW_HTTP_PORT`、`CW_HTTP_DATA_DIR`。这是 producer 源码契约；保留的原运行材料没有实际 argv/env 值记录，不能把源码构造冒充为原进程的实测环境。
- 原 delegate 目录只保留了报告、envelope 和 stdout 等派发产物，没有 `probe-report.jsonl`、`probe-denial.jsonl` 或探针进程日志。原 pytest `tmp_path`/`TMPDIR` 的精确根路径未在安全元数据中保留，所以没有在 `/tmp` 扩大搜索。测试 transient unit 名由 pytest PID 和 UUID 生成，原记录未保留该 unit 名或其 `ExecMainStatus/Result/Signal`；`delegate-dlg-20261005-035443-9e4502` 是执行器 unit，不是 fatal 测试 unit。对已回收的 delegate unit 查询得到 `LoadState=not-found`，其余默认状态值不作为 fatal 运行证据。

## 单次受控探针

- 隔离环境使用 Python 3.12.3、pytest 9.1.1、pytest-asyncio 1.4.0、WebSockets 15.0.1；未改仓库依赖或测试文件。
- 只调用了 `test_fatal_cleanup_exits_process_and_reaps_children[systemd-unit]`。用例的真实消费环境门禁调用 `systemd-run --user --quiet --wait --collect --service-type=exec /bin/true`；它返回非零，fixture 将 systemd 参数标为 skip。机器有 ffmpeg，但 user systemd 状态为 degraded。pytest 输出为 `1 skipped in 0.09s`，调用退出码 4（目标参数在 skip 后没有 collector）；fatal fixture、应用进程和 fatal unit 均未启动。
- 该探针只证明本次环境不能执行 systemd fatal 用例；不用于补写原运行输入或解释原 `post_fatal` 缺失。按任务约束没有重试，也没有再跑其他 fatal 变体。

## 应用链与 P1 两问

- 应用链源码：`core/server/http_server.py:281-298` 的周期清理 task 将异常交给 `_on_source_cleanup_done()`，再调 `_mark_fatal()`；`core/server/app.py:195-218` 汇总监听任务失败，`start()` 进入 `_drain_after_fatal()`，由 `stop()` 收回识别 worker、HTTP runner/worker 与 listener，再以非零状态退出。测试 fixture 正是要验证这条链。源码链存在不代表原运行已证明走完该链；缺少的正是原 `post_fatal` 事件及 transient unit 时间线。
- 真实使用是否触发：没有真实部署记录证明生产清理遇到过该 `PermissionError`；目前只有测试 fixture 对具体源文件注入该异常，P1 第一问不成立。
- 后果是否不可接受：已观察到的测试控制流通过了非零退出、子进程消失、cgroup 清空、数据保留和 listener 关闭；缺报告本身降低诊断能力。但因为未证明原 listener 收到的异常类型和 fatal 时间线，无法排除其余应用路径，P1 第二问不能完整裁决。
- 所以没有足够证据判应用生命周期 P1，也没有足够证据判干净或仅为已解释 flaky；机读 verdict 保持 `skipped`。

## 最小后续边界

只在 user systemd 可通过同一 `/bin/true` 门禁的真实消费环境，单次运行这个 fatal 参数化用例；保留该次 `tmp_path` 下的 `probe-report.jsonl`、denial/process 日志，以及 fatal transient unit 的 `ExecMainStatus/Result/Signal` 和 PID 时间线。先确认是否产生 `post_fatal` stdout 行，再检查对应 JSONL append/flush/fsync 的实际错误。若证实应用收到 fatal 但 fixture 报告未落盘，修复边界在测试报告生产/同步；若证实 listener 未观察到该异常，再以实测应用路径定位。当前不修产品、不改测试，也不扩跑完整套件。
