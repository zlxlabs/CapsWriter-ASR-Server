# PR88 历史清账冻结差异独立审查 Verdict

- 风险等级：internal
- 冻结审查范围：`e849c21748392ad848131e07ff17d32e4cc83a8b..ca370b88a778ad4aee39b1e06b48dea3af8c823b`
- 输入：仅固定 Git 对象、卡面 spec 和下列被审文件；未读取实现报告或推理。
- 被审文件：`docs/development/known-issues/artifact-disposition-261006.md`、`docs/development/testing.md`、`docs/sessions/261006-issue-root-fixes/artifact-history-appendix.md`、`artifact-inventory.tsv`、`progress/artifact-disposition-progress.md`。
- OCR：命令按卡面执行，stdout envelope 为 `status=skipped`、`reason=no_reviewable_items`、`coverage=none`、0 findings，attendance 写入成功；不计为已审。
- 审查结论：`changes-required`；4 项 P2、1 项 P3；无 P1。当前资料不足以作为 #81 可独立复核的完整清账依据。六项本轮不恢复的边界本身未被扩大。
- OCR 命令：`ocr-review --repo <worktree> --from e849c21748392ad848131e07ff17d32e4cc83a8b --to ca370b88a778ad4aee39b1e06b48dea3af8c823b --audience agent --concurrency 4 --background-file /tmp/capswriter-81-review1-dlg-20261006-031727-acb476/spec-summary.md`

failure-visibility: p2-only

## Findings

### P2-1：source_records 把基线缺失写成源对象缺失

**违反 spec**：每个 source ref + full SHA + path 的存在、缺失、错误须分别记录，不能以基线状态代替源对象状态。

**证据**：inventory 的六项不恢复行（TSV 第 4、6、132、135、142、148 行）都把 `refs/heads/card/public-quality-260926@44690dbb1def6ea8a5e679fea16388c6394f8f89` 对应的路径标为 `MISSING`。直接查询该 SHA 的 Git tree，这六个路径实际均为 blob：`scripts/gate-quality` `031664bd8e46…`、`tests/test_gate_quality.py` `6ddd61687354…`、`gate-shadow.yml` `e9c7ee7062a5…`、`devcontainer.json` `4394a67ece5f…`、`pyproject.toml` `e83caffa55d4…`、`uv.lock` `107dd3b6c4a1…`。完整 449 条来源记录中，391 条标为 `MISSING`，其中 360 条在其记录的 source SHA 下实际解析为 blob，31 条才是缺路径；8 条 `REF_NO_PATH` 均是有效 commit 下的缺路径。基线 147 条状态另行复算为 113 缺失、34 存在，和表中 `baseline_state` 一致。

**后果与风险**：inventory 的 source 状态不能回答对应来源对象是否含该文件；六项资产虽按授权可本轮不恢复，其来源证据却被写成缺失，后续核对者可能据此误判其可恢复性或历史内容。项目风险 P2：影响本次内部清账证据，不影响运行时。

### P2-2：同 blob 的历史路径被归为“基线已有更新版本”

**违反 spec**：同 blob 证明内容已在基线；不同 blob 必须先核差异，不能自动称为已被更新版本取代。

**证据**：`artifact-inventory.tsv:80` 的 `docs/sessions/261003-http-completion/progress/m4-plan-progress.md` 被归为 `superseded-in-baseline`，消费者说明也称基线已有更新版本。但其唯一含文件内容的来源 `7ab3551818f0e93549c18f4bd0c7da7b44d52b33` 标为 `EXISTS_SAME_BLOB`，独立对象比较确认它与基线 blob `eae8afb6d4b0…` 相同；另一个来源 `ff0f2ddd…` 为 `REF_NO_PATH`，没有不同 blob 可支持“更新版本”分类。

**后果与风险**：至少一条分类与其源 blob 证据矛盾，文档列出的 16/18 内容分类及按 disposition 清账不能直接采信。项目风险 P2：历史去向分类错误，无运行时影响。

### P2-3：关键复核脚本只存在于本机临时路径

**违反 spec**：可复跑命令须随仓或提供自包含入口；本机 `/tmp` 脚本不算克隆者已有的正式验证入口。

**证据**：附录 `artifact-history-appendix.md:115-117` 将摘录校验交给 `/tmp/capswriter-261006-artifact-dlg-20261006-025712-1985d5/verify_sources.py`；进度 `artifact-disposition-progress.md:21` 声称 `verify_deliverables.py` 通过，但仓库固定 H0 中没有这两个脚本。附录五段摘录我用源 ref/full SHA 独立复核，均逐字匹配；对每段首字符做变异后均不再匹配，说明摘录当前可在本机对象库中核实，但此判据没有随仓交付。

**后果与风险**：其他克隆者不能复跑 source 检查、TSV 计数与链接负控，不能把进度中的脚本通过记录当作可重复验证。项目风险 P2：证据可重复性不足，不影响运行时。

### P2-4：固定实现 diff 超过卡面硬预算

**违反 spec**：`Diff-Lines-Hard=350`。

**证据**：冻结 diff 的 `git diff --numstat` 合计为 391 行新增、1 行删除，即 392 个变更行，超过硬预算 42 行（新增行数本身也超过 41 行）。

**后果与风险**：实现 diff 没有遵守本卡的硬范围预算。项目风险 P2：交付约束违规；不推断为代码运行故障。

### P3-1：disposition 类别数前后不一致

**违反 spec**：分类行数须与文档数字、枚举一致。

**证据**：known-issues 文档 `:52-61` 列出 10 种 disposition；其 `:100` 与 progress `:20-21` 都称“9 类”。TSV 独立解析得到 10 类、147 行。

**后果与风险**：关单谓词的类别总数与逐项表不一致，可能漏核一类。项目风险 P3：文档计数错误。

## 已核对且通过的部分

- 80,793 字节 TSV 完整读取并解析：147 条唯一路径、449 条 source 记录、5 栏均非空；类别实际计数为 16/18/77/2/1/18/1/6/4/4，合计 147。
- 对 e849 基线逐路径复算，`baseline_state` 的 113 缺失与 34 存在均正确；不存在 rev（`rc=128`）与有效 rev 下不存在 path 的 `missing` 状态由独立负控区分。另以同一文件的不同 blob 验证不同 SHA 不会被误认为相同内容。
- `docs/development/testing.md` 的 CI 描述与 e849 的真实 `.github/workflows/ci.yml` 一致：工作流含 pytest 步骤、无 lint 步骤；`gate.yml` 调用外部 Required Gate v2。六资产边界保留“不恢复”“不等于永久退役”与重开条件，shadow 与 Required Gate 明确不等价；#82 及其他在途项未被算作已完成。
- 附录的 5 段 source-check 均与其 Git 源对象逐字相符，首字符变异负控全部拒绝；这不替代随仓提供正式复核入口。
- 对 337 refs 的冻结扫描总数未能从提交中的冻结 ref 清单独立重建；当前 ref 数据不是 H0 时点快照，因此该总数记为未独立验证，不据此判定为错误。
