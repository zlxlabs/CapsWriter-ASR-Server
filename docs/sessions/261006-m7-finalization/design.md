---
stage: planning
dispatch_id: dlg-20261006-024303-c1bd68
card_type: tests-docs
goal: http-integration/M7
verify_mode: local-docs-v1
---

# M7 最终落地前置核实与有界执行计划

本文件是**规划卡**产物，不是 M7 完成记录。M7 未完成，本卡不宣布完成、不改 `GOALS.md` 或
`goals/http-integration/M7-baseline.md` 状态、不推进或合并 PR #82。

## 0. 锁定决策（承接主脑，非本卡新议）

- M6 验收冻结在 `796104c`；不替后来在 `e849c21` / `d251618` 上运行的源码背书。M6 的完成状态
  （来源 `goals/http-integration/M6-qa.md`、合并记录 `2bfe0f5` / `ee61475`）不因本卡推进而改变。
- M7 的 HTTP / 默认 WS 应用层字节、真实 ASR 质量、耗时与资源证据，必须取自**Windows 修复正式
  合并后的共同源码**。旧平台参考数（旧 492、Windows 21/25、POSIX 21/25、Linux 首测 4 次串行）
  一律不作为新源码资格。
- 生产部署另需授权；本卡与后续计划卡都不含生产动作。
- 本卡不重新设计 HTTP 接口，只规划剩余交付。

### 已否决方案（不得在后续卡复活）

| 已否决 | 否决理由 | 来源 |
| --- | --- | --- |
| 盲跑 full / grid 矩阵找根因 | 55 failed / 24 errors 已在同 head 上测过两次，仍红；再跑一次不产生新输入 | `windows-http-integrity-fix-progress.md`（PR82 head 内）两段实测 |
| 延长 timeout / sleep 让红变绿 | 4 个 `naked-shell` 失败中两种形态是「探针 120s 未产出报告」；加时间只是掩盖 | 同上，`test_http_cleanup` 15 passed / 4 failed |
| 重试直到绿 | 同上，且禁止用重试结果冒充资格 | 同上 |
| 旧 492 全量 / POSIX 21/25 / Windows 21/25 冒充新源码资格 | 这些数字归属源修 `9e0dd6db` 端点，PR 自身记录明确「不是本 head 新跑」 | `windows-http-integrity-fix-progress.md` |
| fake 模型 / stub 结果当 ASR 质量 | stub 只证明采集链路，不证明识别 | `m6-final-merged-acceptance.md:66` |
| 跨仓改 gate / 平台工具 | 门禁逻辑在 `zlxlabs/gate`；本卡不越权 | `docs/development/testing.md` |
| 生产服务改动或凭据调查 | 未授权 | 卡面非目标 |
| 把 PR #82 的 `O_BINARY` 局部已审当作全套件绿的证明 | 已审的是两行 `os.open`，不是套件结果 | PR82 body 自述 |

## 1. 核实方法与来源台账

只读调研，未运行产品代码、未启动服务、未下载模型、未读凭据或私有 transcript/音频/哈希。
命令输出缓存于本卡私有 state 目录（卡面指定的 dispatch 私有缓存路径），不入仓。

