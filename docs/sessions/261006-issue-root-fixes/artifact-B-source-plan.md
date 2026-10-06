# #81 B 档实际来源对齐准备

## 结论与边界

这不是 B 档落地，也不是 #81 关单。用户于 2026-10-06 在
[#81 comment 6013575120](https://github.com/zlxlabs/CapsWriter-ASR-Server/issues/81#issuecomment-6013575120)
选择「只补原登记的 38 份 verdict」，但要求先由 HTTP/M7 线确认来源归属。

原测量基线 `origin/master` 的完整 SHA 是
`902400887445603a58f7dc960a24e809ca779a0a`；通过 `git ls-remote
https://github.com/zlxlabs/CapsWriter-ASR-Server.git refs/heads/master` 核得当前
远端 master 为 `dccca739131ac95e54f75bf5611508aa7ff3c20a`。本树未 fetch、未改
base；两套对象的待补路径均按真实树查验，不用宽表回填当前状态。

原 38 的原始测量快照不在当前可读对象中，现有 `artifact-inventory.tsv` 是
147 paths / 449 source records 的宽表，不能单独证明「哪 38」及其作者归属。下表是
从宽表按 `MISSING_AT_BASE` 且位于 `261001-http-files`、`261003-http-completion`
或 `261004-sdk-time-contract` 的 reviews 目录机械得到的 **38 条候选路径**；数字
相同不等于已认证为原 38。公共门禁目录的 4 条 reviews/progress 仍列在未定项，
不擅自塞入下表。

## 逐路径候选表

表内 `sourceCommit/blobSHA` 均由真实 commit:path 解析；同一路径的同 blob 来源合并
展示，`NO_PATH` 来源单独保留，不能把它当成另一个 blob。`基线/当前` 分别是
`9024008` 与远端 master `dccca73` 的全路径结果；`缺失`不是对象不可读。

| path | sourceCommit/blobSHA（完整） | 基线/当前 | 归属 | 在途 | 恢复风险 |
|---|---|---|---|---|---|
| `261001-http-files/reviews/E1-combination-verification.md` | `8c9c0acd698e39df6e11a278563b2eb021a74b5e/a3175760cbe37355ca4f3cee8142668f66fcfd92` | 缺失/缺失 | HTTP | 否 | 原档案；HTTP 确认后才可恢复 |
| `261001-http-files/reviews/E1-owner-review-A-verdict.md` | `d52f8687cb2ed90114547674d84875244576126e/c92faa18dcbeef290087cd0e2f283b1bd6f76bb3` | 缺失/缺失 | HTTP | 否 | 当前 design 依赖；保留历史否决与适用 SHA/日期 |
| `261001-http-files/reviews/E1-owner-review-B-verdict.md` | `5b180d9d6642e17de9222ed1158223ce02740d83/4b58b2bb1c45229173bfb1cc53e49490afd01802` | 缺失/缺失 | HTTP | 否 | 原档案；不得重判 |
| `261001-http-files/reviews/E2-final-accept-precheck-H5.md` | `e2f75a80602c5e1ccd2038a93fe6f3d0d3d5f298/265541b323c75c4399b3d93260c0d02175aabe78` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-final-accept-precheck.md` | `36043f9942c8301f87b4d989c40d73797cc41229/5de5ab0c1fd38f6fb34a062008afb7557abd08a0` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-gate-findings-evidence.md` | `f8a7decc3bc5c1d2f8433ecbe330f0b3411f3c17/2e793af8a7c505bf7c627ba64e13c3c41af66ab9` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-params-installed-consumer-verdict.md` | `da9264df8c4540db915d82840127e8611f322918/c59e6c5804cb526dff622b77e0970690a9555f5f` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-params-prereq-review-verdict-safe.md` | `aceb570c590d819c5b0e696d13717908e8435396/7b4310c04540435adc68df23803531134105d8cd` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-params-prereq-review-verdict.md` | `a67752ac9c885ddbfd33ea5ddc9f4e0c0dd383d6/7b4310c04540435adc68df23803531134105d8cd` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-prereq-accept-precheck.md` | `cbf0be38fa76ca877f3606c697a45c870e4eff05/ad4405ae99904a73472ee3a1a5cc167264e2e238` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-prereq-combination-verdict.md` | `70c2ead63e0610abaaac7f753003934cc9cde6db/6624b0c0d9beb05aaa841a140fe8790c1c844c96` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-prereq-review-verdict.md` | `42a9b2e5c6cbde2de2b4877a28156cd99ee81c2f/9573a43e444f83217508710133c66ad957a88189` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-upload-review-A-verdict.md` | `90bc06ccd442cb13c7a759e57b815c35d9d2118b/abdbb3208c274e692074e4e4b64a90c3ec52e454` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-upload-review-B-verdict.md` | `f60ee8a70e5bfc52100573a39efbdb6783eb42f3/4748ede581694e0497c44e781997f219d88e21ac` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-upload-review-C-verdict.md` | `560ca94c779a5476bb0edb08f406e5d2863ef025/4620d80965ab054c4c3a21ff1e173e368d2d380b` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-upload-review-D-verdict.md` | `10b89e20bbf6c11d9e37ae9beced6384828b6c96/35b3a76229e6c82b019ca38e950cbbc08956c2ec` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-upload-review-E-verdict.md` | `9fe2c2dad05547adcb85721eb9d037938bc2b12d/1fa22847193bdf502c09b89d0c6dc03d2f198677` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E2-upload-review-F-verdict.md` | `21fee6f23dd56b683991202d6c41b8f051e8d51c/06afe9428fa086eca8f15a72179d011038b63412` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E3-runner-implementation-record.md` | `0b416fe64f756ab024ec960f2d5e9a8998d9a6aa/fce8cbcc45ba0ff5d51a7ab6d2669b68f737fb72` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E3-runner-review-F-verdict.md` | `dff79bb36d6364bcb5fc39521df4505169dd349/c0a440f43bce5355803e72fa77c3fdb7a5649bb7` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E3-runner-review-G-verdict.md` | `d388e6be77d602af0f72e67d5e499a5b9768df37/3943f887dced0f8b34760b36de977a82700d6403` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E3-runner-review-verdict.md` | `f454103b3fb98614625c08b3271ca503a28469e2/94a827b6bf6eb9f840d77b0214100ded1b075c6e` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E5-sdk-review-A-verdict.md` | `b06887589a3e79d97ae2926b4a94b4779d479499/41930927dabc463d2ebfa18955d386f685b359d2` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261001-http-files/reviews/E5-sdk-review-B-verdict.md` | `af00f6f0aedccbf4eb50022a23141a9b4525f489/8f58fe51cb7df510e76c2b85140887551b22c6b7` | 缺失/缺失 | HTTP | 否 | 原档案；确认旧适用范围 |
| `261003-http-completion/reviews/c2-fixed-review1-verdict.md` | `72dec5260f4c7743d1d41729aa14d20099ca6b92/ff8fb11228f399b845c5abbfc6ffad71f5147e65`; `1b8f61cf7462790f427ef0778435678ac42c1d95/ff8fb11228f399b845c5abbfc6ffad71f5147e65`; `d1b68bb6477df780b9e15bdb9bb694e7fb03b45b/ff8fb11228f399b845c5abbfc6ffad71f5147e65` | 缺失/缺失 | HTTP | 否 | 同 blob 多来源；HTTP 确认后再恢复 |
| `261003-http-completion/reviews/c2-fixed-review2-verdict.md` | `6e7bf0816eb86e635dc3c501f6a54f1daa36cc5b/7b1cd859ab2ae74c717e8aeeddea45aaaba7c5d4`; `5c4b3e7a90ac7f9db39eb76e6966d461730b18c2/7b1cd859ab2ae74c717e8aeeddea45aaaba7c5d4`; `38d286f1f73ef3d9c6bef1522f8f0c5df4e86db1/NO_PATH` | 缺失/缺失 | HTTP | 否 | 保留 NO_PATH；不把路径缺失当 blob 冲突 |
| `261003-http-completion/reviews/m6-postfatal-verdict.md` | `c4bbdb38f04128e5d00c7dcff08b73696b686b67/10c51a69886de36097e21f9d42aaef11f8203193`; `6d4665359d5b1c7599de1c0db15e278ac94d0fa5/NO_PATH` | 缺失/缺失 | HTTP | 否 | 保留 NO_PATH；旧否决不可重判 |
| `261003-http-completion/reviews/m6-repeat-matrix-increment-verdict.md` | `1c566b54f88db8b047b42665118a32a681e969c5/ab8f069e7a41d5606619a77dd02406e51eb29257` | 缺失/缺失 | HTTP | 否 | 过程审查；先确认仍有消费者 |
| `261003-http-completion/reviews/m6-repeat-matrix-review1-verdict.md` | `03e8e48dd89f1fda14a72a467f5b8dc0546db09e/3c9ecb0a0f472a9e8817ba17af2aae260c03cffb` | 缺失/缺失 | HTTP | 否 | 过程审查；先确认仍有消费者 |
| `261003-http-completion/reviews/m7-platform-prep-verdict.md` | `8c132f13627cb413a4d214b9a44f5a632ab9db61/268082cfd1cf2e011ff5aefb335f047de18af1c7`; `887014512f2e1ab7c455c450efd9c06586c8bba9/268082cfd1cf2e011ff5aefb335f047de18af1c7`; `41939845ae221370b19cab8fa523969a365f4702/NO_PATH` | 缺失/缺失 | M7 | 待 M7 确认 | 不以在途 H1 证据替代旧 verdict |
| `261003-http-completion/reviews/pr64-second-canonical-verdict.md` | `b47fc0350c0a7d181a98646a32580a29828bb18d/8c163d4e4c04e9d6041e405ab4c3305a61485ee4` | 缺失/缺失 | HTTP | 否 | 先确认 PR64 归属与适用范围 |
| `261003-http-completion/reviews/windows-http-integrity-native-verdict.md` | `6256bad127001690fa415d717aae6371ee466194/35b799bfaa66506c5f85a56c6c5fd33d37adcf85`; `6f978349a26ab081745f174a56fa2c01ef08a277/35b799bfaa66506c5f85a56c6c5fd33d37adcf85`; `2a6b76443f3abe95b9376b3ba9aa38b33688b1d4/35b799bfaa66506c5f85a56c6c5fd33d37adcf85`; `fce9131a256a7a8e26a48a0c0882b81444f9ee59/35b799bfaa66506c5f85a56c6c5fd33d37adcf85` | 缺失/缺失 | HTTP（Windows） | 是，#82 | 冻结；交给 PR82，不由本卡恢复 |
| `261003-http-completion/reviews/windows-http-integrity-posix-verdict.md` | `6256bad127001690fa415d717aae6371ee466194/9f32e61b446dfe231904f416fa5842cc45c719e1`; `6f978349a26ab081745f174a56fa2c01ef08a277/9f32e61b446dfe231904f416fa5842cc45c719e1`; `1776101eaab0b57daedc0457fc0deb4bda0a33f3/9f32e61b446dfe231904f416fa5842cc45c719e1`; `fce9131a256a7a8e26a48a0c0882b81444f9ee59/9f32e61b446dfe231904f416fa5842cc45c719e1` | 缺失/缺失 | HTTP（Windows） | 是，#82 | 冻结；交给 PR82，不由本卡恢复 |
| `261003-http-completion/reviews/windows-http-integrity-review1-verdict.md` | `6256bad127001690fa415d717aae6371ee466194/7ed85387c4b9b7b43a8b449d7631437dc135e5c9`; `6f978349a26ab081745f174a56fa2c01ef08a277/7ed85387c4b9b7b43a8b449d7631437dc135e5c9`; `fce9131a256a7a8e26a48a0c0882b81444f9ee59/7ed85387c4b9b7b43a8b449d7631437dc135e5c9`; `6cb69885606a4012d9ea0c6a54c3ec7fba963c5b/7ed85387c4b9b7b43a8b449d7631437dc135e5c9` | 缺失/缺失 | HTTP（Windows） | 是，#82 | 冻结；交给 PR82，不由本卡恢复 |
| `261004-sdk-time-contract/reviews/auto-budget-review1-verdict.md` | `6d7f6f9593dc88c601c2a3fccd9e3eaf4bdc3a7c/ebbc4bf28f9b2567208cbb65014fee42effce02a` | 缺失/缺失 | 其他（SDK） | 否 | SDK owner 确认后再恢复 |
| `261004-sdk-time-contract/reviews/auto-budget-review2-verdict.md` | `9f41b16b696b461ac78a2fcaad1657783aff6871/936f9e7a5bfd3a175b4812079a88de5daed2f764` | 缺失/缺失 | 其他（SDK） | 否 | SDK owner 确认后再恢复 |
| `261004-sdk-time-contract/reviews/independent-review1-verdict.md` | `b74c7de53b75bd711f63eb840f8cb05aad8ae49b/559d8874563ad9c54b0a60c0740aec1022f4636d` | 缺失/缺失 | 其他（SDK） | 否 | SDK owner 确认后再恢复 |
| `261004-sdk-time-contract/reviews/independent-review2-verdict.md` | `70d05e5883933390818f9e672fe6850e48210cb7/34ddef3ed68ed257a222865f9fe97eb9271a3c37` | 缺失/缺失 | 其他（SDK） | 否 | SDK owner 确认后再恢复 |

## 已确认与未定

- **对象可恢复事实：** 38 条候选路径对应 54 条来源记录、48 个来源 commit；
  48 个 commit 对象均存在，51 条 `commit:path` 可解析为真实 blob，另 3 条明确是
  `NO_PATH`，没有把「对象不存在」混写成「路径不存在」。
- **已确认适用线索：** `E1-owner-review-A-verdict.md` 被历史附录指向基线
  `docs/sessions/261001-http-files/design.md:24,26` 的现存量化结论；这里只保留指针，
  不复制、不改写原 verdict。其余候选只确认了对象和旧盘点状态，尚未确认当前消费者。
- **待确认：** 原 38 的成员身份仍缺原测量快照；HTTP owner 需确认 24 条
  `261001` 及表中非 Windows 的 HTTP 行，M7 owner 需确认 `m7-platform-prep-verdict`
  的两个同 blob 来源，SDK owner 需确认 4 条 SDK verdict。所有确认都要连同
  sourceCommit/blobSHA、历史适用 SHA/日期及原否决或 failed 文本一起确认。
- **明确不在本卡恢复：** PR #82 在途的三条 Windows verdict（表中三行）交给
  `card/http-windows-integrity-pr-delivery-261005`；当前 M7 在途文件
  `docs/sessions/261006-m7-finalization/h1-native-positive-evidence.md` 不是旧
  verdict，不能互相替代。其余 35 条不属于 PR82 文件范围，但仍需对应 owner 对齐。
- **未定的公共门禁四条：** `20260926-public-gate` 下的
  `reviews/fork-backup-refresh-verdict.md`、`reviews/onboarding-verdict.md`、
  `progress/onboarding-progress.md`、`progress/quality-entry-progress.md`。它们来自
  原 65 路径分布，但当前宽表不足以证明它们是否属于原 38；本卡不恢复。

## 下一落地卡的硬约束

1. 只对 owner 明确确认的 path/blob 做逐 blob 原文恢复；不能按最后提交、最长来源或
   当前文件名择一。`NO_PATH` 记录继续作为冲突证据保留。
2. 恢复时保留原 verdict 的否决/failed 结论、适用 SHA 和日期；不把历史失败改写成
   当前 PASS，也不因当前 master 仍缺失就补造结论。
3. 先用真实远端 master SHA 重跑全路径 `git cat-file -e`，再提交必要文档；本准备卡
   不操作 PR82、Windows、部署资产、来源认证器或其他 worktree。
