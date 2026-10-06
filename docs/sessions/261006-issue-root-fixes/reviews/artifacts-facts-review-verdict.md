# #81 局部来源与摘录检查 verdict

failure-visibility: p2-only

## 冻结范围

- 全量：`e849c21748392ad848131e07ff17d32e4cc83a8b..d3ec402bba7584a2bc51ca7b39d21403b2162620`；增量：`88aaa697ea6893b7315932be22813b159f601f30..d3ec402bba7584a2bc51ca7b39d21403b2162620`。
- 增量四问：①范围为已知说明、当前阶段进度、R3 原档案；`artifact-inventory.tsv` 与 `artifact-history-appendix.md` 不在增量。R3 路径 blob `f7acdc786ba716593b4064855a564a78b5c6091c` 与来源提交 `ee8b24e6605a34c836e78b59e44085be344469e2` 同 blob。②只用标准库 `Counter` 记输入状态/标签，无新 helper 或依赖。③计数只描述输入；状态差异计数不参与退出判定，`fail` 仍控制退出码。④整体 `RESULT` 与认证语句已移除；当前说明保留局部错误和非零退出，历史运行记录注明非认证。
- 全量范围包括 known-issues、testing 订正、TSV、appendix、progress 与历史 verdict。只机械核历史档案 blob/链接；不以其正文作业务证据。inventory 147 路径、449 source、10 标签；附录 5/5 连续原文与指定 Git 源匹配。

## Finding

### P2 — `rev-parse` 查询错误被归为对象不可用

- 违反 I2：区分查询错误、无路径和对象不可用。代码路径：[known-issues checker](../../../development/known-issues/artifact-disposition-261006.md:112) 中 `rev-parse` 任意非零都返回 `OBJECT_UNAVAILABLE`（116）；该 `tree()` 供 `observed()` 查询 TSV 每条 source。
- 实测：给真实 checker 设置格式错误的 `GIT_CONFIG_GLOBAL` 后，Git 的 `rev-parse` 对有效 commit 返回 128 并报配置解析错误；checker 消费 `.agents/skills` 的 source 行时仍输出 `observed=OBJECT_UNAVAILABLE`，总退出 1。错误可见，但原因状态错误；正常对象库下 449 条状态均一致。
- internal 两问：实际审查中会在 Git 查询上下文/对象数据库出错时触发（本次故障注入可复现）；后果仍 fail-loud、不会误报零或通过，但会把查询故障指向缺失历史对象，故属 P2 诊断误分类，不是 P1 静默放行。

## 实核与边界

- 从冻结 Git blob 抽取 7,540-byte checker，SHA-256 `b3e7d5eba3c51cf71c4c7a71a4269ec7a5932d32069858523b59e47b57d5a341`，于 d3ec402 临时 worktree 的实际输入文件运行。
- 正常：147 path / 449 source，已核 449、不可核 0、状态差异 0；标签计数 10 类合 147。独立 Git 对象复算为 34 `EXISTS_AT_BASE` / 113 `MISSING_AT_BASE`，来源 22 same / 28 diff / 360 base-missing / 39 NO_PATH，差异 0。
- 删一条路径：146 / 448，退出 0；改一标签为 `invented-category`：标签计数如实显示 1，退出 0；两者无整体认证。缺失 SHA 给具体 `UNAVAILABLE`/`ERROR` 并退出 1；EV-A1 两行换序报非连续原文并退出 1。
- 已知链接断链 0。抽样对象：EV-A1/A2 对应 E1 verdict 源路径 `docs/sessions/261001-http-files/reviews/E1-owner-review-A-verdict.md`，Git blob `c92faa18dcbeef290087cd0e2f283b1bd6f76bb3`；仅凭样本不认证完整消费者关系。另两组摘录源 blob：`docs/sessions/261003-http-completion/m6-final-evidence-audit.md` `a8b5560c5765d217795a2e309fbfe31a428d3f37`；`docs/sessions/260930-http-file/reviews/eng-outside-verdict.md` `72aac8c180967895ff3eea6212f49ffa26afe6e1`。
- `testing.md` 订正与 CI 源码相符：CI 有 pytest 步骤，无 lint 步骤。六项旧资产及其他业务去向只按输入抽样，不签整体分类或消费者完整性；#82 不作处置。
- OCR 实际命令：`ocr-review --repo "$(git rev-parse --show-toplevel)" --from e849c21748392ad848131e07ff17d32e4cc83a8b --to d3ec402bba7584a2bc51ca7b39d21403b2162620 --audience agent --concurrency 4 --background-file /tmp/caps-artifacts-facts-review-dlg-20261006-074247-0fec0b/spec-summary.md`；envelope `skipped / no_reviewable_items / coverage=none`，不算 OCR 已审。
- 隔离限制：一次宽范围 diff 的工具输出意外显示了历史 verdict 正文及早期 progress 内容；未引用或用于本 verdict 的 finding/验证，但本会话输入隔离不完整。OCR envelope 为 skipped，没有审查覆盖。未运行全量 CI/应用测试；只执行卡定验证。
