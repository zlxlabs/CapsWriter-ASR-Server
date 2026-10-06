# 历史产物清账（#81）

## 这是什么

#81 要求给历史分支产物一个**可核查的去向**：每个候选路径有精确来源、当前消费者证据和明确处置。
本文件是面向人的入口；机器可读数据在同会话目录下：

| 文件 | 作用 |
| --- | --- |
| [`docs/sessions/261006-issue-root-fixes/artifact-inventory.tsv`](../../sessions/261006-issue-root-fixes/artifact-inventory.tsv) | 147 个路径 × 5 栏：`path` / `baseline_state` / `source_records`（`ref@fullsha=blob状态`，多出处全列）/ `current_consumer_evidence` / `disposition` |
| [`docs/sessions/261006-issue-root-fixes/artifact-history-appendix.md`](../../sessions/261006-issue-root-fixes/artifact-history-appendix.md) | 当前交付结论依赖的历史审查/否决证据，逐字摘录 + 恢复指针 |
| [`docs/sessions/261006-issue-root-fixes/progress/artifact-disposition-progress.md`](../../sessions/261006-issue-root-fixes/progress/artifact-disposition-progress.md) | 三阶段进度存档与每阶段结论 |

盘点基线：`e849c21748392ad848131e07ff17d32e4cc83a8b`（含 PR #84、#86）。

## 原则（四条，违反其一就是错账）

1. **不以祖先关系判未交付**。分支头不是主干祖先只说明合并方式（squash / rebase），不说明内容是否已交付。
2. **不以缺失数归零作关单条件**。本轮结果就是「113 个路径基线不存在且已逐项定去向」，不是零。
3. **不改写历史结论**。旧否决不是当前红；新验收不回洗旧时点；两个时点各自带 SHA。
4. **没有当前需求证据的代码本轮有意不恢复**。不恢复 ≠ 永久退役（见下方「重开条件」）。

## 两套口径，不能混用

| 口径 | 数字 | 来源与状态 |
| --- | --- | --- |
| 原工单 tracked 产物口径 | 约 65 项产物 / 38 份审查 | 来自 #81 工单正文。**本轮远端 API 不可用，未能逐字复核其定义**，只作口径名引用，不作本卡判据 |
| 宽归档快照口径（本表） | 337 refs / 449 条 ref+path 记录 / 147 路径 / 其中 113 路径基线不存在 | 本地 Git 对象全量扫描。排除本轮新建的 6 个 card ref 后为 **445/143/109**，与顾问数字逐项一致 |

宽口径比工单口径宽，因为它包含回收档案（`refs/reclaimed/**`）中的**未跟踪快照**：`.untracked`
提交带进 `logs/`、`retro/`、`memory/`、`sdk/*.egg-info/`、`.agents/`、`.cursor/`、`GEMINI.md`
等运行痕迹与代理工具配置。这些只登记来源与排除原因，**不复制内容**（私有记忆与日志不进公开仓）。
因此「109 > 65」「37 ≠ 38」都属口径差，不是数据打架。

## 判据与对照（这些数字怎么来的，可复跑）

- **来源只用 Git 对象**：`git log --diff-filter=A base..ref --name-only` + `git ls-tree`，不用工作区文件，
  不用陈旧 checkout。
- **三态查询，不是两态**：路径存在性用 `git ls-tree` 判定——stdout 空 = 不存在（`MISSING`）；
  非零退出 = 查询错误（`ERROR_*`）。**查询错误绝不并入 MISSING**。
- **正负对照**：`docs/README.md` → 存在（返回 blob SHA）；`docs/__no_such_file_261006__.md` → 不存在；
  非法 rev（40 个 0）→ `rc=128 / fatal: not a tree object`，与前两者分开记账。
- **消费者证据**：`git grep -F` 在基线树上按全路径计命中数，16 个路径有提及（多是代码文件被文档引用）；
  本文登记的文档类历史路径**命中为 0**，即主干无人引用。

## 去向分类与关单谓词

`disposition` 栏取值与对应谓词（谓词是**每项都要满足**，不是数文件）：

| disposition | 数量 | 关单谓词 |
| --- | --- | --- |
| `content-in-baseline-no-action` | 16 | 内容逐 blob 已在基线树；无需动作。同 blob 只证明内容在底座，不证明合并方式 |
| `superseded-in-baseline` | 18 | 基线已有更新版本；历史版本不合并，只登记来源 |
| `archive-pointer-old-process` | 77 | 纯旧过程：`git show` 指针可读，不进主干，不复制 |
| `archive-pointer-current-dependency` | 2 | 当前结论依赖的历史证据，已进 appendix 逐字摘录 |
| `archive-pointer-association-unverified` | 1 | 泛称引用关联未证实，如实标注，不升级为证据 |
| `excluded-content-not-copied` | 18 | 运行日志 / `retro/` 顾问日志 / `memory/` 私有记忆 / `sdk/*.egg-info` 构建产物 / `.agents` `.cursor` `GEMINI.md` 代理工具配置：**只登记来源与排除原因，不复制内容**（含 `logs/` 5、`retro/` 2、`memory/` 4、egg-info 4、代理配置 3） |
| `superseded-path-registered` | 1 | 旧路径被基线新路径取代（`docs/testing.md` → `docs/development/testing.md`） |
| `not-restored-scope-decided` | 6 | 六项旧资产，本轮有意不恢复（见下节） |
| `in-flight-issue-82` | 4 | #82 的 PR 在途交付，不复制、不当已解决 |
| `in-flight-other-card` | 4 | 本轮其它卡的产物（设计 SHA `8e93f7e4` 等），不属 #81 |

