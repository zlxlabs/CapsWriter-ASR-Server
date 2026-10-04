# PR62 正式 ready：本 run 规范判决与 finding 读取

不是新冷审、不预先定 P1、不修代码、不重跑、不申诉。
`application_verdict` 与执行器任务完成态正交。

## 结论

正式 ready run 的**实际消费者 payload**把这次失败归到「主审已执行且有 primary findings」，不是 setup/model 没跑完，也不是聚合器没拿到 canonical 对象。

- 门禁机读行 `AGENT-GATE-VERDICT-V1`：`v=1`，`draft=false`，`primary=executed`，`gate_result=fail`，`classification=code_fail`，`reason_code=primary_findings`，`skip_reason=null`。
- GitHub Actions artifact `total_count=0` 只说明 GH 通道空，**不能**读成 no-finding。
- 聚合器已 resolve/download canonical 对象（`AUDIT_SOURCE_ATTEMPT=1`），随后 `Aggregate required verdict` 因上述机读行失败。
- 本执行器**没有**可读的 canonical findings 正文（缺 `line` / `trigger` / `evidence` / `acceptance` / `executedModel`）。
- **`application_verdict=unknown`**。精确 finding 处置未完成。不建议用普通 rerun 刷新 finding 身份。

## 本 run 生产者身份（API 对象，不用当前主干倒推）

| 字段 | 值 |
|---|---|
| 仓库 | `zlxlabs/CapsWriter-ASR-Server`（`repository.id=971940657`，head 仓同 id） |
| PR | 62，head 分支 `card/http-m4-c2-cleanup-261003`，非 draft |
| run | `37204722377` attempt 1，workflow `gate`，`workflow_id=367725633`，`check_suite_id=100774218372` |
| created / started | `2026-10-04T13:11:19Z` |
| event | `pull_request` |
| 结论 | `completed` / `failure` |
| head | `c2818c5cba71ac86ddc0da1bee54538d34cdfe6b` |
| base（run.pull_requests 与 PR `baseRefOid`） | `b0818dc7859d1d8100e42f5c70cb75d34da422f7` |
| callee source | `zlxlabs/gate/.github/workflows/gate-v2.yml@v2`，`ref=refs/tags/v2`，`sha=6fd21e0ab5a27a279fe5cd15dd74edaa0b079fe9` |
| 合成 merge（checkout 日志短 SHA，本地无此对象） | `28e1127`；文案为 Merge `c2818c5c…` into `b0818dc7…`。全量 merge SHA 未从本 run API 字段取出 |

状态面板评论 `5970020301`（`updated_at=2026-10-04T13:16:10Z`）把本 run 记为 `fail` / 要修代码；同 head 的 draft run `37204655950` 记为 `skipped`（主审未跑，绿≠过审）。

## 本 run 作业与首个失败步骤

| job | id | 结论 | 首个非 success/skipped 步骤 |
|---|---|---|---|
| classify_pr_paths | 111443417845 | success | 无 |
| quality | 111443418170 | success | 无 |
| resolve_advisory | 111443467926 | success | 无 |
| primary | 111443468167 | failure | step 9 `Run review-primary` failure（13:11:51Z–13:15:34Z） |
| ocr (ocr-minimax) | 111443510896 | success | 无 |
| gate（聚合器） | 111444219220 | failure | step 6 `Aggregate required verdict` failure（13:15:59Z–13:16:00Z） |
| notify | 111444304554 | success | 无 |
| ledger | 111444304583 | success | 无 |

primary 在 step 9 失败之后：annotate / diagnostics manifest / canonical upload / diagnostics upload / silo 网络诊断均为 success。不能把尾部诊断成功读成 primary 通过。

聚合器在 step 6 失败之前：`Resolve canonical primary audit artifact` 与 `Download canonical primary audit` 均为 success。step 6 之后 convergence receipt、terminal envelope、status panel、delivery diagnostic、silo 诊断均为 success。

check-run 注解（非 finding 正文）：

- primary：`primary review verdict=fail reviewer='codex-sub'`；`GATE-NET-DIAG-V1 job=primary … silo_http=http_200 github_https=http_200`。
- 聚合器：`quality: success`；`primary audit source run_attempt=1 (current run_attempt=1)`；`primary review verdict is 'fail'`；`classification=code_fail, reason_code=primary_findings, gate_result=fail`；`GATE-NET-DIAG-V1 job=gate … silo_http=http_200`。

## 对照 run（同 head，不是本正式 ready gate）

| run | 身份 | 结论 | 说明 |
|---|---|---|---|
| `37204655544` attempt 1 | workflow `CI`，created `2026-10-04T13:10:12Z`，head/base 与本 ready 相同 | success | job `111443220392` 单元测试 (websockets) success；job `111443220569` 单元测试 (websockets==15.0.1) success |
| `37204655950` attempt 1 | workflow `gate`，created `2026-10-04T13:10:12Z`，callee sha 同 `6fd21e0a…` | success | primary job `111443275300` **skipped**；`gate / gate (draft)` job `111443337554` success。这是旧 draft skip，不是本次正式 ready |

## 机读判决 payload 指针