| 事实 | 来源 | 类型 |
| --- | --- | --- |
| 本卡 base `e849c21`，远端 master 同 SHA | `git ls-remote origin refs/heads/master`（本卡执行时） | 已测 |
| PR #82 `OPEN` / `isDraft=true` / head `fce9131a` | `gh pr view 82 --json state,isDraft,headRefOid` | 已测（白名单字段） |
| PR82 改 6 个文件，生产改动只在 `core/server/http_store.py` | `gh pr view 82 --json files` | 已测 |
| 合并 `e849c21` 与 `fce9131a` 无冲突，产出树 `634c7d7` | `git merge-tree --write-tree`（exit 0，0 CONFLICT） | 已测 |
| 合并树保留两处 `getattr(os, "O_BINARY", 0)` 与新增 Windows 测试 | `git show 634c7d7:core/server/http_store.py` / `:tests/test_http_file_tasks.py` | 已测 |
| 合并树相对 master 的非文档差异只有 2 文件 / +77 −2 | `git diff --stat e849c21 634c7d7 -- core/ sdk/ tests/ .github/ scripts/ config_server.py start_server.py` | 已测 |
| master 与 PR82 的测试面差异是 M6 五轮矩阵 + #76 看门狗 + harness 改动 | `git diff --name-status fce9131a e849c21` | 已测 |
| master CI run `37403660636`（head `e849c21`）三 job 全 success，py3.12 `512 passed, 3 skipped` | `gh run list` + `gh api .../check-runs` + job log 第 937 行 | 已测 |
| PR82 head CI 三 job 全 success，py3.12 `500 passed, 3 skipped in 256.89s` | job `111751291971` log 第 946 行 | 已测 |
| PR82 的 gate `primary` / `ocr` / `resolve_advisory` 为 `skipped`（draft） | `gh api .../commits/fce9131a/check-runs` | 已测 |
| 55 failed / 24 errors / 421 passed / 3 skipped 是 **Linux 本机 uv 运行**，非 Windows | PR82 head 内 `windows-http-integrity-fix-progress.md` 两段自述命令与 `Linux 全量 CI 栈` / `uv run --no-project` | 已测（读 PR82 head 文档） |
| 本机当前有非本卡的 pytest 长驻（PID 2431473，`tests/test_ws_progress_watchdog.py -k s1`，已运行 38090s） | `ps -o pid,lstart,etimes,cmd` | 已测 |
| 本机 20 核 / 49 GiB / systemd user `degraded` / 36 个 python 进程 | `nproc`、`/proc/meminfo`、`systemctl --user is-system-running`、`ps` | 已测 |
| M7 基线工具 `scripts/_baseline_http_ws.py` 与指南 `docs/guides/http-baseline.md` 已在主干 | `docs/guides/http-baseline.md`、`docs/development/testing.md` | 已测 |
| M7 Linux 首测已做过 4 次串行实测，但服务 SHA 是 `820c3a2`、工具 SHA `d4eab57` | `m7-linux-baseline-evidence.md` | 已测（旧源码，仅参考） |
| M7-baseline.md 的「已知阻塞：等待 E6」是旧描述，M6 已历史完成 | `goals/http-integration/M7-baseline.md` vs `goals/http-integration/M6-qa.md` | 已测（文档事实） |

GitHub API 调用 6 次（PR 元数据、PR body、PR files、PR commits、master check-runs、PR82
check-runs、两次 job log），在 15 次预算内。

## 2. 阻塞来源核实：Windows 55/24 到底是什么

### 2.1 已测事实

1. **两次红是 Linux 本机运行，不是 Windows。** PR82 head 内进度文档两段分别写明命令为
   `uv run --no-project --python 3.12 ...`（Linux 依赖栈），并自述「Linux 全量 CI 栈」。Windows
   原生证据（21/25 红绿、字节对照表）归属源修 `9e0dd6db` / 实现父 `0bb836e3`，PR 自己声明
   「不是本 head 新跑三机 runtime」。
2. **两次红的结果完全一致**：`55 failed, 421 passed, 3 skipped, 24 errors`，分别在旧入口
   （`pytest -q -ra --tb=line --junitxml`）和标准入口（`python -m pytest tests/ -q -rs
   -p no:cacheprovider`）下复现，rc=1，套件 2 均因 fail-stop 未跑。
3. **失败分布已记录**：`test_http_cleanup` 15 passed / 4 failed，失败全在 `naked-shell` 参数
   （systemd 侧用例在 15 passed 内实际跑过）；`test_http_store` 16 passed；Windows 二进制用例
   `test_http_binary_payload_survives_append_recovery_and_commit_replay` **passed**；其余以
   `EOFError`（45）与 setup `EOFError`（24）为主，首个异常类型 `EOFError`，落在 stdlib
   `multiprocessing/connection.py:399` 的 `_recv`。另有一个 `409≠400` 的
   `test_options_missing_and_none_default_but_falsy_wrong_types_are_rejected`，隔离复跑通过。
