# Fork 备份刷新验收记录

日期：2026-09-26。核对对象为刷新快照提交 `393f3f5c585dce4fa07538d9309871ee28c11388`，来源 ref 为 `origin/card/fork-backup-260926`。

## 独立只读复核

只读 reviewer `archive_refresh_review` 实查 r2 manifest：336 条路径无重复、无符号链接；实际 336 个对象大小及哈希匹配，mismatch=0，236 个 JSON 成功解析。30 个 PR 中 29 merged、1 open；详情的 head/state/merged time 与分页列表一致。PR 元数据分页 181 页、824 条，计数匹配。

远端快照记录与 `post-push.tsv` 精确相符：12 个 live heads、0 tags、30 个 pull heads。fixed quality ref `229710c33b3da89bc560f00eab0c63de607ee1f4` 与 PR #30 API、详情和 pull head 一致；summary 的 `393` 与备份 ref 一致。bundle 共 44 refs：42 heads/PR heads，另有 HEAD 与 PR #30 merge。reviewer 受只读限制，未做 fresh clone。

## 独立恢复探针

implementer `archive_restore_probe` 在 `/tmp/caps-fork-restore.RjDQCd/fresh.git` 实际执行 bare clone、fetch bundle `refs/*` 和 `git fsck --full`；fsck stdout/stderr 均空、退出 0。恢复后 12 heads、30 PR heads 的每个 tip 均与详情相符；`393` 可由 `cat-file` 读取且与 fork backup ref 一致。public quality ref 与 PR #30 记录均为 `229710`。

负向探针将错误的 master 期望 tip 改成 `393`，diff 退出 1，确认该反例能被检出。failure-visibility 检查为 clean。
failure-visibility: clean

## 边界与结论

变量/secret name 计数为 0；动态触发值脱敏路径未覆盖，不宣称有样本覆盖。GitHub PR 页面及身份元数据无法精确恢复；用户接受导出后解除 fork。网页解除/迁移尚未确认，不能记为完成。

本 verdict 仅确认冻结后验证过的制品快照；不声称本地新分支已备份，也不表示远端 fork 已解除或迁移。本文档只在本地分支提交，不 push、不建 PR；后续待 F 迁后纳入。

制品 SHA-256：r2 manifest `9f8de006d5ee2a8d3a9d446c1818b192bf0804f7ab5e0d51734b3ab55790ea1f`；bundle `e32ab44fc918738a22951b9d09ec1e6ded0ff830debe2d333140536aeb11bde0`。r1 仍为原 manifest `f4618d8716304a15e8415612634b76c5465e4ce222dcf09c8bd5352d7eab3818`、bundle `f0acd953786f3389a273dfd561ec9e0e199318be3d34bb978365b4462a66558f`。
