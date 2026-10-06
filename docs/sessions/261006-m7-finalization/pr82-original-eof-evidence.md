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
