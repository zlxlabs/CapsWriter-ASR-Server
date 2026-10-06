# #81 B 档恢复索引：非在途历史审查结论（artifact-B-restored-index）

- 依据：`263d4770627f8577d4e4f5459e87a277599facec:docs/sessions/261006-issue-root-fixes/artifact-B-source-plan.md` 准备表；用户 2026-10-06 修订范围「按真实可核清单落地B、在途保留、公开门禁未确认」。
- 分母：准备表 38 条候选 + 公共门禁未定 4 条 = 42；本 PR 新增恢复 28；类型排除 6；在途有意留档 4（Windows×3 交 PR #82、m7-platform-prep×1）；公共门禁不明 4。
- 声明：原「38 份 verdict」的测量快照已缺失，本索引按可核来源恢复，**不是原 38 集合的认证**，不含任何整体 PASS 判定；恢复物是历史档案，非当前代码审查结论，历史 FAIL/p1-found/skipped/否决按原 blob 逐字保留、未改写为当前成功。
- 复算方法：`git rev-parse <sourceCommit>:docs/sessions/<path>` 应等于 blobSHA；`git cat-file blob <blobSHA>` 应与文件字节一致（本批 28/28 已过 `git hash-object`==blob 校验）。
- 来源修正：`E3-runner-review-F-verdict.md` 准备表 sourceCommit 第 9 位 hex 笔误 `dff79bb3…`，实际为 `dff79bbd36d6364bcb5fc39521df4505169dd349`（本地 ref 与 `git ls-remote origin` 双核一致），blob 不变。
- NO_PATH 证据保留：`c2-fixed-review2-verdict.md` 源 `38d286f1f73ef3d9c6bef1522f8f0c5df4e86db1`、`m6-postfatal-verdict.md` 源 `6d4665359d5b1c7599de1c0db15e278ac94d0fa5` 在对应 commit 无此路径（已实测），按准备表保留为冲突证据，不当 blob 使用。