## 六项旧资产：需求边界与重开条件

来源统一为 `refs/heads/card/public-quality-260926@44690dbb1def6ea8a5e679fea16388c6394f8f89`。
基线树对六项**既无同路径、也无同 blob 副本**。本轮**有意不恢复**，理由与重开条件逐项如下：

| 资产 | 本轮不恢复的理由（需求边界） | 重开条件 |
| --- | --- | --- |
| `scripts/gate-quality` | 现行 gate 走 Required Gate v2 调用方（`gate.yml`）+ `zlxlabs/gate`，仓内门禁逻辑无第二实现。基线 `docs/sessions/261003-http-completion/reviews/pr64-canonical-risk-verdict.md:17` 已记载「本仓无 Makefile/`scripts/gate-quality`；gate-v2 quality 走 legacy，无 `lint:` 则跳过」 | 出现**必须由仓内脚本执行**的门禁需求（如需要固定 argv 的仓内 lint 入口），且有人给出消费者 |
| `tests/test_gate_quality.py` | 其测试需求的一部分已被 `.github/workflows/ci.yml` 的 pytest 矩阵承担；旧入口的固定 argv / 子进程契约无现行消费者证据 | 需要锁定旧入口的 argv 契约本身（例如有人以该契约为被测对象） |
| `.github/workflows/gate-shadow.yml` | 独立 shadow caller，与现行 `gate.yml`（Required Gate v2 caller）**不等价**，不能互相顶替；当前无 shadow 需求 | 明确要求「同一提交双门禁并行、shadow 不阻塞」且指定消费方式 |
| `.devcontainer/devcontainer.json` | 旧开发 workspace 组合，当前 CI 不消费 | 明确要求容器内开发环境（且给出镜像/依赖锁定方式） |
| 根 `pyproject.toml` | 当前测试与运行入口是 `uv run --no-project` + 显式 `--with` 列表，不读根 `pyproject.toml` | 决定改用根 pyproject 作为依赖声明（须同时决定 `uv.lock` 的去留） |
| 根 `uv.lock` | 与根 pyproject 同属旧 workspace，`--no-project` 下不消费 | 同上（锁文件只在有根 pyproject 时才有意义） |

**边界**：以上六项是「本轮不恢复」，不是「永久退役」，也不是「已被取代」这一既成事实。
需要时按「重开条件」重新评估，不因本表存在就默认已关闭。

## 本轮同时订正的一处事实

[`docs/development/testing.md:18`](../testing.md) 原写「上游单测与 **lint** 由 ci.yml 跑」。实际
`.github/workflows/ci.yml` 只有 pytest 相关步骤（含五轮矩阵工件结构校验），**没有任何 lint 步骤**，
且 `pr64-canonical-risk-verdict.md:17` 记有「单元 CI 只跑 pytest，不检 F401」。本卡只把该句订正为
实际 CI 行为，**不新增 lint 流程、不恢复旧 lint 入口**（见上表 `scripts/gate-quality`）。

## 已知误用风险

- 拿「109 个基线不存在」当欠账数量 → 错：其中 18 个是运行痕迹/私有记忆/构建产物，本就不该进仓。
- 拿「65 / 38」当本卡现状 → 错：那是工单口径，本表是宽归档口径。
- 拿「分支头不在主干祖先」当代码未交付 → 错：`core/server/http_file_runner.py` 等 34 个路径基线都有。
- 拿旧 `m6-final-evidence-audit.md` 的「原完成条件未达」说当前 M6 未完成 → 错：完成结论冻结在
  `796104c`，两者是不同时点，见 appendix 第 2 节。
- 拿 appendix 里的历史 P2 说当前实现有 P2 缺陷 → 错：`E1-owner-review-A-verdict.md` 的 P2 已在基线
  `design.md:26` 被显式保留为**冻结行为**，不是待修缺陷。

## 关单与边界

本卡**只交付证据**，不改 #81 的状态、不关单、不替其他主脑关闭 issue/PR、也不回洗 M6 历史验收。
关闭 #81 的判定：上表 9 类 disposition 逐项有去向、引用可读、历史结论未被改写、
`docs/development/testing.md` 描述与实际 CI 一致；由 Pi 主脑核对后在 #81 记录决定人与日期再按谓词关单。