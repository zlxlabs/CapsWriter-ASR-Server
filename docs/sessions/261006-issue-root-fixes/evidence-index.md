# 审查与运行时证据索引 (261006-issue-root-fixes)

本索引记录 Issue #76、#85、#87 修复批次的独立审查与运行时验证证据出处。历史结论逐字保留，不重定 P 等级，不代表当前生产环境或最新主干审查状态。

## 证据清单

| 文档路径 | sourceCommit | blobSHA | 适用审查范围 | 模式 | OCR三态 | 限制与历史说明 | 后续已合修复 |
|---|---|---|---|---|---|---|---|
| [reviews/decode-review1-verdict.md](reviews/decode-review1-verdict.md) | `8e736671d2` | `561297b64c` | `e849c21748..d196db1277` | 仅源码审 | status=reviewed / complete / minimax | 源码审非亲测，无新 finding | PR #89 (92bf36c) |
| [reviews/decode-review2-verdict.md](reviews/decode-review2-verdict.md) | `6ada7edcb5` | `ccbd54ccf0` | `e849c21748..d196db1277` | 运行时反向+源码 | status=reviewed_fallback / complete / deepseek | minimax超时，fallback覆盖非primary成功 | PR #89 (92bf36c) |
| [progress/decode-runtime-evidence.md](progress/decode-runtime-evidence.md) | `a5a526f4ee` | `e2b3173bbc` | `d196db1277` | 本地实跑 | N/A (runtime取证) | 真ffmpeg+真实WS+fake ASR worker，非生产 | PR #89 (92bf36c) |
| [reviews/sdk-review2-verdict.md](reviews/sdk-review2-verdict.md) | `19f489d9fa` | `caf5c3cb8b` | `e849c21748..5c05a0c402` | 源码+探针 | status=reviewed / complete / minimax | 归属 dispatch b3816e (勿与84295d交换) | PR #90 (dccca73) |
| [reviews/sdk-contract-review-verdict.md](reviews/sdk-contract-review-verdict.md) | `50aa3f4f95` | `0c5fac811d` | `e849c21748..137032657a` | 受控探针+源码 | status=reviewed / complete / minimax | Task43 p1-found针对旧137非cdee;受控永等非自然;保历史不重评 | PR #90 (dccca73) |
| [reviews/pr90-incremental-final-verdict.md](reviews/pr90-incremental-final-verdict.md) | `2ba644d8af` | `df9c4df184`* | `137032657a..cdee617f66` | 源码+窄测 | status=reviewed / complete / minimax | *唯一格式归一：原“- failure-visibility: clean”纠为顶格整行 | PR #90 (dccca73) |
| [reviews/harness-review2-verdict.md](reviews/harness-review2-verdict.md) | `3d59382c14` | `b6cfb02090` | `e849c21748..e2755ed8a8` | 本地窄测+源码 | status=reviewed_fallback / complete / deepseek | 归属84295d;旧隔离任务failed/seal冲突保历史，不冒独立合格 | PR #91 (3ebcb72) |
| [reviews/harness-review1-verdict.md](reviews/harness-review1-verdict.md) | `f357fc986f` | `9f757303cc` | `e849c21748..482cf9ae72` | 源码+窄测 | status=reviewed / complete / minimax | 历史代码PR已含入仓，本索引仅引用不二次copy | PR #91 (3ebcb72) |
| [reviews/sdk-review1-verdict.md](reviews/sdk-review1-verdict.md) | `34a4ed9ff4` | `3068b668bb` | `e849c21748..050b6dc5f4` | 源码+探针 | status=reviewed_fallback / complete / deepseek | 历史代码PR已含入仓，本索引仅引用不二次copy | PR #90 (dccca73) |

## 约束与失效说明

1. **历史局限**：Task43 之 `p1-found` 针对旧提交 `1370326`，后续 5 行 gather 取消修复已合入 PR #90（终态为 `cdee617`），历史定级不重定。
2. **环境保真**：`decode-runtime-evidence.md` 使用真实 ffmpeg 与真实 WS 配合 fake ASR worker，仅作机制闭环验证，不代表生产 ASR 推理表现。
3. **OCR 状态**：`decode-review2` 与 `harness-review2` 均为 minimax leg_timeout 后的 deepseek fallback 完成，非 primary 成功。
4. **格式差异**：`pr90-incremental-final-verdict.md` 仅规范化 `failure-visibility` 顶格格式，原 blob 为 `df9c4df184dac7e680ed082f82fd1799f14b05bc`。
