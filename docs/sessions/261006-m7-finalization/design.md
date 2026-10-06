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

- M6 验收冻结在 `796104c`；不替后来在 `e849c21` / `d251618` 上运行的源码背书。M6 完成状态
  （`goals/http-integration/M6-qa.md`、合并记录 `2bfe0f5` / `ee61475`）不因本卡推进而改变。
- M7 的 HTTP / 默认 WS 应用层字节、真实 ASR 质量、耗时与资源证据，必须取自**Windows 修复正式
  合并后的共同源码**。旧平台参考数（旧 492、Windows 21/25、POSIX 21/25、Linux 首测 4 次串行）
  一律不作为新源码资格。生产部署另需授权。
- 本卡不重新设计 HTTP 接口，只规划剩余交付。

### 已否决方案（不得在后续卡复活）

| 已否决 | 否决理由 | 来源 |
| --- | --- | --- |
| **无新输入地**盲跑 full / grid 找根因 | 同 head 已测两次仍红；第三次不产生新输入。注意：全量漏斗**仍是交付要求**（见 §2.3），此处否决的是把它当诊断手段而非免除它 | `windows-http-integrity-fix-progress.md`（PR82 head 内）两段实测 |
| 延长 timeout / sleep 让红变绿 | 4 个 `naked-shell` 失败中两种形态是「探针 120s 未产出报告」；加时间只是掩盖 | 同上，`test_http_cleanup` 15 passed / 4 failed |
| 重试直到绿 | 同上，且禁止用重试结果冒充资格 | 同上 |
| 旧 492 全量 / POSIX 21/25 / Windows 21/25 冒充新源码资格 | 这些数字归属源修 `9e0dd6db` 端点，PR 自身记录明确「不是本 head 新跑」 | `windows-http-integrity-fix-progress.md` |
| fake 模型 / stub 结果当 ASR 质量 | stub 只证明采集链路，不证明识别 | `m6-final-merged-acceptance.md:66` |
| 跨仓改 gate / 平台工具 | 门禁逻辑在 `zlxlabs/gate`；本卡不越权 | `docs/development/testing.md` |
| 生产服务改动或凭据调查 | 未授权 | 卡面非目标 |
| 把 PR #82 的 `O_BINARY` 局部已审当作全套件绿的证明 | 已审的是两行 `os.open`，不是套件结果 | PR82 body 自述 |

## 1. 核实方法与来源台账

只读调研，未运行产品代码、未启动服务、未下载模型、未读凭据或私有 transcript/音频/哈希。
命令输出缓存于本卡私有 state 目录，不入仓。

| 事实 | 来源 | 类型 |
| --- | --- | --- |
| 本卡 base `e849c21`，远端 master 同 SHA | `git ls-remote origin refs/heads/master` | 已测 |
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
| 本卡执行当时本机有非本卡的 pytest 长驻（PID 2431473，`tests/test_ws_progress_watchdog.py -k s1`，已运行 38090s） | `ps -o pid,lstart,etimes,cmd` | **本次观测**，非失败当时状态 |
| 本卡执行当时本机 20 核 / 49 GiB / systemd user `degraded` / 36 个 python 进程 / loadavg 3.59 5.42 7.06 | `nproc`、`/proc/meminfo`、`systemctl --user is-system-running`、`ps`、`/proc/loadavg` | **本次观测**，非失败当时状态 |
| M7 基线工具 `scripts/_baseline_http_ws.py` 与指南 `docs/guides/http-baseline.md` 已在主干 | `docs/guides/http-baseline.md`、`docs/development/testing.md` | 已测 |
| M7 Linux 首测已做过 4 次串行实测，但服务 SHA 是 `820c3a2`、工具 SHA `d4eab57` | `m7-linux-baseline-evidence.md` | 已测（旧源码，仅参考） |
| M7-baseline.md 的「已知阻塞：等待 E6」是旧描述，M6 已历史完成 | `goals/http-integration/M7-baseline.md` vs `goals/http-integration/M6-qa.md` | 已测（文档事实） |

GitHub API 调用共 11 次：PR 元数据、PR body、PR files、PR commits、master check-runs、master
run 的 jobs 列表、PR82 check-runs（两次，其中一次为取 job id）、两次 job log、`gh run list`。
在 15 次预算内。

