# M6 工件收口（合格分层，不宣称 Goal 完成）

本卡 **qualified 通过**：无会话五轮补上实际 `env -i` 运行链；c6 双臂全量 JUnit 与 12 组具名样本保持为已审产物（归属 Task `20261006-04` / `dlg-20261005-175500-b9df8a`）。
不改 App / test / CI / 配置 / 依赖。Draft PR #83 仍未批准，不 Ready、不 merge、不 Gate rerun。
schema 通过 ≠ 五轮认证。M6 Goal **未标完成**。假引擎不是 ASR 质量。

## 1. 来源分层（不要混成一条链）

| 层 | SHA / 身份 | 证明什么 | 不证明什么 |
|---|---|---|---|
| CodeH2 | `77940745146d377d780e1f840bfbfd633740c114` | 五轮矩阵实现 + schema-only 消费者 | 当时没有全量 JUnit；不 retro |
| 83 DocHead（本卡之前） | `f38213085b530a1acb8a51816770a40a2bcc4b44` | 已审治理/审查 Doc | 指定树无裸运行链；声称仍 unknown |
| c6 套件证据 | `c6a17380c441263de05399977f8b1228ffd1682a` | 新时点双臂 full XML | 继承环境，不能充 bare |
| 本卡 | c6 之上仅两份新 Doc + 实际 c6 裸跑 | child 会话键空；trace SHA=c6 | 不重跑 Hosted；不修 P2 |

nonDoc **340** 在 779 / f382 / c6 相同。
合法不同 H1 树 `6b129a73…` ≠ H2 树 `e260c171…`；坏引用 `cat-file` 128。
两臂 XML 都是 65318 字节，摘要不同：pin `7e68c487df3e13b3…`，unpin `fc51cb20fe528ffc…`。
stdout 摘要也不同。pin websockets **15.0.1**，unpin **17.2**（`importlib.metadata` 实采）。
pin stdout 末行 `511 passed, 3 skipped, 195 warnings in 436.93s`；unpin `410.39s`。
本卡不覆写 f382「当时缺 JUnit」那一句。

## 2. 12 个 Source Spec 具名节点（直接查 XML）

未调用 `map_groups.py`，不用 helper 宽闭包当语义证明。
pin JUnit：`tests=514`、failures=0、errors=0、skipped=3；推导 passed=511。
三条资源 skip，与源码行一致、非 HTTP：

- `tests/test_aligner_integration.py::test_aligner_loads_not_fallback`（`:53`，ForceAligner 后端/模型）
- `::test_aligner_produces_token_timestamps`（`:62`，同上）
- `tests/test_segmenter.py::test_vad_pipeline_smoke`（`:208`，silero-VAD / onnxruntime）

组间样本可重叠，不可把各列相加当总量。组 10 必须是 PCM oracle，组 11 必须是末段 finalfail。

| 组 | Spec 语义 | 具名 node | 样本 | 状态 |
|---:|---|---|---:|---|
| 1 | SDK PATCH / 落盘 SHA | `test_real_sdk_upload_bytes_match_server_disk_sha` | 1 | passed |
| 2 | 跨连接领取 | `test_real_container_upload_then_other_connection_takes_done_result` | 4 | passed |
| 3 | 丢 202 恢复 | `test_lost_commit_response_recovers_with_exactly_one_recognition` | 1 | passed |
| 4 | 未确认后缀 | `test_resume_after_failed_patch_only_sends_unconfirmed_suffix` | 1 | passed |
| 5 | SIGTERM 重启 | `test_sigterm_exits_zero_and_restart_marks_server_restarted` | 1 | passed |
| 6 | GET 持久 payload | `test_result_producer_payload_and_done_survive_new_process` | 1 | passed |
| 7 | 同 worker HTTP+WS | `test_real_ws_and_http_share_one_worker_without_key_pollution` | 1 | passed |
| 8 | 取消/IO 交错 | `test_handler_cancellation_and_io_completion_orders_preserve_confirmed_bytes` | 1 | passed |
| 9 | 容量（缩小常量，非 16 GiB） | `test_concurrent_http_commit_respects_budget` | 1 | passed |
| 10 | **PCM oracle**（`Task.data` / 16k mono f32） | `test_resampled_sources_produce_bounded_16k_mono_f32_segments` | 2 | passed |
| 11 | **finalfail**（末段失败不发布 partial） | `test_final_segment_failure_fails_job_without_publishing_partial` | 1 | passed |
| 12 | 五轮 + 旧 WS | `test_five_round_same_service_concurrency_cancel_restart_ws` | 1 | passed |

producer 边界：PATCH body、落盘 SHA、ffmpeg argv、磁盘字节、GET/WS 真对象。12once 来自这套 full XML，不是再跑 12×5。
裸五轮见 `m6-bare-shell-retained-evidence.md`，与 Hosted 五轮不是同一次运行。

## 3. collector 负控 ≠ 矩阵 TDD；c6 §6 消歧

对 XML **副本**（原件未改）：NC0 原件 **accepted**；注入真实 failure、删除映射 node、给 HTTP 侧打关键 skip、截断映射指向缺失文件，均 **reject**。
这一层只证明采集器，不是矩阵 AssertionRed，也不改仓库测试。
P2 仍 backlog：简单 duplicate ID 会挡住「ID 必须含 `r{n}`」；去掉 `rContains` 后仅 unique 的 fixture 仍绿。
c6 `m6-retained-suite-evidence.md` §6 把「全重标 clone 仍被 schema 消费者接受」标成 **B 范围局限**。
那是可证性边界，不是待做的反伪造功能，不要升成新防御 P2。本卡不修 CI 测试。

## 4. 原保 unknown / 明确不做

- 原 30 缺 JUnit 时点不追认。
- `dlg-20261005-183710-6a1454` TIMEOUT、报告 0、暂存「文档交付完成」≠ 合格交付；envelope unknown 原保。
- `dlg-20261005-164121-c35048` `died_unknown` 与报告自报 succeeded 并存，不重签。
- 47 轮 wrapper 在收集前 uv 拒绝（argv 引号，无 JUnit）原保。
- Hosted `37339081182` / artifact `11356924649` / checkout `8f9a0ec4` / gate `37349915275` 只作已有 Src；不重下、不抬旧 H1 `f99`。
- 16 GiB 物理上限、三平台容器、生产 `CapsWriterServer`/`SocketManager` 全装配、真 ASR 质量：unknown。
- 不改 Goal 索引。私有 XML 目录不入库。
