# #81 历史产物清账进度存档

- 当前阶段：阶段一「候选核对」完成。盘点表 `artifact-inventory.tsv` 已生成（147 个路径 / 449 条 ref+path 记录），来源全部取自真实 Git 对象，未使用工作区文件。
- 本段结论：基线 `e849c21748392ad848131e07ff17d32e4cc83a8b` 下 34 个路径已存在（16 个逐 blob 相同、18 个被基线更新版本取代），113 个基线不存在。每个路径都有 `source_records`（精确 ref@fullsha=blob 状态）、`current_consumer_evidence`、`disposition` 四栏，无空去向。
- 口径分离：顾问口径（排除本轮新建的 6 个 card ref）复现为 445 记录 / 143 路径 / 109 基线不存在，与顾问数字逐项一致；本表含本轮 6 个 ref 故为 449/147/113。原工单 tracked 产物口径（约 65 项 / 38 份审查）是另一口径，不与本表混用，来源见 known-issues 文档。
- 关键决策与已否决方案：不按「squash 后非祖先」判未交付；不按缺失数归零作关单条件；不整包合历史分支；不复制日志/retro/memory/egg-info 内容（只记来源与排除原因）；不判基线已有路径为未交付。
- 下一步唯一动作：阶段二把当前交付结论依赖的历史审查/否决证据写入 `artifact-history-appendix.md`，并对 `docs/development/testing.md` 的 CI 描述只做事实订正。