上述 ps/负载/systemd 三行是**本卡执行当时的观测**，两次红发生在 2026-10-05，两者相隔约一天。
本卡**不**把它们当作失败当时的因果输入；历史当时的环境与版本状态 **unknown**。

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
5. **采集计数相等**：hosted `500+3=503`，本机 `55+421+3+24=503`。**这只证明计数相等**。无同次
   JUnit / node multiset 对照，**用例集合是否相同为 unknown**，不得据此排除集合差异。

### 2.2 结论（严格区分已测 / unknown）

- **已测**：
  - 这两次红不是 Windows 平台失败——PR82 自己的文档写明运行命令与依赖栈为 Linux 本机
    （来源：PR82 head 内 `windows-http-integrity-fix-progress.md` 两段）。
  - 该具名 Windows 二进制用例 `test_http_binary_payload_survives_append_recovery_and_commit_replay`
    在红场里 **passed**。
  - PR82 的生产改动与主干可无冲突合并，合并树保留两处 `O_BINARY` 与该新增测试。
- **unknown（不得写成结论）**：
  - 该用例 passed **只证明那一个用例通过**，**不证明** `O_BINARY` 改动没有在别处导致 55/24 中的
    任何失败。其余 79 个失败（45 failed + 24 errors）**无一被本卡归因**。
  - hosted 绿 / 本机红的差异原因 **unknown**。可能是环境、依赖版本、源码差异、或以上组合；本卡
    没有同次 JUnit / node 对照，也没有当时的依赖版本快照，**不能判定**。
  - 55/24 的**单一根因**仍 **unknown**。现有收据只到失败分布与首个异常类型，不到因果。本卡不发明根因。

### 2.3 最小根因验证（替代 full 重跑，但不得缩完成条件）

**不豁免交付要求**：PR #82 的**全量本地漏斗仍是正常交付要求**，本节只是在其之前加一次有诊断
价值的定向验证，**不替代**全量、不把未知红当噪音、也不在本计划里自授豁免。

必须至少覆盖**两个不同失效簇**各一个原具名 case（只跑 cleanup 的 4 条会漏掉 45+24 的 EOF 簇）：

| 簇 | 取哪个 case | 取法 |
| --- | --- | --- |
| 簇一：cleanup / `naked-shell` | `tests/test_http_cleanup.py` 中一个 `naked-shell` 参数用例 | 先 `--collect-only -q` 取准 node id，不凭记忆写 |
| 簇二：真实 `EOFError` 失败族 | 从原 JUnit 取**一个确认为 failed/error 的 EOF 具名 node** | 读原 JUnit 的 node 名；不自行猜哪个测试会 EOF |

执行要求：

- **同入口**：两个 case 都走 `python -m pytest tests/<file>::<node> -q -rs -p no:cacheprovider`
  这一个入口，与两次红的标准入口一致，不换入口。
- **环境与版本对照**：记录本次完整实际版本（Python / pytest / websockets / aiohttp / httpx /
  numpy / rich / colorama / soundfile / pytest-asyncio / ffmpeg）与 host，并从原两次红能取到的
  版本记录（PR82 文档已记 python 3.12.3 / websockets 15.0.1 等）列出**差异表**。没有差异表就没有
  环境假设的证据。
- **源码对照**：在同一 base（`fce9131a`）与同环境下取对照，不拿 master 的绿冒充 base 的绿。
- **child 退出签名**：对 EOF 簇那个 case，记录子进程**退出码与退出前最后信号**（不含私有正文）。
  这是把「EOFError 在 `_recv`」从症状推向因果的唯一现有抓手。
- **负载**：记录执行当时负载，**仅作描述**，不得当因果；一次安静环境下转绿**不能**证明负载相关。
- 预计耗时：定向两 case + 对照 ≤ 600s。隔离措施：独立 `TMPDIR`；不启停任何既有服务；只对自己
  启动的 PID 操作；不读原失败日志与录音。
- **判据约束力**：若只写「跑完仍红 / 转绿」，该判据无法区分环境、版本与源码三类假设；因此判据
  必须同时产出「版本差异表 + child 退出签名」，否则结论一律记 **unknown**，不得写「根因已定位」。

## 3. 基线工具与三平台可用性

### 3.1 已测：工具与契约现状

