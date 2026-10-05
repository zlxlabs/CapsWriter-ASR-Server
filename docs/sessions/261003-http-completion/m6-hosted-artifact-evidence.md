# PR83 Hosted CI 五轮工件：实际 run / job / 消费证据

对象：`zlxlabs/CapsWriter-ASR-Server` PR83 Draft，冻结 head H0 `da81cacc13061be8a7693775ebca7e413a29a189`，base `6aa76f6c6935e9cef00afc1bcbcf8327e7c95488`。
本文件只记录 Hosted `ci.yml` 实际写出并被独立进程读到的 payload 与源身份。schema 五轮不单独证明完整服务生命周期，不标 M6 Done。Draft `gate / primary` 与 `gate / ocr` 均为 SKIPPED，不是模型批准。

取证时刻 live `refs/pull/83/head` 仍为 H0；live merge 当时等于 run 检出 SHA。身份以该 run 的 job 日志与 `trace.json` 的 `source_sha` 为准，不以事后 live merge 回填。

## 1. 精确 CI 身份（public API，非最新绿标签）

按 `head_sha=H0` 列出该 SHA 上全部 Actions run，共 2 条，均为 `event=pull_request`、`run_attempt=1`、`status=completed`：

| 角色 | workflow | run | 结论 | 不是本卡工件源 |
|---|---|---:|---|---|
| 五轮 producer+consumer | `CI` `.github/workflows/ci.yml` | [37302715605](https://github.com/zlxlabs/CapsWriter-ASR-Server/actions/runs/37302715605) | success | — |
| Draft gate | `gate` | 37302716283 | success（OCR/primary **SKIPPED**） | 是 |

`CI` run 的 `pull_requests[0]`：number=83，head=H0，base=`6aa76f6c…`。三异质 job 都 success，不能把 3.11 绿当 M6 循环：

| job id | 名称 | pytest 目标 | 校验工件 | 上传工件 |
|---:|---|---|---|---|
| 111739015793 | 单元测试 (py3.11 / websockets) | `tests/test_sdk_*.py` | skipped | skipped |
| 111739016164 | 单元测试 (py3.11 / websockets==15.0.1) | `tests/test_sdk_*.py` | skipped | skipped |
| **111739016003** | **单元测试 (py3.12 / websockets)** | `tests/` | **success** | **success** |

py3.12 步骤结论：检出代码 success → 运行 pytest success（`M6_REPEAT_MATRIX_ARTIFACT_DIR=${{ runner.temp }}/m6-repeat-matrix`）→ **校验五轮矩阵工件结构** success → **保存五轮矩阵工件** success。

检出命令（job 日志，非猜测）：`git checkout --progress --force refs/remotes/pull/83/merge`。日志原文：`HEAD is now at 750ecfb Merge da81cacc… into 6aa76f6c…`。`actions/checkout@v4` 未覆写 `ref`，因此 `git rev-parse HEAD` ≠ H0。

## 2. Artifact → 实际文件字节

`GET …/runs/37302715605/artifacts` 仅 1 个，未过期：

| 字段 | 值 |
|---|---|
| id | 11342646375 |
| name | `m6-repeat-matrix-py312` |
| size_in_bytes | 936（zip） |
| created_at | 2026-10-05T11:30:11Z |
| workflow_run.id / head_sha | 37302715605 / H0 |

下载该 artifact zip（私有 0700 目录，不入库）。zip 成员白名单：仅相对路径 `trace.json`，无 `..` / 绝对路径。解出 5740 字节，NUL=否，空=否，sha256 `992b37d4788d8c2f0c8b14fa0e2caf4b0973ee1491f9302258f5543893ca3ec4`。

## 3. `source_sha` 参照系（merge commit ≠ H0 提交，树字节相等）

| 对象 | 40-hex | parents | tree |
|---|---|---|---|
| H0（PR head / run.head_sha） | `da81cacc13061be8a7693775ebca7e413a29a189` | `e9278e17…` | `43c3274004ed58bc40ec68c8dd11592abaaeffcc` |
| producer `source_sha` / 检出 HEAD | `750ecfb4f3e8853707cc7357901a40a7820ac3e5` | **base + H0** | **同一 tree** `43c32740…` |

`source_sha` 来自测试里 `git rev-parse HEAD`，即 merge commit，不是 H0。fetch 该 SHA 后，`git diff --numstat H0 750ecfb4 -- start_server.py start_proxy.py config_server.py config_proxy.py core sdk tests/test_http_qa_repeat_matrix.py tests/test_http_file_runner.py .github/workflows/ci.yml` **空**。所列 CLI / CORE / SDK / 新测试 / harness / `ci.yml` 与 H0 字节相等（非空、无 NUL）。commit 身份仍必须写成 merge，不能写成 H0。

工件根字段无 `producer_argv` / `producer_env`（记缺，不补）。

## 4. writerfile 安全字段（5 轮 × 4 相位）

根：`schema_version=1`，`skips=[]`，`source_runtime=python-3.12`，`producer_roles=[http-sdk, ws-frame, ffmpeg-shim, recording-worker, managed-http-subprocess, io-thread-barrier]`。`rounds` 恰好 5，每轮 `pass=true`，`data_dir_role=persistent-httpdata`，相位键均为 `concurrency` / `cancel_io` / `restart` / `legacy_ws`。

| round | ffmpeg_start_count | restart pid_old → pid_new | 各相位 `round_job_id` 含 `rN` |
|---:|---:|---|---|
| 1 | 3 | 9191 → 9267 | 是 |
| 2 | 6 | 9416 → 9492 | 是 |
| 3 | 9 | 9640 → 9715 | 是 |
| 4 | 12 | 9864 → 9960 | 是 |
| 5 | 14 | 10111 → 10177 | 是 |

`ffmpeg_start_count` 单调递增 3,6,9,12,14，是共享 shim 日志的累计条数，不是每轮清零后的独立计数；第 5 轮 +2。十个 PID 两两不同。每轮 `restart.done_replay=true`，`legacy_ws.ws_final=true`。嵌套 `cancel_first`/`io_first` 对象存在，本文件不展开。

## 5. 实际 consumer：CI 步 + 本机对真实文件的正反例

CI 步「校验五轮矩阵工件结构」在 pytest **之后**、upload **之前**，独立 `python - <<'PY'`：`importlib.util.spec_from_file_location("m6_repeat_matrix", Path("tests/test_http_qa_repeat_matrix.py"))`，然后 `consume_repeat_matrix_trace(Path(os.environ["M6_REPEAT_MATRIX_ARTIFACT_DIR"]) / "trace.json")`。env 角色与 upload `path` 角色同为 `${{ runner.temp }}/m6-repeat-matrix/`，与 zip 内相对文件 `trace.json` 对齐。不能拿 artifact 名里的 `5` 或 job 成功绿当内部 rounds=5。

本机对下载得到的 **同一 5740 字节** 再调该 consumer 一次：接受。对 clone 文件做注入后各拒一次（均为 `AssertionError`，不是自写 expected）：

| 控制 | 改动 | 结果 |
|---|---|---|
| 正例 | 原件 | 接受 |
| 缺第五轮 | rounds 截到 4 | `rounds 必须恰好 5 条，实际=4` |
| 缺取消相位 | 删 round1 `cancel_io` | `round 1 缺少相位 ['cancel_io']` |
| 缺重启相位 | 删 round3 `restart` | `round 3 缺少相位 ['restart']` |
| 注入标记 | 加 `_injection_marker` 且 round5 `pass=false` | `round 5 pass 不为 true` |

以上只证明 **这个 consumer 对 payload shape 有约束**，不是本进程复跑完整五轮矩阵，也未跑真实模型 / 私有媒体。

## 6. 这证明了什么 / 仍缺什么

**已证明（Hosted CI 存在与 payload 完整 shape）：** H0 的 pull_request `CI` run#37302715605 attempt 1 的 py3.12 job 写出 `trace.json`，独立 importlib 步读该路径且步骤 success，artifact `m6-repeat-matrix-py312` 可下载；根 schema 与 5×4 相位、`skips=[]`、累计 ffmpeg 计数、每轮新 PID 均在真实字节里；consumer 正例接受、缺轮/缺相位/改 pass 均红；merge tree 与 H0 源字节一致。

**不能外推：** 完整隔离服务并发／取消／重启／旧 WS 的代码语义与 ASR 质量（另卡审查）；`producer_argv`/`producer_env` 未入工件，无法从本 payload 核 `CW_HTTP_DATA_DIR` 实参；ffmpeg 是否每轮独立进程只看到累计计数；无会话 shell 五轮不在本 run；Draft primary/OCR skipped ≠ 批准；测试 SUCCESS ≠ M6 Goal Done。不 ready PR、不 rerun、不改 GateDisposition。
