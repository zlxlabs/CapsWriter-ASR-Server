# M6 H2 有界证据归源与正常交付

CodeHead = `77940745146d377d780e1f840bfbfd633740c114`。本卡只复制已审治理/审查 Doc，不改 py/yml/config/test/harness，不宣称 Goal 完成、不修 Windows、不谈 ASR 质量。Draft PR #83 未批准。schema 通过 ≠ 五轮真实执行。

## 1. 主干与非 Doc 同源

`git ls-remote origin refs/heads/master` 非空，仍为 `6aa76f6c6935e9cef00afc1bcbcf8327e7c95488`。`6aa` 是 H2 祖先，无需为对齐而 merge master。H2 不是 `6aa` 祖先（实现差在 PR 分支上）。CI merge checkout `8f9a0ec4ade6f995a5f149b9f8278bde5787f941` parents=`6aa`+H2，tree=`e260c171001c9f56ee94adc4cf572022ddae91fe` = H2 tree。GH recursive `truncated=false`，blob=475 / object=578，集非空。已知否定：H1 tree `6b129a73…` ≠ H2；坏引用 `git cat-file` 退出 128。新 Doc 落地后 nonDoc 仍应 exact CodeH2。未发现 master 在 `6aa` 之后的代码增量，不重跑第三套 full。

## 2. 原 30 与双臂 / 裸产物

原 30 报告与 envelope 只作定位，不当计数源。本卡亲取 owned 工件：

| 臂 | source_sha | runtime | rounds | ffmpeg 事件下标 / start | io-first pending/mailbox/held | cancel-first | WS-live |
|---|---|---|---:|---|---|---|---|
| 裸 `env -i` | H2 `779…` | python-3.12 | 5 | 0,7,14,20,27 / 4,4,3,4,4 | 0/32/false | 1/31/true | true×5 |
| 全量 pin 15.0.1 | H2 `779…` | python-3.12 | 5 | 0,7,14,21,28 / 4,4,4,4,3 | 同左 | 同左 | true×5 |
| 全量 unpin | H2 `779…` | python-3.12 | 5 | 0,6,13,20,27 / 3,4,4,4,4 | 同左 | 同左 | true×5 |
| Hosted artifact | merge `8f9a0ec4…` | python-3.12 | 5 | 0,7,14,21,28 / 4,4,4,4,3 | 同左 | 同左 | true×5 |

脚本：`env-i-named.sh`（`env -i` + 具名模块）、`full-pin.sh` / `full-unpin.sh`（`flock 600` + `timeout 900` + `pytest tests/`）。`data_dir_role=persistent-httpdata`，`ffmpeg_argv_real=true`，`http_source_bytes_match` 与 PCM oracle 为 true，restart `result_payload_equal=true`。offset 是日志事件下标，非 byte offset，start 不必恒 4。JUnit XML **缺**；独立 pytest summary 文件 **缺**（报告/provider stdout 不当原产物）。故 511 passed / 3 skipped / 12 passed 仍是原 30 报告声称，本卡不把它写成亲计 JUnit。不以 Hosted 代裸。3 skip 身份可从源码核对、不与 HTTP deps 混：`tests/test_aligner_integration.py` 模块级 skipif（ForceAligner 后端/模型，覆盖 `:53` / `:62` 两函数）、`tests/test_segmenter.py:208` silero-VAD。假引擎不是 ASR 质量；生产 `CapsWriterServer`/`SocketManager` 完整装配未覆盖。

## 3. Hosted CI 与前派发 DIED

canonical run `37339081182` attempt 1 event=`pull_request` head=H2 conclusion=`success`；job `111861242756` 步骤 `运行 pytest` → `校验五轮矩阵工件结构`（importlib 同文件 `consume_repeat_matrix_trace`，H2 blob `7d511b8350211745c7af337a1ec091f61f00be1c`）→ `保存五轮矩阵工件` 均为 success。artifact `11356924649` name=`m6-repeat-matrix-py312`。3.11 job 只跑 SDK glob，不计五轮。3.12 websockets 未钉，精确版本 **unknown**，不写卡面 15。H1 run `37311065357` / artifact `11346765500` 不是 H2。

前派发 `dlg-20261005-164121-c35048` envelope `status=died`、`is_final=false`、`died_reason=died_unknown`，报告 3480 字节首行 `<!-- delegate-outcome: succeeded -->`。systemd `LoadState=not-found`、`InvocationID` 空、`ExecMainExitTimestamp` 空；默认 `Result=success`/`ExecMainStatus=0` **不当成功**。源报告与 envelope 未改、不重签。本卡只核对其留下的外部事实（artifact/tree/job 步骤）并复制 `d3a9218373b74e1e2b95e9d755590904080ef567` 字节。不宣该派发已完成。

gate run `37339082379`：`primary`/`ocr` skipped，`gate (draft)` success ≠ 正式主审批准。

消费者对原 trace 接受；全重标 clone 亦接受 ≠ executed 5。负例副本（缺第 5 轮 / 缺相位 / 简单重标 / io-first 仍 held / offset 复用 / 非法 sha）为 AssertionError。

