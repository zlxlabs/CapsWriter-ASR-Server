<!-- delegate-outcome: succeeded -->

# M6 十二组 QA 独立终审 verdict

failure-visibility: p2-only

## 固定审查对象

- 冻结范围：`5134720e058e0e9ae3d3feddebf4942f8bf7ed7a..1cd07fe7b4f474269081b698ff7b7c928d7d9b75`。
- 审查结论：通过，无阻塞 finding；仅 1 条 P3 测试路径重复计算摘要，接受不修。
- 不读取 `m6-qa-evidence.md`、实现 progress/report、前 review/verdict（含 AA39）或真实音频。原始设计/QA 与当前 QA 索引只用于定义十二组合同及定位测试；结论来自源码、consumer tests 和本次运行。

## 本文件的来源声明

以下「十二组 consumer 索引」与「本轮实测 / 反向变异 / 限制」各节，是把该轮**独立冷审报告**中已经交付的事实转录进本仓，供维护者直接 `git` 查阅：它们**不产生新的审查结论**，不重跑实验、不改判级、不改固定 SHA、不改 result。本文件不新增事实源或抽象；引用的一切判据都在本仓路径内可查，逐字节原件留在内部交接区。

## Finding 与分诊

| 位置 | 工具候选 | 本仓定级 | 两问与处置 |
|---|---|---|---|
| `tests/harness/worker.py:63-66` | OCR `low / maintainability`：同一 `Task.data` 连续计算完整 SHA-256 与前缀 SHA-256 | P3，接受不修 | 真实触发：是，每个被记录的 worker Task 都执行；后果可接受：是，仅测试 harness 多做一次散列，不改变结果、协议或生产服务。记录为低优先级 backlog，不阻塞。 |

## 十二组 consumer 索引（转录既有冷审报告，不产生新的审查结论）