4. **同一 head 在 hosted CI 是绿的**：py3.12 job `111751291971`（head `fce9131a`）
   `500 passed, 3 skipped, 0 failed`。master 的 py3.12 job（head `e849c21`，run `37403660636`）
   `512 passed, 3 skipped, 0 failed`。
5. **采集总数一致**：hosted `500+3=503`，本机 `55+421+3+24=503`。同一份用例集合，两种环境两个
   结果。

### 2.2 结论（区分已测与推断）

- **已测**：这不是 Windows 平台失败；不是 `O_BINARY` 修复引入的失败（该用例在红场里 passed）；
  不是用例集合差异（503 对 503）；PR82 的生产改动与主干可无冲突合并，且合并树保留修复与新增测试。
- **推断（未经本卡验证，需下一张卡的最小新因果输入）**：本机红与 hosted 绿的差异落在**运行环境**，
  而非被审源码。已知的环境差异至少有三条，且都不是「把超时调大」能解决的：
  a. 本机并发负载（36 个 python 进程、loadavg 曾达 7+；`EOFError` 于
     `multiprocessing/connection.py:399 _recv` 是子进程侧管道先关闭的典型形态，与资源/并发下的
     子进程早死一致）；
  b. 本机 `naked-shell` 探针形态依赖本机 shell 环境与 120s 报告等待，而 hosted runner 不跑该
     形态的同等路径；
  c. 本机 systemd user 为 `degraded`。
- **仍是 unknown**：55/24 的**单一根因**。现有收据只到失败分布与首个异常类型，不到因果。
  本卡不发明根因。

### 2.3 一次有新输入的最小根因验证（替代 full 重跑）

在**干净隔离环境**下只跑 `tests/test_http_cleanup.py` 的 `naked-shell` 参数集，并同时记录
本机当时的负载水位。判据：`naked-shell` 是否仍红、以及 4 个失败是否仍是两种已知形态。

- 入口：`uv run --no-project --python 3.12 --with numpy --with rich --with websockets==15.0.1
  --with colorama --with pytest==9.1.1 --with soundfile --with pytest-asyncio==1.4.0
  --with aiohttp==3.14.3 --with httpx==0.28.1 python -m pytest
  "tests/test_http_cleanup.py::test_source_file_is_unlinked_after_http_job_terminal[?naked-shell]"
  -q -rs -p no:cacheprovider`（实际 node 名以收集结果为准，先 `--collect-only -q` 取准）。
- 预计耗时：单文件定向 ≤ 300s 外层上限；不跑全量。
- 隔离措施：独立 `TMPDIR`；不启停任何既有服务；只对自己启动的 PID 操作；不读原失败日志与录音。
- 新输入点：这是**第一次**在有负载水位记录的情况下单独取这 4 个用例的结果。此前两次都只有全量
  汇总，没有「这 4 个在安静环境下是否仍红」这一维。
- 红验约束力自查：若判据写成「重跑后仍是 4 failed」而不区分形态与负载，则该判据无法区分
  「环境负载」与「代码缺陷」；因此判据必须同时记录形态与水位，且若安静环境下转绿，结论只能是
  「负载相关」，不得写成「根因已修」。

## 3. 基线工具与三平台可用性

### 3.1 已测：工具与契约现状

- 采集器 `scripts/_baseline_http_ws.py`，指南 `docs/guides/http-baseline.md`，均在主干。
- 生产消费者：HTTP 上传原始文件字节；默认 WS v2 走 `sdk/capswriter_asr/client.py` 的
  `transcribe_file(..., encoding="flac")`，音频放 UTF-8 JSON 文本帧 `data` 字段（Base64），
  不发二进制帧。
- 质量 oracle：CER 相对参考稿，参考稿来源状态显式 `verified/unverified/not_provided`；工具
  **不判质量通过**，`status=ok` 只代表采集与落盘完成。
