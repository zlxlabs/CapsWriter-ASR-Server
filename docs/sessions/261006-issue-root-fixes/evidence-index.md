# 审查与运行时证据索引 (261006-issue-root-fixes)

本索引记录 Issue #76、#85、#87 修复批次的独立审查与运行时验证证据出处。历史结论逐字保留，不重定 P 等级，不代表当前生产环境或最新主干审查状态。

## 证据清单

| 文档路径 | sourceCommit | blobSHA | 适用审查范围 | 模式 | OCR三态 | 限制与历史说明 | 后续已合修复 |
|---|---|---|---|---|---|---|---|
| [reviews/decode-review1-verdict.md](reviews/decode-review1-verdict.md) | `8e736671d2f7979a40212db6e75771e8285610bb` | `561297b64cb10a943421fdbe7fbbf0068c683557` | `e849c21748..d196db1277` | 仅源码审 | status=reviewed / complete / minimax | 源码审非亲测，无新 finding | PR #89 (92bf36c) |
| [reviews/decode-review2-verdict.md](reviews/decode-review2-verdict.md) | `6ada7edcb5b51740b25187db81b245f2f0dbcf55` | `ccbd54ccf08390efea113d45594560d5e4be4584` | `e849c21748..d196db1277` | 运行时反向+源码 | status=reviewed_fallback / complete / deepseek | minimax超时，fallback覆盖非primary成功 | PR #89 (92bf36c) |
| [progress/decode-runtime-evidence.md](progress/decode-runtime-evidence.md) | `a5a526f4ee9ce5ba3fc1d33a6bc1acc0b738c56c` | `e2b3173bbc63adafd9cb0d2f6d408761ec4c7bfd` | `d196db1277` (运行) | 本地实跑 | N/A (runtime取证) | 真ffmpeg+真实WS+fake ASR worker，非生产 | PR #89 (92bf36c) |
| [reviews/sdk-review2-verdict.md](reviews/sdk-review2-verdict.md) | `19f489d9facbd8127fb942a5f613cead9cb2a327` | `caf5c3cb8b6f2d66962f2ce6d2082132ba0cbce1` | `e849c21748..5c05a0c402` | 源码+探针 | status=reviewed / complete / minimax | 归属 dispatch b3816e (勿与84295d交换) | PR #90 (dccca73) |
| [reviews/sdk-contract-review-verdict.md](reviews/sdk-contract-review-verdict.md) | `50aa3f4f957f38dfed907ba6acf9267eec9ed262` | `0c5fac811dfa75cd104da64f16dcaa111ac9be43` | `e849c21748..137032657a` | 受控探针+源码 | status=reviewed / complete / minimax | Task43 p1-found针对旧137非cdee;受控永等非自然;保历史不重评 | PR #90 (dccca73) |
| [reviews/pr90-incremental-final-verdict.md](reviews/pr90-incremental-final-verdict.md) | `2ba644d8afbfc3b2d52d25c5b60396cfd3067001` | `df9c4df184dac7e680ed082f82fd1799f14b05bc`* | `137032657a..cdee617f66` (四问) / 完整 `5c05a0c402..cdee617f66` (三文件含I1/I2) | 源码+窄测 | status=reviewed / complete / minimax | *唯一格式归一：原“- failure-visibility: clean”纠为顶格整行 | PR #90 (dccca73) |
| [reviews/harness-review2-verdict.md](reviews/harness-review2-verdict.md) | `3d59382c141c5e02ef3ce370baf90acdecb13b05` | `b6cfb02090d62f562cfed539009e6d6f83b63305` | `e849c21748..e2755ed8a8` | 本地窄测+源码 | status=reviewed_fallback / complete / deepseek | 归属84295d;旧隔离任务failed/seal冲突保历史，不冒独立合格 | PR #91 (3ebcb72) |
| [reviews/harness-review1-verdict.md](reviews/harness-review1-verdict.md) | `f357fc986f26c89523f287d6f333bca11bcb9327` | `9f757303ccbeabff95ef926a738ff1c403fddd9d` | `e849c21748..482cf9ae72` | 源码+窄测 | status=reviewed / complete / minimax | 历史代码PR已含入仓，本索引仅引用不二次copy | PR #91 (3ebcb72) |
| [reviews/sdk-review1-verdict.md](reviews/sdk-review1-verdict.md) | `34a4ed9ff49d56530c6a99d942f5fd3373693797` | `3068b668bbc2fc67fde87d7e143a84e38467c7e4` | `e849c21748..050b6dc5f4` | 源码+探针 | status=reviewed_fallback / complete / deepseek | 历史代码PR已含入仓，本索引仅引用不二次copy | PR #90 (dccca73) |

## 约束与失效说明

1. **历史局限**：Task43 之 `p1-found` 针对旧提交 `137032657a2ca9f5a3bf66194a5ddf24334e1956`，后续 5 行 gather 取消修复已合入 PR #90（终态为 `cdee617f66069a859fd7d60bce520fc594ab4a4d`），历史定级不重定。
2. **PR90 审查范围**：PR90 一次新增量审查覆盖 `137032657a..cdee617f66` 四问范围，完整增量覆盖 `5c05a0c402..cdee617f66` 三文件（含 I1/I2 约束范围）。
3. **环境保真**：`decode-runtime-evidence.md` 使用真实 ffmpeg 与真实 WS 配合 fake ASR worker，仅作机制闭环验证，不代表生产 ASR 推理表现。
4. **OCR 状态**：`decode-review2` 与 `harness-review2` 均为 minimax leg_timeout 后的 deepseek fallback 完成，非 primary 成功；`sdk-review1` 亦为 fallback/deepseek，`harness-review1` 为 reviewed/minimax。
5. **格式差异**：`pr90-incremental-final-verdict.md` 仅规范化 `failure-visibility` 顶格格式，原 blob 为 `df9c4df184dac7e680ed082f82fd1799f14b05bc`。