- 采集器 `scripts/_baseline_http_ws.py`，指南 `docs/guides/http-baseline.md`，均在主干。
- 生产消费者：HTTP 上传原始文件字节；默认 WS v2 走 `sdk/capswriter_asr/client.py` 的
  `transcribe_file(..., encoding="flac")`，音频放 UTF-8 JSON 文本帧 `data`（Base64），不发二进制帧。
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
| macOS | **本次读取范围未定位到**隔离树/样本/实测记录 | **unknown**；不等于不存在 | 本卡未穷举仓外与前链记录 |

### 3.3 未知项与获取入口（不发明）

| unknown | 获取入口 |
| --- | --- |
| macOS 隔离机器与既有入口 | **本卡读取范围未定位到**；由主脑从仓专属 memory / 前序链核实已有入口与授权，本卡不据此断言不存在 |
| 三平台真实 ASR 质量门槛 | 原设计未定阈值 → §6，状态 **pending**，由主脑问用户 |
| 三平台在**新共同 SHA** 上的可用性 | 合并后按 §4 卡 A/B/C/D 重测，不复用旧数 |
| MP3/AAC/M4A/Opus 样本是否齐备 | 原 M7 完成条件要求这些格式；**缺样本记为缺口**，不缩完成条件 → §4 卡 B/C/D |
| 真实 CPU/RSS | **沿用**原 M7 已要求的资源证据 = 工具外一次性进程树监控；**不新增裁决点，不扩工具**（工具当前不测 CPU/RSS 是既有事实） |

## 4. 最短交付计划（易变决策优先）

依赖图（与下文卡片小节一致）：`C1 → A → {B, C, D}`，三平台可并行；`E` 的**静态准备**可与 C1/A
并行，但 **E 的运行验收必须依赖它实际测试的 runtime SHA**，不能声称完全不依赖 `MERGED_SHA`。

### 卡 C1：解除 Windows 阻塞并正式合并 PR #82

- 目标：把 PR #82 从 Draft 推到正式合并，产出**共同 SHA**。
- 前置新输入：§2.3 的定向验证结论（**不豁免**全量本地漏斗；全量仍是本卡的正常交付要求）。
- 动作：先跑**全量本地漏斗**（与两次红同入口）作为交付要求，再叠加上一步的定向诊断；主脑裁定
  未定根因是否阻塞合并；若不阻塞，补齐 PR82 文档、更新 head、把 PR 标 ready、
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
- **不做**：不修改 `http_store.py` 之外的源码，不改测试来迎合绿，不因根因 unknown 而把全量
  降级为可选。

### 卡 A：冻结共同 runtime 并锁定基线工具版本

- 目标：产出「三平台都必须测的那个 SHA」，并确认基线工具与 SDK 版本在这条 SHA 上可用。
- 前置：C1 完成。
- 动作：记录合并后的 40 位 master SHA 为 `MERGED_SHA`；用 **git 精确 blob** 锁定基线工具
  版本（`git rev-parse MERGED_SHA:scripts/_baseline_http_ws.py` 与
  `git rev-parse <已知良好 SHA>:scripts/_baseline_http_ws.py` 比 blob id；必要时再用
  `git cat-file blob` 比字节），**不为此新建 AST 哈希框架**；确认 `docs/guides/http-baseline.md`
  的 Linux 隔离命令依赖闭包在 `MERGED_SHA` 上仍完整（含 `rich`、`colorama`，M7-review1 P2-1
  的教训）。
- 验证命令：`python -m pytest tests/test_http_baseline.py -q`（定向 11 项，不跑全量）；
  `git diff --check`；上述 `git rev-parse` blob 比对（无需临时脚本）。
- 预算：定向测试 ≤ 120s。
- 失败可见性：blob 不等或定向测试红即停，不进入三平台测量。
- 所需授权：无（只读 + 定向测试）。
- **不做**：不改工具逻辑、不加阈值、不加 fallback。

### 卡 B：Linux 隔离真实基线（`MERGED_SHA`）

- 前置：A。
- 动作：按 `docs/guides/http-baseline.md` 的「Linux 隔离运行」在隔离 checkout 检出
  `MERGED_SHA`，起 Paraformer 服务。**格式覆盖按原 M7 完成条件走**：WAV / MP4 / **MP3 / AAC /
  M4A / Opus**，每个格式 × HTTP/WS-v2 两个协议串行。已有的 WAV/MP4 四次只是**已知部分**，不
  当作格式覆盖已完。
