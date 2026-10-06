# 历史产物清账（#81）

## 这是什么

#81 要求给历史分支产物一个**可核查的去向**：每个候选路径有精确来源、当前消费者证据和明确处置。
本文件是面向人的入口；机器可读数据在同会话目录下：

| 文件 | 作用 |
| --- | --- |
| [`docs/sessions/261006-issue-root-fixes/artifact-inventory.tsv`](../../sessions/261006-issue-root-fixes/artifact-inventory.tsv) | 147 个路径 × 5 栏。`baseline_state` 只说基线有没有该路径；`source_records` 逐条写 `ref@fullsha=source_state`，源侧存在性**独立**判定；`current_consumer_evidence`；`disposition` |
| [`docs/sessions/261006-issue-root-fixes/artifact-history-appendix.md`](../../sessions/261006-issue-root-fixes/artifact-history-appendix.md) | 当前交付结论依赖的历史审查/否决证据，逐字摘录 + 恢复指针 |
| [`docs/sessions/261006-issue-root-fixes/progress/artifact-disposition-progress.md`](../../sessions/261006-issue-root-fixes/progress/artifact-disposition-progress.md) | 三阶段进度存档与每阶段结论 |

盘点基线：`e849c21748392ad848131e07ff17d32e4cc83a8b`（含 PR #84、#86）。

## 原则（四条，违反其一就是错账）

1. **不以祖先关系判未交付**。分支头不在主干祖先集合内，只能说明**无法仅凭祖先关系**判定它是否已进主干（squash / rebase 会打断祖先链）；判交付要看 blob 比较与基线路径状态。
2. **不以缺失数归零作关单条件**。本轮结果就是「113 个路径基线不存在且已逐项定去向」，不是零。
3. **不改写历史结论**。旧否决不是当前红；新验收不回洗旧时点；两个时点各自带 SHA。
4. **没有当前需求证据的代码本轮有意不恢复**。不恢复 ≠ 永久退役（见下方「重开条件」）。

## 两套口径，不能混用

| 口径 | 数字 | 来源与状态 |
| --- | --- | --- |
| 原工单 tracked 产物口径 | 约 65 项产物 / 38 份审查 | 来自 #81 工单正文。**本轮远端 API 不可用，未能逐字复核其定义**，只作口径名引用，不作本卡判据 |
| 宽归档快照口径（本表） | 449 条 ref+path 记录 / 147 路径 / 其中 113 路径基线不存在 | 本地 Git 对象全量扫描的结果。排除本轮新建的 6 个 card ref 后为 **445/143/109**，与顾问数字逐项一致。**扫描时的 ref 总数（当次 337，后续重跑 338）只是那次扫描的运行记录，不是已冻结、可独立重建的分母**；本表不靠它做任何判定 |

宽口径比工单口径宽，因为它包含回收档案（`refs/reclaimed/**`）中的**未跟踪快照**：`.untracked`
提交带进 `logs/`、`retro/`、`memory/`、`sdk/*.egg-info/`、`.agents/`、`.cursor/`、`GEMINI.md`
等运行痕迹与代理工具配置。这些只登记来源与排除原因，**不复制内容**（私有记忆与日志不进公开仓）。
因此「109 > 65」「37 ≠ 38」都属口径差，不是数据打架。

## 判据与对照（这些数字怎么来的，可复跑）

- **来源只用 Git 对象**：`git log --diff-filter=A base..ref --name-only` + `git ls-tree`，不用工作区文件，
  不用陈旧 checkout。
- **源存在性与基线存在性分开判**（三类，不得互相代替）：
  - 基线侧 `baseline_state`：`EXISTS_AT_BASE`（34 路径）/ `MISSING_AT_BASE`（113 路径）。
  - 源侧 `source_state`（449 条记录逐条）：`BLOB_SAME_AS_BASE` 22 条、`BLOB_DIFF_FROM_BASE` 28 条、
    **`BLOB_BASE_MISSING` 360 条（源里确实有这个 blob，只是基线没有该路径）**、`NO_PATH` 39 条
    （有效 commit 下确无此路径，其中 31 条基线也缺、8 条基线有）。
  - `OBJECT_UNAVAILABLE`（该 full SHA 在本对象库不可解析为 commit，例如新克隆未取齐历史对象）与
    `QUERY_ERROR`（查询本身报错）**都不是缺路径**，单独记账，不并入 `NO_PATH`。