- 公共 fixture：`tests/fixtures/http_baseline_producer.json`（HTTP SDK producer 的 create JSON、
  原始 PATCH 字节、commit 请求与 WS v2 文本帧），已授权可复用。
- 口径分离已固化：源文件字节 / 解码 16 kHz mono `f32le` PCM / HTTP PATCH body 与控制 JSON /
  WS JSON UTF-8 与 Base64 音频字段分列；HTTP 重复 offset body 计入 `http_retransmitted_bytes`，
  SDK transport retries 固定 0。

### 3.2 已测：三平台环境可用性

| 平台 | 隔离环境/样本 | 状态 | 来源 |
| --- | --- | --- | --- |
| Linux | 隔离 checkout + Paraformer ONNX CPU + 私有样本/字幕 | **曾可用**，但绑定服务 SHA `820c3a2`、工具 SHA `d4eab57`；样本为私有，不能进公开文档 | `m7-linux-baseline-evidence.md` |
| Windows | Windows 原生 CPython 3.11.7 / 3.12.12 隔离 venv，`0bb836e3` 红绿已测 | **曾可用**，绑定源修端点；ACL 未测（Linux mode 位不可代证） | `windows-http-integrity-*verdict` 三份（PR82 head 内） |
| macOS | 无任何隔离树、无样本、无实测记录 | **unknown，需主脑确认是否有可用机器与授权** | 仓内检索无 macOS 基线收据 |

### 3.3 未知项与获取入口（不发明）

| unknown | 获取入口 |
| --- | --- |
| macOS 隔离机器是否存在、谁有授权 | 主脑裁决；仓内无来源 |
| 三平台真实 ASR 质量门槛 | 原设计未定阈值 → 见 §6 唯一裁决点 |
| Linux/macOS/Windows 在**新共同 SHA** 上的可用性 | 合并后按 §5 卡 A 重测，不复用旧数 |
| 真实 CPU/RSS | 工具**当前不测** CPU/RSS（`docs/guides/http-baseline.md` 明写）；Linux 首测的 RSS/CPU 是一次性外部监控，不是工具能力。是否补测见 §6 裁决点 |

## 4. 最短交付计划（易变决策优先）

依赖图：`C1 → A → B → D`，其中 `E` 可与 `C1` 并行。

### 卡 C1：解除 Windows 阻塞并正式合并 PR #82

- 目标：把 PR #82 从 Draft 推到正式合并，产出**共同 SHA**。
- 前置新输入：§2.3 的最小根因验证结论（不需要全量绿）。
- 动作：主脑裁定根因是否阻塞合并；若不阻塞，补齐 PR82 文档、更新 head、把 PR 标 ready、
  跑完整 gate（draft 期 `primary` 是 `skipped`，必须看 `gh pr checks 82` 的 conclusion 是
  `SUCCESS` 还是 `SKIPPED`）、正式合并。
- 已知可合并性（本卡已测）：`git merge-tree --write-tree e849c21 fce9131a` → `634c7d7`，0 冲突；
  合并树非文档差异仅 `core/server/http_store.py` +8 −2 与
  `tests/test_http_file_tasks.py` +71；两处 `O_BINARY` 与新增测试均保留。
- 验证命令：`git diff --check`；`gh pr checks 82`（人工核对 conclusion）；合并后
  `git ls-remote origin refs/heads/master` 非空且与本地一致。
- 预算：≤ 1 张卡，不跑全量。
- 失败可见性：gate 任一 job 非 SUCCESS/SKIPPED 即停；`primary` skipped 不得当绿。
- 所需授权：Pi 批准推进 PR #82（合并动作）。
- **不做**：不修改 `http_store.py` 之外的源码，不改测试来迎合绿。

### 卡 A：冻结共同 runtime 并锁定基线工具版本