| 组 | 被测代码入口 | consumer 测试（本仓可直接查） | 实际 producer 来源 | 本轮真实证明 | 未测边界 |
|---|---|---|---|---|---|
| 1 二进制上传 | `sdk/capswriter_asr/http_client.py::_finish_upload`；`core/server/http_server.py` PATCH 路由；`core/server/http_store.py` 写入 | `tests/test_http_qa_e2e.py::test_real_sdk_upload_bytes_match_server_disk_sha`；`tests/test_http_client.py::test_cli_submit_subprocess_emits_real_http_requests_and_no_token`；`tests/test_http_file_tasks.py::test_sdk_upload_reaches_disk_then_commit_is_explicitly_unavailable` | SDK 经真实本机 TCP 转发器发 PATCH；服务端磁盘文件为真实 producer 产物 | PATCH body 按 `Upload-Offset` 逐块拼接后与源 bytes 相等；服务端磁盘文件逐字节、长度、SHA 与 SDK 声明一致；CLI 用例从真实子进程发请求并按源切片断言 body。systemd 归档了合成 PATCH body 合并件 90,513 bytes，SHA-256=`0b32278a4eaf0040daf3b7c718f65aef52f875543686f26e107c93d43d311c9d` | 合成容器；生产部署与真实录音未测 |
| 2 受理后断连领取 | `core/server/http_file_runner.py` 结果 sink；`core/server/http_store.py` 结果读取；SDK `get_file_result_http` | `tests/test_http_file_runner.py::test_real_container_upload_then_other_connection_takes_done_result`（mp3/aac/m4a/opus）；`tests/test_http_file_tasks.py::test_persisted_done_result_is_served_after_reopen` | 识别 worker 实际发出的最终 `Result` | 上传调用结束后用**新的** HTTP 请求领取结果；存储 payload 与 worker 实际发出的 `Result` 字段、tokens、timestamps 逐项比对。旧客户端连接与运行态 owner 不作为结果来源 | 结果字段来自可编程假 ASR，不证明识别质量 |
| 3 幂等与显式恢复 | SDK `_request`、`_commit_upload`、`resume_file_http`；server/store commit | `tests/test_http_qa_e2e.py::test_lost_commit_response_recovers_with_exactly_one_recognition`；`tests/test_http_client.py::test_lost_confirmation_requires_explicit_resume_without_restarting_prefix`；`tests/test_http_file_runner.py::test_repeated_commit_returns_same_job_without_resubmitting` | 真实 HTTP server + SQLite；丢响应由客户端 transport 侧注入 | 客户端在真实 httpx send 收到 202 后丢弃响应：库中只有一个 Job，恢复阶段只有 GET，解码一次、Job/结果各一条、worker 段数与单次识别一致 | 真实网卡/远端网络故障无部署验证 |
| 4 可信续传 offset | SDK `_finish_upload` 的 seek/确认 offset；`HttpStore.append_bytes` | `tests/test_http_client.py::test_resume_queries_offset_and_only_sends_remaining_source_bytes`；`tests/test_http_file_tasks.py::test_resume_after_failed_patch_only_sends_unconfirmed_suffix` | 真实 HTTP 服务，第二个 PATCH 注入 I/O 失败 | 恢复时只发送未确认后缀，确认字节计数为 `size-2048`；最终磁盘 bytes 等于源文件，SQLite offset 与 COMMITTED 状态匹配 | 中断点由本地服务 fault injection 控制；生产网络中断频率未量 |
| 5 部分上传跨重启 | `HttpStore` 启动恢复；`HttpServer` 进程监督与 offset 持久提交 | `tests/test_http_supervision.py::test_http_offset_crash_windows_recover_in_new_processes`；`tests/test_http_file_runner.py` 的 SIGTERM/崩溃重启用例；`tests/test_http_store.py::test_restart_converges_queued_and_running_but_keeps_partial_and_done` | POSIX 自有 server 子进程分别在文件 fsync / offset 提交 / ACK 窗口被终止 | 新进程查询确认 offset，并以真实磁盘 bytes/SHA 校验未确认尾与确认前缀；不是同进程对象复用 | 仅当前 Linux/POSIX 环境；其他平台重启语义未知 |
| 6 结果跨重启 | `HttpStore` 结果事务/读取；HTTP job/result handler | `tests/test_http_supervision.py::test_result_producer_payload_and_done_survive_new_process`；`tests/test_http_cleanup.py::test_periodic_cleanup_waits_for_real_runner_reference_then_keeps_result` | server 子进程把实际 producer payload 写入契约文件后被终止 | 新进程 `GET result` 与 producer 文件逐字段相同；源删后结果仍可读 | producer 用假引擎，不证明真实模型结果质量 |
| 7 双 owner 并发 | `core/server/state.py::derive_owner_id/make_task_key`；`TaskHandler._owner_is_active`；WS 收发与 `HttpFileRunner._submit` | `tests/test_http_qa_e2e.py::test_real_ws_and_http_share_one_worker_without_key_pollution` | 真实 multiprocessing Queue + worker 子进程 + Result Queue | 同一轮真实 WebSocket 与 HTTP listener 共用同一 worker：实际接收的 Task 区分 `owner_kind/socket_id/task_id`，HTTP 只入库，WS 只回自己的 task；另测空 WS socket、断开后清理使 worker 不再收到其段。该窄场景额外独立运行 5 次，5/5 通过 | 合成确定性音频与假引擎；不代表并发规模或生产识别质量 |
| 8 取消与 I/O 交错 | `HttpServer` handler；`HttpIoWorker` mailbox；`HttpStore.append_bytes` | `tests/test_http_file_tasks.py::test_handler_cancellation_and_io_completion_orders_preserve_confirmed_bytes` | 真实本地 TCP PATCH，分别跑 cancel-first 与 I/O-first 各 5 轮 | 核对 route 被取消时 mailbox 槽位是否仍占用、DB confirmed offset、磁盘实际 bytes；随后 GET/PATCH 仍拿到可信 offset | 短确定性载荷 + 屏障注入，不是磁盘压力测试 |
| 9 final 与资源边界 | `HttpStore` 文件/结果/物理余量 guard；`HttpServer` admission/共享准入 | `tests/test_http_file_tasks.py::test_negative_matrix_keeps_old_bytes`、`::test_upload_identity_and_limit_validation`、共享准入并发用例；`tests/test_http_capacity.py` 物理余量与重启用例 | 真实 HTTP 响应与 SQLite 状态 | 错 offset、Content-Encoding、无长度、块大小、文件身份、准入/结果预留等错误边界显式返回，旧 bytes 不被覆盖；容量阈值用缩小常量/monkeypatch 验证边界类别与等值放行 | 1 GiB 单文件、16 GiB source 预留、2 GiB DB/WAL/SHM 等真实体量未压测；绝对物理容量与真实吞吐未知 |
| 10 解码与 PCM | `FileSourceDecoder`；`HttpFileRunner._submit`；共享 `PcmSegmenter`；`tests/harness/worker.py` | `tests/test_http_qa_e2e.py::test_resampled_sources_produce_bounded_16k_mono_f32_segments`（44.1 kHz stereo、8 kHz mono 两参数） | 系统 ffmpeg 真实进程作独立参照；worker 侧来自子进程 `queue_in.get()` 收到的真实 `Task.data` | 每段完整 SHA 与独立 ffmpeg 参照中对应 offset 的 bytes 相同；offset 为 0/5/10/15 秒、overlap=1 秒，前三段 96,000 samples/384,000 bytes，末段 80,000 samples/320,000 bytes 覆盖到 20 秒。真实 ffmpeg argv 形如 `-i <服务端 sources/*.bin> -ar 16000 -ac 1 -f f32le pipe:1`，进程 rc=0，且断言 PATH 首项为 shim 目录、存在合成 env marker | 见下方「fork 计数归零」限制；真实平台容器/模型未知 |
| 11 整任务失败与监督 | `TaskHandler.handle_audio_task`；`HttpResultSink`；`HttpFileRunner.fail_job` | `tests/test_http_qa_e2e.py::test_final_segment_failure_fails_job_without_publishing_partial`；`tests/test_http_file_runner.py` 中间段、ffmpeg 失败、结果超限与未知后台异常用例 | 真实 worker 子进程最后一次推理调用失败 | 前段确有 Result，任务终态为 FAILED/inference_failed，results 表没有已发布的完整结果，`GET result` 返回 409；owner 释放且事件循环仍可工作 | 注入的是假引擎末段推理异常，不是 ASR 模型质量测试 |
| 12 源清理与旧 WS 兼容 | `HttpStore.cleanup_terminal_sources`；server 周期清理；runner 活跃 source 引用 | `tests/test_http_cleanup.py::test_store_cleanup_uses_terminal_boundary_and_keeps_every_other_source`、`::test_periodic_cleanup_waits_for_real_runner_reference_then_keeps_result`；容量重启用例；全量旧 WS 回归 | 数据库中的终态/活跃引用/partial/未登记文件与 result 状态 | 终态、活跃引用、partial、未登记文件和 result 的保留/删除分别核对，清理后旧结果可读；完整 consumer suite 含旧 WS health/backpressure/error/protocol/segmentation 用例并两套版本通过 | 通过数据库时间推进验证边界，不等待真实 7 天；真实平台生命周期未测 |

