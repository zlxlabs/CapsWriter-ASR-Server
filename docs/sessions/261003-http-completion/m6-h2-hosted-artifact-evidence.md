# M6 H2 Hosted 原工件源链

本文只记录 PR #83 在 H2 `77940745146d377d780e1f840bfbfd633740c114` 上
**这一次** Hosted CI 的真实发布／消费链。不是 code review，不改消费者，
不用 H1 工件冒充 H2，不把 schema 通过写成五轮真实执行，也不把 Draft 主审
skip 写成批准。Goal 未达。假引擎不是 ASR 质量；Hosted 不能代替裸环境。

## 1. 源 run 与三步

- PR [83](https://github.com/zlxlabs/CapsWriter-ASR-Server/pull/83) 仍为 Draft；
  head = H2，base = master `6aa76f6c6935e9cef00afc1bcbcf8327e7c95488`。
- CI run [37339081182](https://github.com/zlxlabs/CapsWriter-ASR-Server/actions/runs/37339081182)
  event=`pull_request` attempt=1 head=H2 conclusion=`success`。
- 3.12 job `111861242756`「单元测试 (py3.12 / websockets)」360s `success`。
  实际三步均为 success：`运行 pytest` → `校验五轮矩阵工件结构`
  （`importlib` 加载 `tests/test_http_qa_repeat_matrix.py` 的
  `consume_repeat_matrix_trace`，读同一 `M6_REPEAT_MATRIX_ARTIFACT_DIR/trace.json`）
  → `保存五轮矩阵工件`。契约在 `.github/workflows/ci.yml`。
- 同 run 两个 3.11 job 只跑 SDK glob；工件校验与上传均为 `skipped`，不计五轮。
- gate run [37339082379](https://github.com/zlxlabs/CapsWriter-ASR-Server/actions/runs/37339082379)
  的 `primary`/`ocr` 为 `skipped`；`gate (draft)` success ≠ 正式主审批准。
  12 组 QA、两裸环境、正式 gate 各有完成条件，本文不宣称闭合。
- 全量计数与新模块数：job API 无结构字段，未重跑 500。3.12 websockets 未钉；
  精确版本不在结构化元数据里，不引用卡面 15 代。

## 2. 原 artifact（H1 不能替）

- 本源：name=`m6-repeat-matrix-py312` id=`11356924649`，run=`37339081182`，head=H2，
  归档只含 `trace.json`。
- H1 源不得替换：run `37311065357` artifact `11346765500` head=`337689689c9b2a314548b70667e447841bf070ad`。
  原档保留；变体另写；未改源校验器。

根字段：`schema_version=1`（int）；`skips=[]`；`source_runtime=python-3.12`；
`source_sha=8f9a0ec4ade6f995a5f149b9f8278bde5787f941`（40 位小写 hex）；
`producer_roles` 六个非空字符串：`http-sdk`、`ws-frame`、`ffmpeg-shim`、
`recording-worker`、`managed-http-subprocess`、`io-thread-barrier`。
`rounds` 恰好 5。`source_sha` 是本次 PR merge checkout（parents=master+H2），
**不是** H2 head。消费者只拒非法格式，不把该字段当 checkout 鉴权。
PID 只作为 restart 相位两个不等正整数出现，不当进程身份认证。

生产者 `test_five_round_same_service_concurrency_cancel_restart_ws` 用真实
`git rev-parse HEAD` 写 SHA、真实 Python 写 runtime，每轮后写 `trace.json`
字节并同进程消费；CI 再 importlib 读同一路径后上传。真实相位依这段源码与
本次 3.12 pytest 步骤 success，**不**由消费者单独认证 JSON 数据真实发生。

| round | ffmpeg 事件下标 / 本轮 start | cancel-first pending/mailbox/held | io-first pending/mailbox/held | bytes_match / pcm oracle | result_eq / engine_after | WS-on-live-second |
|---:|---:|---|---|---|---|---|
| 1 | 0 / 4 | 1 / 31 / true | 0 / 32 / false | true / true | true / 0 | true |
| 2 | 7 / 4 | 1 / 31 / true | 0 / 32 / false | true / true | true / 0 | true |
| 3 | 14 / 4 | 1 / 31 / true | 0 / 32 / false | true / true | true / 0 | true |
| 4 | 21 / 4 | 1 / 31 / true | 0 / 32 / false | true / true | true / 0 | true |
| 5 | 28 / 3 | 1 / 31 / true | 0 / 32 / false | true / true | true / 0 | true |

ffmpeg_log_offset 是日志**事件下标**（严格递增），不是 byte offset。
每轮 `pass=true`、`data_dir_role=persistent-httpdata`、`ffmpeg_argv_real=true`；
并发 `http_source_bytes=24525` 且源/落盘匹配；restart prefix/suffix=2/4、
known-empty 与 DONE 回放均为 true。工件无凭据赋值、无 IP、无绝对路径。

## 3. 树：H2 与 merge checkout 相同

非空 NUL blob 集（`git ls-tree -r -z`）与 GH recursive tree `truncated=false`：
H2 tree `e260c171001c9f56ee94adc4cf572022ddae91fe` blob=475 / object=578。
merge commit `8f9a0ec4…` tree 同此值，parents 为 master 与 H2。
**CodeH2sameasFinal**：此次 checkout 树相对 H2 无代码差异。master 仍是
`6aa76f6…`，未另开浮动 HEAD。已知否定：H1 tree `6b129a73…` ≠ H2 tree
（同为 475 blob 仍不相等）；坏引用 `git cat-file` 退出 128。空集合相等会通过，
故要求 blob 集非空后才比。

## 4. 原消费者：结构通过 ≠ executed 5

`importlib` 加载 H2 blob `7d511b8350211745c7af337a1ec091f61f00be1c`
（`tests/test_http_qa_repeat_matrix.py`）读原 `trace.json` 一次成功。
基于原 JSON 的副本（不覆盖原档）均为 `AssertionError`，不是 ImportError：
缺第 5 轮；缺 `cancel_io`；缺 `restart`；只改 round 号而 job id 仍属第 1 轮；
`io_first` 仍 held；`result_payload_equal=false`；`ffmpeg_log_offset` 复用前轮。
非法 `source_sha` 格式同样 `AssertionError`（结构，不是对 checkout 鉴权）。
把第 1 轮字段全面重标成 r1..r5 且 offset 递增：**结构接受**，这不是 executed 5。

未跑裸矩阵、全量套件、模型、媒体、Win 或生产。派发时主干基线 API 失败，
继承红未能判定；本次 H2 run/job/artifact 步骤无失败。