- 目标：产出「三平台都必须测的那个 SHA」，并确认基线工具与 SDK 版本在这条 SHA 上可用。
- 前置：C1 完成。
- 动作：记录合并后的 40 位 master SHA 为 `MERGED_SHA`；确认
  `scripts/_baseline_http_ws.py` 的去 docstring AST 哈希与已知值的关系（既有做法：三方
  AST 哈希相等才算工具没被偷换）；确认 `docs/guides/http-baseline.md` 的 Linux 隔离命令依赖
  闭包在 `MERGED_SHA` 上仍完整（含 `rich`、`colorama`，M7-review1 P2-1 的教训）。
- 验证命令：`python -m pytest tests/test_http_baseline.py -q`（定向 11 项，不跑全量）；
  `git diff --check`；AST 哈希三方对比脚本（临时脚本写入私有 state 目录）。
- 预算：定向测试 ≤ 120s。
- 失败可见性：AST 哈希不等或定向测试红即停，不进入三平台测量。
- 所需授权：无（只读 + 定向测试）。
- **不做**：不改工具逻辑、不加阈值、不加 fallback。

### 卡 B：Linux 隔离真实基线（`MERGED_SHA`）

- 前置：A。
- 动作：按 `docs/guides/http-baseline.md` 的「Linux 隔离运行」在隔离 checkout 检出
  `MERGED_SHA`，起 Paraformer 服务，跑 WAV/MP4 × HTTP/WS-v2 四次串行。
- 关键：参考稿来源未核实就写 `unverified`；CER 只表示与该稿差异。私有路径、正文、哈希不进仓。
- 验证：每协议私有 JSON `status=ok`、final `is_final=true`、token/timestamp 数量相等、单调、
  覆盖、时长区间；stdout 只含匿名 ID 与字节/指标。
- 预算：单次协议 ≤ 240s（工具 `--timeout`），外层 ≤ 30min。
- 失败可见性：非零退出 / `BASELINE_FAILED` 即停并原样记录签名，不重试、不换 ID 掩盖。
- 所需授权：起隔离服务（非生产）；Linux 样本在主脑私有目录，本卡不复制。
- **不做**：不改样本、不生成录音、不下模型、不跑 grid。

### 卡 C：Windows 隔离真实基线（`MERGED_SHA`）

- 前置：A（与 B 可并行，各自独立机器）。
- 动作：Windows 隔离 venv + 私有模型缓存目录软链，跑同一组四次串行。
- 关键：**ACL 必须在 Windows 实测**，不能用 Linux mode 位代证；`O_BINARY` 修复的效果要在这条
  SHA 上由真实 producer 字节与磁盘字节相等来验，不复用 `9e0dd6db` 的旧字节表。
- 验证/预算/失败可见性：同卡 B。
- 所需授权：Windows 机器与执行会话。

### 卡 D：macOS 隔离真实基线（`MERGED_SHA`）

- 前置：A + **主脑先裁决 macOS 机器是否存在**（§3.2 为 unknown）。
- 若不存在：卡 D 阻塞，M7 不能宣告完成（缺一条平台证据 = unknown = 未完成）。
- 动作/验证/预算/可见性：同卡 B。

### 卡 E（可并行）：部署说明与入口一致性核对

- 可与 C1/A 并行，不依赖 `MERGED_SHA`。
- 目标：核对 `deploy/README.md`、`docs/guides/getting-started.md` 与实际入口一致——旧 WS 端口
  与默认行为保留、HTTP 显式启用且初始化失败即失败、不把 systemd `is-active` 当业务健康。
- 验证命令：从裸 shell/CI 隔离环境实际走新旧两入口并核对 health 的 `status`/`git_sha`/结果；
  只取白名单字段，不整段回显。
- 预算：≤ 1 张卡，不起生产。
- 失败可见性：任一入口与文档不符即开 issue，不改文档迁就实现。
- 所需授权：起隔离服务。

## 5. 关键不变式与每条的证据来源