### 组 10 的归档限制：fork 计数归零，raw 原件未落盘

systemd 侧车的 `itertools.count()` 在两个 fork 子进程里各自从 0 起，第二种格式的原始 worker PCM 文件**覆盖了**第一种格式的同名文件。留下的事实是：第一组逐段完整 SHA 与独立参照 `reference-stereo44.f32le` 的切片重算后全部相同；第二组原始 PCM bytes 也逐段与 `reference-mono8k.f32le` 相同；两组真实 Task 完整 SHA 仍在 `worker-tasks.jsonl`。第一组 raw `Task.data` 文件本身**未保留**——本文件不把重建的参照切片称作原始 producer bytes，也不声称原始 payload 已全部落盘。限制属于归档形态，不是消费约束被突破（测试内的内容比较断言通过）。

## 本轮实测（同样转录自既有冷审报告）

- **完整消费矩阵**：按 `docs/development/testing.md` 的完整命令 `python -m pytest tests/ -q -p no:cacheprovider`，在两个全新 Python 3.12.3 隔离环境（不用仓库主 venv，依赖与 CI 矩阵一致：`aiohttp==3.14.3`、`httpx==0.28.1`、`pytest==9.1.1`、`pytest-asyncio==1.4.0` 加 ffmpeg）各跑一次：`websockets==15.0.1` → **457 passed, 3 skipped, 163 warnings, 216.22s**；版本解析到 `websockets==17.2` → **457 passed, 3 skipped, 163 warnings, 227.25s**。163 条 warning 主要是当前 Python multiprocessing fork 与 websockets deprecated 属性提示，不是失败。
- **systemd env-i 整文件消费**：独立 user unit 在 systemd cgroup 内用 `/usr/bin/env -i` 起进程（有效 PATH/HOME/PYTHONPATH 与包版本已留存），命令 `python -m pytest tests/test_http_qa_e2e.py -q -p no:cacheprovider -p m6_capture_plugin` → **6 passed, 0 skipped, 8.79s**，`Result=success / ExecMainStatus=0`。即新增 M6 文件零 skip 执行。
- **证据目录**：真实 TCP PATCH body、offset/长度/SHA 清单、两种生成源容器、独立 ffmpeg 解码参照片、worker 收队列后记录的字段与 SHA、ffmpeg argv/env/rc 均在内部交接区的独立目录，**路径不公开**；需要逐字节原件请向交接方索取。本仓可读的是上表的测试约束与下列结论。
- **反向变异（两项合格的最小 AssertionError）**：均在以 `5134720` 为 base 的一次性 scratch worktree + 独立 venv 运行，退出前恢复单处源文件，主审 worktree/main venv 未改。① 把 `HttpFileRunner._submit` 送队列的 `Task.data` 改成同长度全零 bytes（offset/样本数不变）：确认注入行命中后，两个格式都在「参照 SHA == worker 记录的 data SHA」比较处 AssertionError——测的是实际跨进程 payload 内容，不是 observer 改字段。② 在 SDK `_request` 的 TransportError 路径注入一次真实 commit POST 重发（fault injector 只丢首个 commit response，第二个 POST 真到 HTTP server）：测试在实际请求计数断言处 `assert 3 == 2` 转红。
- **未计入的探索性变异**：初次 SDK 重试变异因 fault injector 每次 commit 都丢响应，表现为 RemoteProtocolError 而非 AssertionError，改为单次丢弃后才得到上述合格红验；另一次把 HTTP `socket_id` 改成非空触发真实 `derive_owner_id` fail-fast 与 worker 退出，但测试停在 Queue teardown，未命中目标 owner 断言，故不计数。进程处理上只终止了自己确认归属的 scratch pytest 进程，未向 delegate、父进程组或他人进程发信号。
- **OCR 前置扫描**：受输入限制，只在独立 scratch commit 上扫描 `tests/test_http_qa_e2e.py` 与 `tests/harness/worker.py` 的代码 diff，未把受禁文档交给 OCR；`status=reviewed`、`reason=primary_selected`、`coverage=complete`、`confirmed=1/refuted=0`。模型给出的 `low` 是候选输入，本仓定级与 P1 两问结论见上表。

