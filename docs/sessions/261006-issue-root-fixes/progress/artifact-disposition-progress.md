# #81 历史产物清账进度存档

- 当前阶段：阶段一「候选核对」完成。盘点表 `artifact-inventory.tsv` 已生成（147 个路径 / 449 条 ref+path 记录），来源全部取自真实 Git 对象，未使用工作区文件。
- 本段结论：基线 `e849c21748392ad848131e07ff17d32e4cc83a8b` 下 34 个路径已存在（16 个逐 blob 相同、18 个被基线更新版本取代），113 个基线不存在。每个路径都有 `source_records`（精确 ref@fullsha=blob 状态）、`current_consumer_evidence`、`disposition` 四栏，无空去向。
- 口径分离：顾问口径（排除本轮新建的 6 个 card ref）复现为 445 记录 / 143 路径 / 109 基线不存在，与顾问数字逐项一致；本表含本轮 6 个 ref 故为 449/147/113。原工单 tracked 产物口径（约 65 项 / 38 份审查）是另一口径，不与本表混用，来源见 known-issues 文档。
- 关键决策与已否决方案：不按「squash 后非祖先」判未交付；不按缺失数归零作关单条件；不整包合历史分支；不复制日志/retro/memory/egg-info 内容（只记来源与排除原因）；不判基线已有路径为未交付。
- 下一步唯一动作：阶段二把当前交付结论依赖的历史审查/否决证据写入 `artifact-history-appendix.md`，并对 `docs/development/testing.md` 的 CI 描述只做事实订正。

---

- 当前阶段：阶段二「历史证据」完成。`artifact-history-appendix.md` 已写入 5 段逐字摘录 + 7 条指针。
- 本段结论：当前交付确实依赖两份历史证据——E1 owner 审查 A 的 P2 判定段（基线 `docs/sessions/261001-http-files/design.md:24,26` 保留其量化契约与 P2 分级）与 M6 在 `9024008` 时点的证据盘点（基线 `m6-final-merged-acceptance.md:12` 把完成结论冻结在 `796104c`）。两者的原文判定段已整段保留并带 `source-check` 注释。
- 逐字校验：`verify_sources.py` 报 5 块全部 `missing=0`，每个块的负控（改首行一个字符）均不再命中；`cross_control.py` 把每块放到另外两个证据源，全部匹配失败（判据有约束力，不是恒真）。校验只依赖 `git show` 的对象字节。
- 关键决策与已否决方案：`design.md:5` 的「独立规划终审历史没有完整覆盖」是泛称，`eng-outside-verdict.md` 与它的关联**未证实**，如实标注不升级为证据；两份 m6-repeat-matrix 过程 verdict 只留指针（当前 H1/H2 三审在基线有同名文件，非同一文件，全仓 0 引用）；#82 的三份 Windows 证据标在途，不复制不重复交付。
- 下一步唯一动作：阶段三写人类消费者文档 `docs/development/known-issues/artifact-disposition-261006.md`，并只订正 `docs/development/testing.md` 里「单测与 lint 由 ci.yml 跑」这一处与实际 CI 不符的描述。

---

- 当前阶段：阶段三「人类导航」完成，三阶段全部结束；本卡产物已提交并推送，开 draft PR（不自动关闭 #81）。
- 本段结论：`docs/development/known-issues/artifact-disposition-261006.md` 写明范围/四条原则/两套口径/判据与对照/10 类去向的关单谓词（六项旧资产逐项需求边界与重开条件）/已知误用风险；`docs/development/testing.md:18` 已由「单测与 lint 由 ci.yml 跑」订正为「单测由 ci.yml 跑（只有 pytest 步骤，没有 lint 步骤）」，未新增任何 lint 流程。
- 交付校验：`verify_deliverables.py` 通过——本卡 4 份文档的相对链接全部可解析；TSV 147 行、每行 5 栏、`disposition` 与证据格无空缺；known-issues 里的 10 类计数与 TSV 实际逐项相等；负控（空证据格）被判不合格为 True。
- 关键决策与已否决方案：六资产写「本轮有意不恢复 + 重开条件」，不写「永久退役」也不写「已被取代」；不新增扫描工具/常驻状态/第二套门禁；不复制日志、retro、memory、egg-info、代理工具配置内容；不改 #81 状态、不关单、不回洗 M6 验收。
- 下一步唯一动作：Pi 主脑核对本卡证据后，在 #81 记录决定人与日期，再按 known-issues 文档里的关单谓词关单。

---

## 阶段四：独立审查 verdict（`reviews/artifact-review1-verdict.md`，commit `6633b74e`）的分诊与有限修复

- 固定审查范围 `e849c21..ca370b88`；verdict 全文以 cherry-pick（`391d1d1`）原样纳入，**未改写一个字**，
  包括其中对本卡不成立的 P2-4。审查者自报 outcome failed（调查超 25 次/15 分钟），其源对象复算与摘录
  字节检查在本卡采纳，但不因此把那次审查当作完整通过。

