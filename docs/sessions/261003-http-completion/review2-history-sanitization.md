# Review2 公开历史隔离说明

本文件记录一次用户授权的受限公开 Git 历史隔离。只改写一条审查分支引用，不改默认主干。
旧 GitHub 对象缓存不能承诺消失：分支 tip 隔离不等于平台已经撤回历史 blob。

## 范围

- 源基线（新历史唯一父提交）：`337689689c9b2a314548b70667e447841bf070ad`
- 新 tip：本提交。完整 40 位 SHA 以 push 后该授权审查分支的远端值为准
- 迁入文件：`docs/sessions/261003-http-completion/reviews/m6-h1-full-review2-verdict.md`
- 该 verdict 与隔离前已公开的干净 blob 字节相同；结论与 `failure-visibility` 未改写
- 未改源代码、未改 M6 目标语义、未改其它审查报告

## 做了什么

1. 在非 Git 私有目录保存完整 bundle，并执行 `git bundle verify`，结果成功。
2. 在私有新建 bare 仓库 fetch 该 bundle，恢复演练成功。
3. 从源基线新建历史，只放入上述干净 verdict 与本说明；不合并、不 cherry-pick 旧审查提交链。

## 明确不承诺

- 不承诺旧 GitHub objects 已被 purge。
- 不清理 GitHub 缓存、不发通知、不开 Support 工单。
- 本操作不删除该审查分支，只改写其公开 tip。
- 本次清理不宣布 M6 完成。

## 验收布尔量

- 受限备份成功：是
- 真实恢复演练成功：是
- 新历史相对源基线无宿主绝对路径模式：是（提交前扫描）