- 缺口纪律：MP3/AAC/M4A/Opus 任一样本缺失或参考稿缺失，**记为缺口并保留在完成条件里**，不
  静默缩小覆盖、不把 WAV/MP4 结果外推成全格式结论。缺样本需向主脑报缺口并等入口。
- 关键：参考稿来源未核实就写 `unverified`；CER 只表示与该稿差异。私有路径、正文、哈希不进仓。
- 验证：每协议私有 JSON `status=ok`、final `is_final=true`、token/timestamp 数量相等、单调、
  覆盖、时长区间；stdout 只含匿名 ID 与字节/指标。
- 预算：单次协议 ≤ 240s（工具 `--timeout`）；全格式外层 ≤ 90min。失败可见性：非零退出 /
  `BASELINE_FAILED` 即停并原样记录签名，不重试、不换 ID 掩盖。
- 资源证据：按原 M7 已要求的口径，用**工具外一次性进程树监控**记峰值 RSS 与累计 CPU 时间，
  **不为此扩工具**。
- 所需授权：起隔离服务（非生产）；样本在主脑私有目录，本卡不复制。
- **不做**：不改样本、不生成录音、不下模型、不跑 grid。

### 卡 C：Windows 隔离真实基线（`MERGED_SHA`）

- 前置：A（与 B 可并行，各自独立机器）。动作：Windows 隔离 venv + 私有模型缓存目录软链，跑
  **同一组格式**（WAV / MP4 / MP3 / AAC / M4A / Opus × HTTP/WS-v2）串行；格式缺口纪律同卡 B。
- 关键：**ACL 必须在 Windows 实测**，不能用 Linux mode 位代证；`O_BINARY` 修复的效果在这条
  SHA 上由真实 producer 字节与磁盘字节相等来验，不复用 `9e0dd6db` 的旧字节表。
- 验证/预算/失败可见性：同卡 B。所需授权：Windows 机器与执行会话。

### 卡 D：macOS 隔离真实基线（`MERGED_SHA`）

- 前置：A + **主脑核实 macOS 隔离机器与样本的已有入口**（§3.2 本卡读取范围未定位到，不等于
  不存在）。
- 若确实无机器或样本：卡 D 阻塞，M7 不能宣告完成（缺一条平台证据 = unknown = 未完成）；同时
  按缺口纪律上报，不用其他平台结果顶替。
- 动作/验证/预算/可见性：同卡 B（含格式覆盖与资源监控）。

### 卡 E：部署说明与入口一致性核对

- **静态准备**（文档比对、旧入口枚举）可与 C1/A 并行，不依赖 `MERGED_SHA`。
- **运行验收必须依赖它实际测试的 runtime SHA**：从裸 shell/CI 隔离环境实走新旧两入口并核对
  health 的 `status`/`git_sha`/结果，这个 `git_sha` 就是被测 runtime；文档必须与**它实际测的
  那个 SHA** 一致。因此 E 的运行段不声称“完全不依赖 `MERGED_SHA`”——若它要跑最新主干，就依赖
  `MERGED_SHA`；若跑别的 SHA，文档结论就只覆盖那个 SHA。
- 目标：核对 `deploy/README.md`、`docs/guides/getting-started.md` 与实际入口一致——旧 WS 端口
  与默认行为保留、HTTP 显式启用且初始化失败即失败、不把 systemd `is-active` 当业务健康。
- 验证命令：从裸 shell/CI 隔离环境实际走新旧两入口并核对 health 白名单字段；只取白名单字段，
  不整段回显。
- 预算：静态 ≤ 半张卡；运行段 ≤ 1 张卡，不起生产。
- 失败可见性：任一入口与文档不符即开 issue，不改文档迁就实现。
- 所需授权：起隔离服务。

## 5. 关键不变式与每条的证据来源