- 通道：聚合器 job `111444219220` 日志（内存捕获，不落原文）。
- 日志 blob sha256：`538494711a7d4a771f9190c126fad063e369fcd5bfc4aa6b5cf5671474e705a8`。
- 含 `AGENT-GATE-VERDICT-V1` 的原始行 sha256：`d89ff73d7b3e0ce4214314b170160f12fedeb51dd340601febda011215b6e241`。
- 标记起 payload sha256：`c9e4da25da4984e1d07cc2725d0ed847ca6b3c693ee9e0659a1309bf23bf50b9`。
- 安全字段即上一节 JSON 键值。check-run `output.summary/text` 均为空，不以人类关键词补判决。

## Canonical primary audit

生产者（primary 上传步骤 success）与消费者（聚合器 resolve/download success）实际对象名：

- artifact name：`primary-audit-v2-971940657-c2818c5cba71ac86ddc0da1bee54538d34cdfe6b-37204722377-1`
- 对象前缀：`d14/971940657/primary-audit-v2-971940657-c2818c5cba71ac86ddc0da1bee54538d34cdfe6b-37204722377-1`
- 文件名：`primary-review-audit.json`
- `AUDIT_SOURCE_ATTEMPT=1`（与当前 attempt 一致）

GitHub `GET .../actions/runs/37204722377/artifacts` → `{total_count:0,artifacts:[]}`。该空列表不是「没有 finding」。

本执行器未取得该 JSON 的 `finding id/path/line/title/trigger/evidence/acceptance/executedModel` 正文。reviewer 身份仅有日志/注解中的 `codex-sub`；**executedModel 未知**。

## 日志通道白名单（明确不是 canonical）

primary job `111443468167` 日志 blob sha256：`b617e6996186fc3f73b54d4a69c203c13d1e9959130a0e12ca9bc0bdf0545134`（另一次拉取曾得空体，不以空体覆盖已成功捕获）。

`primary review fail reason: finding` 行共 5 条（major 1 / minor 3 / nit 1）：

| finding_id | severity | file | line | trigger | evidence | acceptance |
|---|---|---|---|---|---|---|
| `correctness-expired-state-not-committed` | major | `core/server/http_store.py` | 缺 | 缺 | 缺 | 缺 |
| `reliability-stop-reentry-bypasses-cleanup-drain` | minor | `core/server/http_server.py` | 缺 | 缺 | 缺 | 缺 |
| `performance-cleanup-repeats-full-history-scan` | minor | `core/server/http_store.py` | 缺 | 缺 | 缺 | 缺 |
| `testing-probe-inherits-unapproved-environment` | minor | `tests/fixtures/http_fatal_exit_probe.py` | 缺 | 缺 | 缺 | 缺 |
| `reliability-probe-output-handle-not-closed` | nit | `tests/fixtures/http_fatal_exit_probe.py` | 缺 | 缺 | 缺 | 缺 |

不把 title/summary 等诊断原文写入本文。不凭这些行做 P1 两问或证伪。

冻结范围 `b0818dc7859d1d8100e42f5c70cb75d34da422f7..c2818c5cba71ac86ddc0da1bee54538d34cdfe6b` 的路径 diff（`git diff --numstat`）：

- `core/server/http_store.py`：44 插入 / 4 删除（非空）
- `core/server/http_server.py`：42 插入 / 0 删除（非空）
- `tests/fixtures/http_fatal_exit_probe.py`：472 插入 / 0 删除（非空）
- `sdk/`：空。SDK 不在本 diff。当前 `origin/master=e117f0249b2cd503308fa1d682a72dcc6949b432` 相对冻结 base 超前 8 commit，含已合并 PR #70；**不能**用当前主干或 #70 解释本 run 的 primary findings。

## 只读取数尝试（一次收口，未借长期密）

1. GitHub run/job/check-run/annotations/PR 面板：可读，见上。
2. GitHub artifacts：0。
3. 本机按 run/job/head 文件名缓存：0。
4. `silo_store.py` 的 `get/resolve` 是既有只读接口，但需要 Silo 凭据。本执行器进程与派发父进程环境均无 `SILO_*` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`（只查键名与值长度，未读 `.env` / profile / 凭据文件，未使用任何密钥）。
5. `zlxlabs/gate#249` 现有评论 2 条。`5979799963` 已是「既有 audit JSON / 现有只读接口」请求（对象是 PR64 run `37188220228`，不是本 62）。#249/#248 政策禁止复制 Silo 长期 key。**没有**新的受控读取方式发布。本卡不发新 issue 评论、不加新 actor。

缺的最小字段（仍须绑定本 run/attempt/head）：canonical 中每条 finding 的 `id/severity/path/line/trigger/evidence/acceptance` 与 `executedModel`。

## 应用两问

未做。规范正文不齐，保留 `application_verdict=unknown`，不用合成路径或别仓主题冒充证伪。

现规格若将来取到正文，只应以 `docs/sessions/261001-http-files/design.md`、`docs/sessions/261001-http-files/qa.md`、`docs/sessions/261003-http-completion/m4-plan.md` 与 PR 62 当时 body 为准，不附历史作者报告推理。

## 继承红 / 新红

派发时刻主干基线不可用（`gh api request failed`）。**继承红：未能判定。** 本 ready run 的红是本次观察到的事实，不据此宣称相对未知基线为「新红」。

## 建议（给门禁持仓，不在本仓改 runtime）

把本 run 身份（上表 + canonical 对象名）交给 `zlxlabs/gate` owner，**沿用** #249 已有受控读请求，索取该 attempt 的脱敏 canonical findings JSON 或指出已支持的只读绑定接口。不要普通 rerun 刷新 finding 身份；不要复制 Silo 长期 key、扩大 org secret 或改 v2 tag。