- **正负对照**：`docs/README.md` → 存在（返回 blob SHA）；`docs/__no_such_file_261006__.md` → `NO_PATH`；
  40 个 0 的假 SHA → `OBJECT_UNAVAILABLE`。三者三态分开，判据不是恒真。
- **消费者证据的证据强度**：全路径字面检索只能证明「没有字面出现」，**不能据此宣称无人引用**（引用可能用
  相对链接、basename 或只写 SHA）。本表登记为「基线树未见文档链接指向，未逐条证实」；谁要断言
  「无消费者」，需自己按链接/basename + 适用 SHA 再核一次。

## 去向分类与关单谓词

`disposition` 栏取值与对应谓词（谓词是**每项都要满足**，不是数文件）：

共 **10 类**，逐类计数如下（与 TSV 逐行解析结果相等，合计 147）：

| disposition | 数量 | 关单谓词 |
| --- | --- | --- |
| `content-in-baseline-no-action` | 17 | 所有可读来源与基线**同 blob**：内容已在基线树，无需动作。同 blob 只证明内容在底座，不证明合并方式 |
| `baseline-has-later-divergent-content` | 17 | 存在与基线**不同 blob 的可读来源**，且基线该路径最后修改提交**晚于**该来源提交。每行写明采用比较对象 `ref@fullsha` 与两个时间。**只断言内容层事实**（同路径、基线较晚、内容不同），未逐条做语义核查，**不等于语义上已被取代**；无时间证据或无可读来源时构建脚本 fail fast，不静默分类 |
| `archive-pointer-old-process` | 77 | 纯旧过程：`git show` 指针可读，不进主干，不复制 |
| `archive-pointer-current-dependency` | 2 | 当前结论依赖的历史证据，已进 appendix 逐字摘录 |
| `archive-pointer-association-unverified` | 1 | 泛称引用关联未证实，如实标注，不升级为证据 |
| `excluded-content-not-copied` | 18 | 运行日志 / `retro/` 顾问日志 / `memory/` 私有记忆 / `sdk/*.egg-info` 构建产物 / `.agents` `.cursor` `GEMINI.md` 代理工具配置：**只登记来源与排除原因，不复制内容**（含 `logs/` 5、`retro/` 2、`memory/` 4、egg-info 4、代理配置 3） |
| `not-restored-scope-decided` | 6 | 六项旧资产，本轮有意不恢复（见下节）。注意：它们在源对象里**确实存在 blob**，只是基线没有；本轮不恢复是需求决定，不是「文件找不到」 |
| `superseded-path-registered` | 1 | 旧路径被基线新路径取代（`docs/testing.md` → `docs/development/testing.md`） |
| `in-flight-issue-82` | 4 | #82 的 PR 在途交付，不复制、不当已解决 |
| `in-flight-other-card` | 4 | 本轮其它卡的产物（设计 SHA `8e93f7e4` 等），不属 #81 |

## 公开自包含复算入口（克隆者可直接跑）

把下面代码块存成 `verify_artifact_disposition.py` 放在仓库根，运行 `python3 verify_artifact_disposition.py`。
它**只校已冻结的交付物**（TSV 的 449 条来源记录、附录 5 段摘录、本仓文档链接），不扫描整机 refs、
不重审历史报告、不引入任何依赖或 CI 步骤。四道关：逐条复算 source_state（**来源不可核即失败，不默认 PASS**）、三个负控（虚构路径 / 假 SHA /
同 blob 不得判「基线含较晚不同内容」）、摘录按**连续完整行字节**核对（含顺序/相邻/空行）并带首字符变异负控、
文档链接。退出码 0 = 全过。

反例对照（本卡在真实树实测，非沙箱逻辑判断）：把 TSV 任一来源 SHA 换成不存在的 SHA → 报
`来源不可核` 并退出非零；把附录某段摘录的两行换序 → 报「不是连续原文」并退出非零；两者还原后回到
`RESULT: PASS`。