| 不变式 | 需要什么证据算成立 | 现在在哪 |
| --- | --- | --- |
| HTTP 可靠原字节 | 源文件字节 = producer PATCH body = 磁盘物理字节 = SHA；弱网重发字节显式记录 | `tests/test_http_file_tasks.py::test_http_binary_payload_survives_append_recovery_and_commit_replay`（PR82 新增，合并树保留）；`http-baseline.md` 口径段 |
| 默认 WS 协议不变 | SDK 默认 `flac` + UTF-8 JSON 文本帧 + Base64，二进制帧 0 | `tests/test_http_baseline.py::test_ws_meter_observes_actual_sdk_v2_send_payload`；fixture `tests/fixtures/http_baseline_producer.json` |
| 完整结果可重新领取 | final `is_final=true`；token/timestamp 等长；跨连接领取 | `tests/test_http_baseline.py`（HTTP final 校验）；M6 五轮矩阵的跨连接领取样本 |
| 真实模型质量 | 真实模型 + 可核实参考稿；工具不判通过 | **未测**；旧 Linux 首测参考稿 `unverified` |
| 格式覆盖完整 | MP3/AAC/M4A/Opus 与既有 WS 基线均有字节/重发/质量/资源数据 | **未测**；旧首测只做了 WAV/MP4，缺口保留在完成条件里 |
| 字节口径分离 | 容器 / PCM / 重发三者分列，不相加、不互相冒充 | `docs/guides/http-baseline.md` 测量口径段 |
| 生命周期 / RSS / CPU | 工具外一次性进程树监控（沿用原 M7 已要求的资源证据口径） | 旧 Linux 首测一次性监控（服务 SHA `820c3a2`）；工具本身不测，不扩工具 |
| 部署说明与入口一致 | 裸 shell/CI 隔离环境实走两入口 | **未测**（卡 E） |
| 三平台同源 | 三平台都测同一个 `MERGED_SHA` | **未测**（卡 B/C/D） |

**规则**：以上任一条证据失败或缺失即记 `unknown`；缺任意一条不得宣告 M7 整体完成。

## 6. 质量门槛：pending，由主脑问用户

原设计（`goals/http-integration/M7-baseline.md` 与 `docs/guides/http-baseline.md`）**没有定真实
ASR 质量门槛**，且明确写了「`status=ok` 不是识别质量通过」「CER 只表示相对参考稿差异」。因此
本卡不自行发明阈值，**状态为 pending：需主脑向用户提问**，本卡不代问、不代决。

待主脑提问的候选（供提问用，不是本卡结论）：

- 选项 A（记录制）：三平台各交同一 `MERGED_SHA`、同一组样本、同一 `seg_duration/seg_overlap`
  下的 token 数、耗时、相对**已核实**参考稿的 CER 差异表；只要求数字齐、来源可追、不做跨平台
  优劣结论，不设通过阈值。
- 选项 B（阈值制）：由用户指定 CER 上限与耗时上限，再据此判定通过。
- 选项 C：先补一段可核实的人工标注样本，再定阈值（工作量最大）。

在用户回答前，卡 B/C/D 只按选项 A 的**采集**部分执行，不下质量结论。CPU/RSS **不在**待裁决项
——原 M7 已要求资源证据，沿用工具外监控即可（见 §3.3）。

## 7. 与其他在途卡的协作边界

- 会话 `dlg-20261006-023326-a6bee5`（scope `docs/sessions/261006-issue-root-fixes/`）正在写
  `design.md` 与 `progress/design-preflight-progress.md`。**本卡不写入该目录、不引用其结论**。
- #76 / #81 / #85 / #87 的设计与代码由其他会话推进。本卡只读不写。
- 本卡私有 state 目录不入仓。
- 共享 checkout 有六个未跟踪脚本，**归属本卡未核实**；本卡在独立 worktree，全程未触碰。

## 8. 本卡的明确边界

未做：不跑全量/grid、不改应用/测试/依赖/CI、不改 `GOALS.md` 或 M6/M7 状态、不推进或合并
PR #82、不部署或停止生产、不下载模型、不生成或改动用户录音、不读原失败日志与录音、不读
凭据/私 transcript/原音频、不 SSH 远程环境。本卡只做只读核实 + 可派卡计划；原 M7 契约已能覆盖
的部分只补差分规划，不新发明质量阈值、不新造工具。

本卡**未**把 55/24 归因于任何原因：平台（Linux）有 PR82 文档来源，根因 **unknown**；hosted 绿
与本机红的差异原因 **unknown**；用例 node 集合是否相同 **unknown**。