| path（docs/sessions/ 下） | sourceCommit | blob | 状态 | 说明 |
|---|---|---|---|---|
| 261001-http-files/reviews/E1-owner-review-A-verdict.md | d52f8687cb2ed90114547674d84875244576126e | c92faa18dcbeef290087cd0e2f283b1bd6f76bb3 | 本PR新增 | p2-only；与 design.md PCM 契约段对应（准备表线索） |
| 261001-http-files/reviews/E1-owner-review-B-verdict.md | 5b180d9d6642e17de9222ed1158223ce02740d83 | 4b58b2bb1c45229173bfb1cc53e49490afd01802 | 本PR新增 | 原档案；不重判 |
| 261001-http-files/reviews/E2-params-installed-consumer-verdict.md | da9264df8c4540db915d82840127e8611f322918 | c59e6c5804cb526dff622b77e0970690a9555f5f | 本PR新增 | 反向复核 verdict |
| 261001-http-files/reviews/E2-params-prereq-review-verdict-safe.md | aceb570c590d819c5b0e696d13717908e8435396 | 7b4310c04540435adc68df23803531134105d8cd | 本PR新增 | clean；与下一行同 blob 双路径 |
| 261001-http-files/reviews/E2-params-prereq-review-verdict.md | a67752ac9c885ddbfd33ea5ddc9f4e0c0dd383d6 | 7b4310c04540435adc68df23803531134105d8cd | 本PR新增 | 同 blob 多来源，两条原路径都恢复 |
| 261001-http-files/reviews/E2-prereq-combination-verdict.md | 70c2ead63e0610abaaac7f753003934cc9cde6db | 6624b0c0d9beb05aaa841a140fe8790c1c844c96 | 本PR新增 | 含明确 review verdict（pass） |
| 261001-http-files/reviews/E2-prereq-review-verdict.md | 42a9b2e5c6cbde2de2b4877a28156cd99ee81c2f | 9573a43e444f83217508710133c66ad957a88189 | 本PR新增 | p2-only |
| 261001-http-files/reviews/E2-upload-review-A-verdict.md | 90bc06ccd442cb13c7a759e57b815c35d9d2118b | abdbb3208c274e692074e4e4b64a90c3ec52e454 | 本PR新增 | p1-found 原样保留 |
| 261001-http-files/reviews/E2-upload-review-B-verdict.md | f60ee8a70e5bfc52100573a39efbdb6783eb42f3 | 4748ede581694e0497c44e781997f219d88e21ac | 本PR新增 | p1-found 原样保留 |
| 261001-http-files/reviews/E2-upload-review-C-verdict.md | 560ca94c779a5476bb0edb08f406e5d2863ef025 | 4620d80965ab054c4c3a21ff1e173e368d2d380b | 本PR新增 | p2 |
| 261001-http-files/reviews/E2-upload-review-D-verdict.md | 10b89e20bbf6c11d9e37ae9beced6384828b6c96 | 35b3a76229e6c82b019ca38e950cbbc08956c2ec | 本PR新增 | p2-only |
| 261001-http-files/reviews/E2-upload-review-E-verdict.md | 9fe2c2dad05547adcb85721eb9d037938bc2b12d | 1fa22847193bdf502c09b89d0c6dc03d2f198677 | 本PR新增 | p1-found 原样保留 |
| 261001-http-files/reviews/E2-upload-review-F-verdict.md | 21fee6f23dd56b683991202d6c41b8f051e8d51c | 06afe9428fa086eca8f15a72179d011038b63412 | 本PR新增 | PASS WITH P2 BACKLOG（历史） |
| 261001-http-files/reviews/E3-runner-review-F-verdict.md | dff79bbd36d6364bcb5fc39521df4505169dd349 | c0a440f43bce5355803e72fa77c3fdb7a5649bb7 | 本PR新增 | 准备表 commit 笔误已修正（见上）；FAIL p1 原样 |
| 261001-http-files/reviews/E3-runner-review-G-verdict.md | d388e6be77d602af0f72e67d5e499a5b9768df37 | 3943f887dced0f8b34760b36de977a82700d6403 | 本PR新增 | clean |
| 261001-http-files/reviews/E3-runner-review-verdict.md | f454103b3fb98614625c08b3271ca503a28469e2 | 94a827b6bf6eb9f840d77b0214100ded1b075c6e | 本PR新增 | FAIL 原样保留，不改当前 |
| 261001-http-files/reviews/E5-sdk-review-A-verdict.md | b06887589a3e79d97ae2926b4a94b4779d479499 | 41930927dabc463d2ebfa18955d386f685b359d2 | 本PR新增 | p2-only |
| 261001-http-files/reviews/E5-sdk-review-B-verdict.md | af00f6f0aedccbf4eb50022a23141a9b4525f489 | 8f58fe51cb7df510e76c2b85140887551b22c6b7 | 本PR新增 | 终审 |
| 261003-http-completion/reviews/c2-fixed-review1-verdict.md | 72dec5260f4c7743d1d41729aa14d20099ca6b92 | ff8fb11228f399b845c5abbfc6ffad71f5147e65 | 本PR新增 | 同 blob 另源 1b8f61cf7462790f427ef0778435678ac42c1d95、d1b68bb6477df780b9e15bdb9bb694e7fb03b45b |
| 261003-http-completion/reviews/c2-fixed-review2-verdict.md | 6e7bf0816eb86e635dc3c501f6a54f1daa36cc5b | 7b1cd859ab2ae74c717e8aeeddea45aaaba7c5d4 | 本PR新增 | 同 blob 另源 5c4b3e7a90ac7f9db39eb76e6966d461730b18c2；NO_PATH 38d286f1 保留 |
| 261003-http-completion/reviews/m6-postfatal-verdict.md | c4bbdb38f04128e5d00c7dcff08b73696b686b67 | 10c51a69886de36097e21f9d42aaef11f8203193 | 本PR新增 | skipped 判定原样；NO_PATH 6d466535 保留 |
| 261003-http-completion/reviews/m6-repeat-matrix-increment-verdict.md | 1c566b54f88db8b047b42665118a32a681e969c5 | ab8f069e7a41d5606619a77dd02406e51eb29257 | 本PR新增 | 增量审查；非整体完成证明 |
| 261003-http-completion/reviews/m6-repeat-matrix-review1-verdict.md | 03e8e48dd89f1fda14a72a467f5b8dc0546db09e | 3c9ecb0a0f472a9e8817ba17af2aae260c03cffb | 本PR新增 | skipped 原样 |
| 261003-http-completion/reviews/pr64-second-canonical-verdict.md | b47fc0350c0a7d181a98646a32580a29828bb18d | 8c163d4e4c04e9d6041e405ab4c3305a61485ee4 | 本PR新增 | p2-only |
| 261004-sdk-time-contract/reviews/auto-budget-review1-verdict.md | 6d7f6f9593dc88c601c2a3fccd9e3eaf4bdc3a7c | ebbc4bf28f9b2567208cbb65014fee42effce02a | 本PR新增 | pass（历史） |
| 261004-sdk-time-contract/reviews/auto-budget-review2-verdict.md | 9f41b16b696b461ac78a2fcaad1657783aff6871 | 936f9e7a5bfd3a175b4812079a88de5daed2f764 | 本PR新增 | pass（历史） |
| 261004-sdk-time-contract/reviews/independent-review1-verdict.md | b74c7de53b75bd711f63eb840f8cb05aad8ae49b | 559d8874563ad9c54b0a60c0740aec1022f4636d | 本PR新增 | 独立审查 verdict |
| 261004-sdk-time-contract/reviews/independent-review2-verdict.md | 70d05e5883933390818f9e672fe6850e48210cb7 | 34ddef3ed68ed257a222865f9fe97eb9271a3c37 | 本PR新增 | clean |
| 261001-http-files/reviews/E1-combination-verification.md | 8c9c0acd698e39df6e11a278563b2eb021a74b5e | a3175760cbe37355ca4f3cee8142668f66fcfd92 | 类型排除 | 自述「只记录组合树消费侧验证证据」，非独立 verdict；原文对象未删改 |
| 261001-http-files/reviews/E2-final-accept-precheck-H5.md | e2f75a80602c5e1ccd2038a93fe6f3d0d3d5f298 | 265541b323c75c4399b3d93260c0d02175aabe78 | 类型排除 | 官方 accept_precheck 记录 |
| 261001-http-files/reviews/E2-final-accept-precheck.md | 36043f9942c8301f87b4d989c40d73797cc41229 | 5de5ab0c1fd38f6fb34a062008afb7557abd08a0 | 类型排除 | 自述「不代表独立主审」 |
| 261001-http-files/reviews/E2-gate-findings-evidence.md | f8a7decc3bc5c1d2f8433ecbe330f0b3411f3c17 | 2e793af8a7c505bf7c627ba64e13c3c41af66ab9 | 类型排除 | finding 证据与分诊，自述「只记录证据」 |
| 261001-http-files/reviews/E2-prereq-accept-precheck.md | cbf0be38fa76ca877f3606c697a45c870e4eff05 | ad4405ae99904a73472ee3a1a5cc167264e2e238 | 类型排除 | 预检元数据生成记录 |
| 261001-http-files/reviews/E3-runner-implementation-record.md | 0b416fe64f756ab024ec960f2d5e9a8998d9a6aa | fce8cbcc45ba0ff5d51a7ab6d2669b68f737fb72 | 类型排除 | 实现记录（派发卡点名），非 verdict |
| 261003-http-completion/reviews/windows-http-integrity-native-verdict.md | 6256bad127001690fa415d717aae6371ee466194（4源同blob） | 35b799bfaa66506c5f85a56c6c5fd33d37adcf85 | 有意留档 | 在途 #82，交 PR82；本卡不恢复，原文对象未删改 |
| 261003-http-completion/reviews/windows-http-integrity-posix-verdict.md | 6256bad127001690fa415d717aae6371ee466194（4源同blob） | 9f32e61b446dfe231904f416fa5842cc45c719e1 | 有意留档 | 同上 |
| 261003-http-completion/reviews/windows-http-integrity-review1-verdict.md | 6256bad127001690fa415d717aae6371ee466194（4源同blob） | 7ed85387c4b9b7b43a8b449d7631437dc135e5c9 | 有意留档 | 同上 |
| 261003-http-completion/reviews/m7-platform-prep-verdict.md | 8c132f13627cb413a4d214b9a44f5a632ab9db61、887014512f2e1ab7c455c450efd9c06586c8bba9（同blob） | 268082cfd1cf2e011ff5aefb335f047de18af1c7 | 有意留档 | M7 在途重叠，用户修订范围明确不恢复；另 NO_PATH 41939845ae221370b19cab8fa523969a365f4702 |
| 20260926-public-gate/reviews/fork-backup-refresh-verdict.md | — | — | 不明 | 准备表未给 sourceCommit/blob；用户定「公开未确认」，本卡不恢复 |
| 20260926-public-gate/reviews/onboarding-verdict.md | — | — | 不明 | 同上 |
| 20260926-public-gate/progress/onboarding-progress.md | — | — | 不明 | progress 本非 verdict；同上 |
| 20260926-public-gate/progress/quality-entry-progress.md | — | — | 不明 | 同上 |

- 现master已在：0 —— 恢复前对基线 `03ec517731135656929b8a019090f7918bc02d66`（与派发时 `git ls-remote origin` 实测远端 master 一致，无人新落）逐路径核验，无同路径对象，无覆盖。
- byte 校验：28/28 `git hash-object`==blobSHA；恢复总量 1776 行 / 238,801 B（原文，非新模板），在 2400/3500 预算内。
- publicscan：api key/secret/passwd/webhook/bearer/ghp/xox/外域 email 模式 0 命中。
- 行尾空白：全量仅 1 行（`E2-params-installed-consumer-verdict.md:73` 行尾双空格，历史原文自带、逐字保留）；`git diff --check` 共报这 1 行，非本卡新增错误。（更正：预检时用本机 `grep -E '[ \t]+$'` 得到的「8 行」是把 `\t` 当字面量 t 的方言误报，已用 od 与 `git diff --check` 双重核伪。）
