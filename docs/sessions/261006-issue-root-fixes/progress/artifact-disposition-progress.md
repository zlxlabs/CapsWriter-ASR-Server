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
- 本段结论：`docs/development/known-issues/artifact-disposition-261006.md` 写明范围/四条原则/两套口径/判据与对照/9 类去向的关单谓词/六资产逐项需求边界与重开条件/已知误用风险；`docs/development/testing.md:18` 已由「单测与 lint 由 ci.yml 跑」订正为「单测由 ci.yml 跑（只有 pytest 步骤，没有 lint 步骤）」，未新增任何 lint 流程。
- 交付校验：`verify_deliverables.py` 通过——本卡 4 份文档的相对链接全部可解析；TSV 147 行、每行 5 栏、`disposition` 与证据格无空缺；known-issues 里的 9 类计数与 TSV 实际逐项相等；负控（空证据格）被判不合格为 True。
- 关键决策与已否决方案：六资产写「本轮有意不恢复 + 重开条件」，不写「永久退役」也不写「已被取代」；不新增扫描工具/常驻状态/第二套门禁；不复制日志、retro、memory、egg-info、代理工具配置内容；不改 #81 状态、不关单、不回洗 M6 验收。
- 下一步唯一动作：Pi 主脑核对本卡证据后，在 #81 记录决定人与日期，再按 known-issues 文档里的关单谓词关单。