| finding | 分诊 | 实际动作与输出 |
| --- | --- | --- |
| P2-1 源状态被基线状态代替 | **采纳** | 449 条 source 记录逐条重查源 entry：`BLOB_SAME_AS_BASE` 22、`BLOB_DIFF_FROM_BASE` 28、`BLOB_BASE_MISSING` **360**、`NO_PATH` 39；`OBJECT_UNAVAILABLE` 与 `QUERY_ERROR` 独立成态。六项资产现在显示源里确有 blob（如 `scripts/gate-quality` = `031664bd8e46…`），不再是「MISSING」。承恢复谓词的 147 个路径**全部**至少有一个可读精确来源（`paths_without_readable_source=0`） |
| P2-2 同 blob 被归「已被更新版取代」 | **采纳** | `progress/m4-plan-progress.md` 改判 `superseded-in-baseline` → `content-in-baseline-no-action`：其唯一含内容的来源 `7ab35518…` 与基线同 blob `eae8afb6…`，另一来源 `ff0f2ddd…` 是 `NO_PATH`，无任何不同 blob 支持「取代」。全表重算后仅此 1 处去向变化 |
| P2-3 复核脚本只在本机 `/tmp` | **采纳** | known-issues 新增「公开自包含复算入口」代码块（只校已冻结 inventory 与引用，不新增扫描器/CI/依赖）；本卡树内按该入口实跑一次，输出见下。本机 `/tmp` 脚本降为副产物 |
| P2-4 硬预算 350 超限 | **不成立（反驳）** | 350 是**审查卡**给新增 verdict 的预算，不是本实现卡的预算；本卡 `Diff-Lines-Hard=1500`，冻结 diff 为 392 行（391+1），未超。verdict 自身 61 行也未超 350。**因此不缩表、不造修复**，按分诊记录，不改实现 |
| P3-1 disposition 类别数不一致 | **采纳** | 修后实际为 **10 类**，计数 17/17/77/2/1/18/6/1/4/4 = 147，文档与逐行解析相等；同批修掉两处过强事实：「非祖先」改为「无法仅凭祖先关系判定」、全路径字面检索 0 命中不再宣称「无人引用」，337 refs 明确为**当次扫描运行记录**而非冻结分母 |

- 不动的边界：原工单 65/38 口径、六资产本轮不恢复边界与重开条件、`#82` 在途标注、历史适用 SHA
  （`d52f8687` / `69bee18d` / `4565bfcc` / `9024008` vs `796104c`）均**未变**。
- 本阶段验证：公开入口实跑 `RESULT: PASS`（449 条来源记录状态不符 0、三个负控成立、5 段摘录逐行一致、
  文档链接断链 0）；`git diff --check` 干净。

---

## 阶段五：R2 审查 verdict（`reviews/artifacts-review2-verdict.md`，50 行）与最后收口

- H0 = `9b49864`；R2 verdict 原文纳入（内容与原对象逐字相同，见本阶段回执）。审查者已独立核对
  449 source / 147 path / 10 类 / 五段摘录的真实 bytes 均正确；本阶段不重挖 refs、不重审 38 份、不恢复六资产。

| finding | 分诊 | 实际动作与输出 |
| --- | --- | --- |
| P2-1 来源不可用仍报 PASS | **采纳** | 公开入口第 1 关改为：`OBJECT_UNAVAILABLE` / `QUERY_ERROR` 走**既有 fail 渠道**（追加到 `fail`，直接影响 `RESULT` 与退出码），同时保留「已核 448 / 不可核 1」的分开计数。合法的 `NO_PATH`（预期查询）与各 `BLOB_*` 仍属已核态，不把 449 分母换成失败数 |
| P2-2 摘录只校行集合、放过重排 | **采纳** | 摘录校验收窄为**连续完整行字节**（顺序、相邻关系、空行都参与），不再转行集合、不丢空行、不 rstrip；失败走 `fail` 渠道报「不是连续原文」，不抛异常 |
| 语义取代措辞过宽（主脑收口第 4 条） | **采纳** | disposition `superseded-in-baseline` → **`baseline-has-later-divergent-content`**（17 行，计数不变）。只断言内容层事实（同路径、基线较晚、内容不同），**未逐条语义核查，不等于语义上已被取代**；TSV 证据格同步改写 |
| 摘录用途边界（收口第 4 条） | **采纳** | 附录写明：五段摘录只用于指定历史判断 + 适用 SHA，**不是完整审查结论**；承担完整结论的文件仍以原对象指针为准 |

- 反例对照（均在本卡真实树与真实 Git 对象上实测，非沙箱逻辑判断）：
  - 单 source 不可用：`已核 448 条来源记录…来源不可核 1 条` + `RESULT: FAIL` + 退出码 **1**（R2 实测此处为 PASS/0）。
  - 摘录两行换序：`RESULT: FAIL` + `行都在但顺序/相邻关系或空行被改动（字符成员相同不等于连续原文）` + 退出码 **1**。
  - 两处还原后回到 `RESULT: PASS` / 退出码 0；既有负控（假路径 `NO_PATH`、假 SHA 不得当 `NO_PATH`、同 blob 不得判「较晚不同内容」、首字符变异）仍全部有效。
- 顾问只读结论（capswriter-81-closure-261006）的沙箱 `.git` 失效只用于确认逻辑，**不冒充 Git 复核**；
  本阶段的 Git 事实全部来自上列本卡实测与 R2 独立实测。
- 边界未变：六资产本轮不恢复与重开条件、历史否决与两个时点、`#82` 在途、原 65/38 与宽归档口径、历史适用 SHA。