## 限制与未知（不因转录而消失）

- **3 个 skip 名称未保存 = unknown**：两套完整 suite 各 3 skipped，但消费命令未列出用例名，该轮未重跑套件追名；**不得套用其他波次的 skip 名单**。新增 M6 文件已由完整套件与 systemd 单文件两次覆盖，没有 HTTP/aiohttp 缺失类 skip。
- 真实 ASR 模型、真实录音、macOS/Windows/Linux 三平台的质量与字节基线未测；本轮用确定性合成输入、真 ffmpeg、真网络/SQLite/worker 与假引擎，不宣称识别质量通过。
- 资源边界只验证缩小常量与类别阈值；1 GiB 单文件、16 GiB source 预留、2 GiB DB/WAL/SHM 的实际体量、吞吐与长期占用未压测。
- 继承红：派发卡的主干基线为 `gh api request failed`，因此「继承红」**未能判定**。两套未变异全量测试没有失败；scratch 中的预期 AssertionError 只算变异证据，不归为自然新红。

## 接手现场与四问（转录）

无交接单。本仓开放 issue inbox 有 #61 容量口径、#57 未入库 tmp 证据、#56 跨 ffmpeg 版本、#52 SDK 多音轨转码、#43 SDK 容器时长；#61/#56 与本轮物理容量/ffmpeg 未知相邻，但该轮不跨仓派修复或关闭 issue。欠账探针为 `orphan 0 / owned 0 / stale-over-7d 0`；memory 报告探针返回 `memory_dir_mismatch`，无法判定，不写成零。

1. **审查对象是否固定且未漂移？** 是，审查只针对 `5134720..1cd07fe`，该轮后续 commit 仅新增 review progress/verdict。
2. **十二组关键证据是否由真实 producer/consumer 锁定？** 本地测试边界中是，逐组见上表；资源绝对体量、真实 ASR 与真实平台仍按未知处理。
3. **是否有 internal P1？** 没有。唯一 finding 在测试 harness 每次触发但后果可接受，未满足 P1 两问。
4. **该轮可完成的实际限制是什么？** systemd stereo raw payload 侧车有覆盖，worker 完整摘要与参照 slice 仍逐段匹配；3 个全 suite skip 名称未回查；派发 baseline API 不可用。