```python
#!/usr/bin/env python3
"""#81 清账交付物自检入口（公开、自包含、无外部依赖）。"""
import os
import re
import subprocess
import sys

REPO = os.environ.get("CAPSWRITER_REPO") or os.path.dirname(os.path.abspath(__file__))
BASE = "e849c21748392ad848131e07ff17d32e4cc83a8b"
TSV = "docs/sessions/261006-issue-root-fixes/artifact-inventory.tsv"
APPENDIX = "docs/sessions/261006-issue-root-fixes/artifact-history-appendix.md"
DOCS = [
    "docs/development/known-issues/artifact-disposition-261006.md",
    "docs/development/testing.md",
    "docs/sessions/261006-issue-root-fixes/artifact-history-appendix.md",
    "docs/sessions/261006-issue-root-fixes/progress/artifact-disposition-progress.md",
    "docs/sessions/261006-issue-root-fixes/reviews/artifact-review1-verdict.md",
    "docs/sessions/261006-issue-root-fixes/reviews/artifacts-review2-verdict.md",
]
READABLE = ("BLOB_SAME_AS_BASE", "BLOB_DIFF_FROM_BASE", "BLOB_BASE_MISSING")
DIFF_CONTENT = "baseline-has-later-divergent-content"
fail = []


def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, errors="replace")


def tree(rev, path):
    """→ (kind, blob)；kind ∈ BLOB / NO_PATH / OBJECT_UNAVAILABLE / QUERY_ERROR"""
    v = git("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    if v.returncode != 0:
        return ("OBJECT_UNAVAILABLE", "")
    p = git("ls-tree", rev, "--", path)
    if p.returncode != 0:
        return ("QUERY_ERROR", "")
    if not p.stdout.strip():
        return ("NO_PATH", "")
    f = p.stdout.strip().split("\n")[0].split()
    return ("BLOB", f[2]) if len(f) >= 3 and f[1] == "blob" else ("QUERY_ERROR", "")


def observed(sha, path):
    kind, blob = tree(sha, path)
    if kind != "BLOB":
        return kind, ""
    b = tree(BASE, path)
    if b[0] == "BLOB":
        return ("BLOB_SAME_AS_BASE" if b[1] == blob else "BLOB_DIFF_FROM_BASE"), blob
    if b[0] == "NO_PATH":
        return "BLOB_BASE_MISSING", blob
    return "QUERY_ERROR_BASE_" + b[0], blob


rows = open(os.path.join(REPO, TSV), encoding="utf-8").read().rstrip("\n").split("\n")
assert rows[0].split("\t") == ["path", "baseline_state", "source_records",
                               "current_consumer_evidence", "disposition"], "TSV 表头变了"
checked = unavailable = 0
for i, line in enumerate(rows[1:], start=2):
    path, _bstate, srcs, ev, disp = line.split("\t")
    if not (srcs.strip() and ev.strip() and disp.strip()):
        fail.append(f"line {i}: 有空来源/证据/去向格")
        continue
    for entry in srcs.split(" "):
        ref_sha, _, state = entry.rpartition("=")
        sha = ref_sha.split("@", 1)[1]
        got, _blob = observed(sha, path)
        if got == "OBJECT_UNAVAILABLE" or got.startswith("QUERY_ERROR"):
            # 真·来源不可核：走既有 fail 渠道，不得默认 PASS（合法态只有 NO_PATH 与各 BLOB_*）
            unavailable += 1
            print(f"  UNAVAILABLE {path} {sha[:12]} recorded={state} observed={got}")
            fail.append(f"line {i}: {path} {sha[:12]} 来源不可核（{got}），本轮不能算通过")
            continue
        checked += 1
        if got != state:
            fail.append(f"line {i}: {path} {sha[:12]} 记录 {state} 与实况 {got} 不符")
print(f"[1] 冻结盘点表：已核 {checked} 条来源记录，状态不符 {len(fail)} 条；"
      f"来源不可核 {unavailable} 条（不可核即失败，不计入通过）")

any_sha = rows[1].split("\t")[2].split(" ")[0].rpartition("=")[0].split("@", 1)[1]
k1, _ = tree(any_sha, "docs/__no_such_file_261006__.md")
print(f"[2a] 负控 有效SHA+虚构路径 → {k1}（期望 NO_PATH；这是预期查询，不是来源不可核）")
if k1 != "NO_PATH":
    fail.append(f"负控 2a 不成立：{k1}")
k2, _ = tree("0" * 40, "docs/README.md")
print(f"[2b] 负控 不存在的SHA → {k2}（期望 OBJECT_UNAVAILABLE/QUERY_ERROR，不得 NO_PATH）")
if k2 == "NO_PATH":
    fail.append("负控 2b 不成立：把不可用对象判成缺路径")
mis = []
for line in rows[1:]:
    path, _b, srcs, _ev, disp = line.split("\t")
    states = [e.rpartition("=")[2] for e in srcs.split(" ")]
    if disp == DIFF_CONTENT:
        readable = [s for s in states if s in READABLE]
        if not any(s == "BLOB_DIFF_FROM_BASE" for s in readable):
            mis.append(path)
print(f"[2c] 负控 同blob+缺来源 不得判「基线含较晚不同内容」：违例 {len(mis)} 条 {mis[:3]}")
if mis:
    fail.append(f"负控 2c 违例：{mis[:3]}")

text = open(os.path.join(REPO, APPENDIX), encoding="utf-8").read()
blocks = re.findall(r"<!-- source-check: (\S+) (\S+) (\S+) -->\n```text\n(.*?)\n```\n", text, re.S)
print(f"[3] 摘录 {len(blocks)} 段（按连续完整行字节核对：顺序/相邻/空行都算）")
if not blocks:
    fail.append("附录未解析到任何 source-check 摘录")
for refsha, apath, ident, body in blocks:
    sha = refsha.split("@", 1)[1]
    c = git("show", f"{sha}:{apath}")
    if c.returncode != 0:
        fail.append(f"摘录源不可读 {ident}: {sha}:{apath}")
        continue
    src = c.stdout
    block_lines = body.split("\n")
    if not any(x.strip() for x in block_lines):
        fail.append(f"摘录 {ident} 为空")
        continue
    needle = "\n".join(block_lines) + "\n"
    if needle not in src:
        loose = [x for x in block_lines if (x + "\n") not in src]
        if loose:
            why = f"缺行 {loose[0][:40]!r}"
        else:
            why = "行都在但顺序/相邻关系或空行被改动（字符成员相同不等于连续原文）"
        fail.append(f"摘录 {ident} 与源对象不是连续原文：{why}")
        continue
    mutated_lines = ["X" + block_lines[0][1:]] + block_lines[1:]
    if ("\n".join(mutated_lines) + "\n") in src:
        fail.append(f"摘录判据对 {ident} 不敏感（首字符变异后仍连续匹配，判据恒真）")
print("[3] 摘录连续性 + 首字符变异负控完成")

broken = []
for d in DOCS:
    p = os.path.join(REPO, d)
    if not os.path.exists(p):
        broken.append(d + "（文件本身不存在）")
        continue
    base_dir = os.path.dirname(p)
    for t in re.findall(r"\[[^\]]*\]\(([^)#]+)", open(p, encoding="utf-8").read()):
        if t.startswith(("http://", "https://", "mailto:")):
            continue
        if not os.path.exists(os.path.normpath(os.path.join(base_dir, t))):
            broken.append(f"{d} -> {t}")
print(f"[4] 文档链接断链 {len(broken)} 条 {broken[:3]}")
fail.extend(broken)

print("RESULT:", "PASS" if not fail else "FAIL")
for f in fail[:20]:
    print("  FAIL:", f)
sys.exit(0 if not fail else 1)
```

覆盖限制（真实说明）：脚本依赖**持有本地归档对象的仓库**。新克隆若未取齐历史对象，对应来源会报
`OBJECT_UNAVAILABLE`——那是**对象不可用**，不是「来源缺路径」，脚本会逐条打印而不是静默通过。
本仓不承诺公开全部旧过程文档与私有快照，因此不为此发布私有原文，也不另造归档机制。

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
关闭 #81 的判定：上表 10 类 disposition 逐项有去向、引用可读、历史结论未被改写、
`docs/development/testing.md` 描述与实际 CI 一致；由 Pi 主脑核对后在 #81 记录决定人与日期再按谓词关单。