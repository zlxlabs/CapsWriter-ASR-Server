# M6 同一隔离服务：并发／取消／重启五轮矩阵

锚点：`goals/http-integration/M6-qa.md`、`docs/sessions/261001-http-files/qa.md`。
本文件只定义**五轮完整矩阵**的循环单元、同服务身份、相位与双消费者；不改 Goal、不把 12 组各再跑五遍。

## 循环单元

具名入口一个：`tests/test_http_qa_repeat_matrix.py::test_five_round_same_service_concurrency_cancel_restart_ws`。

循环由代码常量钉死，不是人工数标签：

```python
REPEAT_COUNT = 5
REQUIRED_PHASES = ("concurrency", "cancel_io", "restart", "legacy_ws")
```

`for round_id in range(1, REPEAT_COUNT + 1)` 每轮跑完整四相位后再写一轮 trace。禁止五个独立 pytest 函数、禁止五个 fresh `data_dir`、禁止「五个异质 job 计数 ≥1」冒充五轮。

12 组普通 suite 仍以 `docs/sessions/261001-http-files/qa.md` 的来源表为准（各组已有真实 producer 测试各覆盖一次）。本矩阵不重跑那 12 组，也不承诺 GiB 级压测。

## 同一服务身份

同服务 = 同配置 + 同源码 + 同一 HTTP `data_dir` + 同一持久 store。五轮共用一个持久根，角色名 `persistent-httpdata`（工件只记角色，不记宿主机绝对路径）。

重启允许主进程 PID 与识别子进程 PID 更换；新旧 PID 必须同时写入该轮 `restart` 相位，且 `pid_old != pid_new`。不能用五个 `tmp_path` fixture 或五个 `ManagedHttpServerHarness.start(data_dir=fresh)` 声称同服务。

`sourceDataDir` 的身份来自真实 producer 的 env / argv（`CW_HTTP_DATA_DIR` 或 harness 启动参数里的 `data_dir`），断言读那份实际传入值，不读测试自己另造的标签。

## 每轮相位（缺一轴即该轮无效）

复用现有 `tests/harness/fake_engine.py`、`tests/harness/worker.py`、`running_runner_server`（QA）与 `ManagedHttpServerHarness`（supervision）。不复制生产方法，不新 Fake HTTP listener，不改 harness。假引擎只证明边界，不是 ASR 质量。

| 相位 | 真实行为 | 证据必须来自 |
|---|---|---|
| `concurrency` | HTTP 与 default-pattern WS（同 state 上的真 `ws_recv`）同时经同一 recording worker / 结果 queue；空 socket 不拦 HTTP；断连 WS 不再出段 | SDK 上传原字节 vs 磁盘；WS 真 frame；`received` 里 Task 的 `owner_kind`/`socket_id`/`task_id`；engine call 计数 |
| `cancel_io` | cancel-first 与 io-first 都在未完成 write 或 I/O worker 屏障下发生；旧 write 完成前槽位不释放；第二 PATCH 不得覆写 prefix | 真实 handler `task.cancel()` + `threading.Event` 屏障；SQLite `confirmed_offset`；磁盘字节；mailbox `_value` |
| `restart` | 同 `data_dir` 上至少一次受控 SIGTERM；新 PID 核对已确认 prefix／未 ACK tail；显式补 suffix（不自动重发 prefix）；已 DONE 新连接领同一 full payload；在途 job → `FAILED[server_restarted]` 且 `received` 已知为空 | 新旧 PID；磁盘 prefix 字节；PATCH offset；`raw_job` / result payload；`list(received)==[]` 作为 known-empty |
| `legacy_ws` | 重启窗口之后 WS 仍能收到对应 `is_final` 结果 | WS 客户端实际收到的 JSON 字段（`task_id`/`is_final`），不是测试手造 dict |

每轮 round/job/idempotency key 必须带 `r{n}`，禁止借上一轮事件用 `>= 1` 通过。

## 工件与两个消费者

调用方必须设置已存在目录 `M6_REPEAT_MATRIX_ARTIFACT_DIR`。测试不得在 env 为空时自选路径。主入口每轮行为断言通过后追加写入 `trace.json`（先写字节再 `replace`）。

字段只含匿名计数 / 角色 / round / phase / pass-fail / 0 skip / `source_runtime` / `source_sha`（40 位）/ producer roles。禁止 credential、token、media hash、私有 env、宿主机路径、IP。

两个消费者读**同一份文件字节**：

1. 测试内 `consume_repeat_matrix_trace(path)`（主入口写完后立刻调）。
2. CI 3.12 job 在 `pytest tests/` **一次**跑完后，用 `importlib` 加载同一函数再读同一路径；不第二次跑该模块（避免 10 轮）。

抽掉第 5 轮、删 `cancel_io` 或 `restart` 相位、或只改 round 标签而不含该轮独特 job id，消费者必须以 `AssertionError` 拒绝。缺 ffmpeg / aiohttp / worker 启动失败：本具名入口 **fail**，禁止 `pytest.skip` / `importorskip`。

py3.11 两维仍只跑 `tests/test_sdk_*.py`，不计五轮。CI 只给 3.12 维加 artifact 目录 env、结构校验与 `upload-artifact`（`if-no-files-found: error`）。测试红可保留部分真实工件；setup 没写出文件则 artifact 步骤 fail-loud。

## 明确不做

不新增产品状态、第二账簿、重试、fallback、任务调度框架、pytest 插件、新依赖。不改 App / SDK / 旧 tests / 配置 / Goal。Win 在飞交付无本矩阵接口依赖；若 master 合入新 App flag 则先 merge 再测，不用旧计数冒充共同源。