| 不变式 | 需要什么证据算成立 | 现在在哪 |
| --- | --- | --- |
| HTTP 可靠原字节 | 源文件字节 = producer PATCH body = 磁盘物理字节 = SHA；弱网重发字节显式记录 | `tests/test_http_file_tasks.py::test_http_binary_payload_survives_append_recovery_and_commit_replay`（PR82 新增，合并树保留）；`http-baseline.md` 口径段 |
| 默认 WS 协议不变 | SDK 默认 `flac` + UTF-8 JSON 文本帧 + Base64，二进制帧 0 | `tests/test_http_baseline.py::test_ws_meter_observes_actual_sdk_v2_send_payload`；fixture `tests/fixtures/http_baseline_producer.json` |
| 完整结果可重新领取 | final `is_final=true`；token/timestamp 等长；跨连接领取 | `tests/test_http_baseline.py`（HTTP final 校验）；M6 五轮矩阵的跨连接领取样本 |
| 真实模型质量 | 真实模型 + 可核实参考稿；工具不判通过 | **未测**；旧 Linux 首测参考稿 `unverified` |
| 字节口径分离 | 容器 / PCM / 重发三者分列，不相加、不互相冒充 | `docs/guides/http-baseline.md` 测量口径段 |
| 生命周期 / RSS / CPU | 独立进程树监控 | 旧 Linux 首测一次性监控（服务 SHA `820c3a2`）；工具本身不测 |
| 部署说明与入口一致 | 裸 shell/CI 隔离环境实走两入口 | **未测**（卡 E） |
| 三平台同源 | 三平台都测同一个 `MERGED_SHA` | **未测**（卡 B/C/D） |

**规则**：以上任一条证据失败或缺失即记 `unknown`；缺任意一条不得宣告 M7 整体完成。

## 6. 唯一需要用户裁决的点

原设计（`goals/http-integration/M7-baseline.md` 与 `docs/guides/http-baseline.md`）**没有定真实
ASR 质量门槛**，且明确写了「`status=ok` 不是识别质量通过」「CER 只表示相对参考稿差异」。因此
本卡不自行发明阈值。

**裁决点（一个问题）**：M7 的「真实 ASR 质量」以什么形式验收？

- 选项 A（记录制）：三平台各交同一 `MERGED_SHA`、同一组样本、同一 `seg_duration/seg_overlap`
  下的 token 数、耗时、相对**已核实**参考稿的 CER 差异表；M7 只要求「三平台数字齐、来源可追、
  不做跨平台优劣结论」，不设通过阈值。
- 选项 B（阈值制）：由用户指定 CER 上限与耗时上限，再据此判定通过。
- 选项 C：先补一段可核实的人工标注样本，再定阈值（工作量最大）。

在用户裁决前，卡 B/C/D 只按选项 A 的**采集**部分执行，不下质量结论。

第二个待裁决（非阻塞本卡，可与卡 E 一起问）：M7 是否要求把 CPU/RSS 收进基线工具，还是继续
沿用「工具外一次性监控」的既有做法。现有指南明写工具不测 CPU/RSS；本卡不擅自扩工具。

## 7. 与其他在途卡的协作边界

- 会话 `dlg-20261006-023326-a6bee5`（scope `docs/sessions/261006-issue-root-fixes/`）正在写
  `design.md` 与 `progress/design-preflight-progress.md`。**本卡不写入该目录、不引用其结论**。
- #76 / #81 / #85 / #87 的设计与代码由其他会话推进。本卡只读不写。
- 本卡私有 state 目录不入仓。
- 共享 checkout 有六个未跟踪脚本，属主脑所有；本卡在独立 worktree，未触碰。

## 8. 本卡的明确边界

未做：不跑全量/grid、不改应用/测试/依赖/CI、不改 `GOALS.md` 或 M6/M7 状态、不推进或合并
PR #82、不部署或停止生产、不下载模型、不生成或改动用户录音、不读原失败日志与录音、不读
凭据/私 transcript/原音频、不 SSH 远程环境。

本卡只做：只读核实 + 可派卡计划。原 M7 契约已能覆盖的部分只补差分规划，不新发明质量阈值、
不新造工具。