## 4. 12 组 Spec 映射（不每组再跑 5）

契约：`goals/http-integration/M6-qa.md`、`docs/sessions/261001-http-files/qa.md`。接点取自已有 full-suite 节点与 qa.md 行号；**collect ≠ run**。JUnit 缺，故「已运行」只到 CodeH2 全量脚本入口 + owned trace，不杜撰每用例绿。

1. SDK PATCH 字节 / 落盘 SHA：`tests/test_http_qa_e2e.py:378`、`tests/test_http_client.py:144`、`tests/test_http_file_tasks.py:205`
2. 跨连接领取 / 重开服务：`tests/test_http_file_runner.py:341`、`tests/test_http_file_tasks.py:451`
3. 丢 202 显式恢复：`tests/test_http_qa_e2e.py:495`、`tests/test_http_client.py:476`
4. 未确认重发字节：`tests/test_http_file_tasks.py:272`、`tests/test_http_supervision.py:503`
5. 崩溃窗口 / SIGTERM·KILL：`tests/test_http_supervision.py:503`、`tests/test_http_file_runner.py:747/784`
6. GET 持久 payload：`tests/test_http_supervision.py:577`、`tests/test_http_cleanup.py:276`
7. 同 worker HTTP+WS：`tests/test_http_qa_e2e.py:114`
8. 取消先 / IO 先 5 轮：`tests/test_http_file_tasks.py:619`；同逻辑在矩阵 `cancel_io` 相位
9. 容量 / 准入：物理 GiB **未测**；缩小常量 `tests/test_http_file_tasks.py:1427/1464`
10. ffmpeg argv / Task.data oracle：`tests/test_http_qa_e2e.py:597`、矩阵 `pcm_segment_oracle_ok` + `ffmpeg_argv_real`
11. 失败形态 / 末段 final：`tests/test_http_qa_e2e.py:667`、`tests/test_http_file_runner.py:491+`
12. 清理 + 旧 WS 回归：`tests/test_http_cleanup.py:142+`；矩阵 `legacy_ws.ws_on_restarted_instance`；CLI 子进程 argv 见组 1 `test_http_client.py:413`

映射缺则 unknown：真实三平台容器、真实 ASR 字节/质量、生产完整装配。旧坏 suite / Windows `55F24E` 不把本卡当绿诊。

## 5. P2 探针（不改仓测试、不改 backlog）

`reviews/m6-h2-increment-verdict.md` @ `c7e512e8adee373750a64ddc8046c15953de5389`：`failure-visibility: p2-only`。简单 relabel 用五份 `_complete_round(1)`，重复 ID 先红，遮住「ID 必须含本轮号」。独立 scratch：ID 各自唯一但无 `r{n}` → 原 H2 `consume_repeat_matrix_trace` **reject**；仅删 `f"r{round_id}" not in evidence_id` 后同 fixture **accept**。原 P2 仍 backlog。不把该单测说成 atomic guard 已锁。咨询 receiver_unavailable；audit 42 不是顾问回执。schema-only 可证性 B 由主脑按原 Spec 裁决。

## 6. 复制清单与机读行

前缀皆 `docs/sessions/261003-http-completion/`。逐 blob 复制，不 merge 脏祖先。

- H1 hosted @ `0a46ac17…`（旧 H1 源，不包装 H2）
- `reviews/m6-h1-full-review1-verdict.md` @ `aafb9ef2…`：唯一更正 L9 `- failure-visibility: p2-only` → 无前缀整行 `failure-visibility: p2-only`；保留 WS 17.2 与 OCR skipped；origin SHA 即此
- H1 producer @ `42ce49d1…`（Task.data 真字节 + 外部 sqlite probe；H1 GET 红来自 review2 后，不把外部 probe 红当矩阵原断言）
- OCR followup @ `318b0890…`（comment `5996359745`，root unknown，非 ScannerRecovered）
- review2 + sanitization @ `757688f7…`（授权清理后干净 blob；禁 merge path59 祖先）
- audit + sanitization @ `8f650e06…`（第二次授权清理；禁 merge 7df/942；不改 audit 原首行）
- H2 increment @ `c7e512e8…`
- H2 hosted @ `d3a92183…`（外部事实核对后原字节）

新增 blob 宿主用户绝对路径 / IPv4 计数 0。`/tmp` 仅审查 OCR 背景路径。

## 7. 预算与未知

H1..H2 实施 47（已冻结）。本卡只 Doc，target 850 / hard 1100。SourceCode 停在 H2；FinalDocHead 为本卡 tip；full PR 仍含他 session Doc。Unknowns：JUnit 缺、Hosted websockets 精确版本 unknown、Draft 主审 skip、P2 判别力、生产装配、ASR 质量。代码接点：`consume_repeat_matrix_trace` / `test_five_round_same_service_concurrency_cancel_restart_ws` / CI importlib 消费。不改 Goal 索引。
