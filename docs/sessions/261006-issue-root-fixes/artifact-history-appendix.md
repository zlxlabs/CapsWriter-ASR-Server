# 历史审查与否决证据附录（#81 清账）

本附录只做一件事：**当前交付结论所依赖的历史审查/否决证据，在这里可核查**。原文不改写、不合并进
现行结论；每段摘录都带精确 source（`ref@fullsha` + 路径），并保留可读的恢复指针。

## 0. 读取规则

- **摘录形态**：每份证据分两档。承担结论的判定段（header 的 `failure-visibility`、结论段、处置段、
  判定口径、完成判定）**原文整段保留**在下方围栏内，围栏前后有 `source-check` 注释，可用
  `verify_sources.py` 逐字比对源对象；不承担结论的篇幅（已审实现清单、未验证范围、附表）**不复制**，
  保留在归档 ref，用下方恢复命令读原文。
- **时点纪律**：历史否决与历史验收都不能覆盖当前时点。旧失败不是当前红，新验收不回洗旧失败。
- **可读性**：盘点时点本文所列全部 source SHA 在本对象库均可解析为可读提交（复算 449 条来源记录，
  `OBJECT_UNAVAILABLE` / `QUERY_ERROR` 均为 0）。这个「0」是**那次运行的记录**，不是随仓冻结的分母清单；
  新克隆若未取齐历史对象会逐条报 `OBJECT_UNAVAILABLE`。若将来某 ref 不可读，指针即为
  `UNKNOWN` 而不是「已归档」。

## 1. 证据 A：浮点 PCM 分段量化 P2（当前 design 保留结论的历史依据）

- 当前保留结论的位置：基线 `docs/sessions/261001-http-files/design.md:24`（量化公式）与 `:26`
  （P2 分级保留）。该结论不是本轮新判断，它来自下述审查。
- source：`refs/heads/card/http-e1-review-a-261001@d52f8687cb2ed90114547674d84875244576126e`
  路径 `docs/sessions/261001-http-files/reviews/E1-owner-review-A-verdict.md`
- 适用审查对象：`9e40df201e9e3cdf4dad18deec7629974b3d6fb3..d090b7d238fe82d8f0303d6e3d304a8f38da1f10`，
  risk-tier internal，历史时点 2026-10-01。
- 基线状态：该路径在基线树不存在（`MISSING_AT_BASE`），去向量为 `archive-pointer-current-dependency`。

<!-- source-check: refs/heads/card/http-e1-review-a-261001@d52f8687cb2ed90114547674d84875244576126e docs/sessions/261001-http-files/reviews/E1-owner-review-A-verdict.md EV-A1 -->
```text
# E1 owner 与共享 PCM 分段独立审查

审查对象固定为 `9e40df201e9e3cdf4dad18deec7629974b3d6fb3..d090b7d238fe82d8f0303d6e3d304a8f38da1f10`，risk-tier 为 internal。

failure-visibility: p2-only

## 结论

本轮审查完成。结论为通过，发现一项 P2：合法浮点分段参数可使 WebSocket producer 生成非 float32 对齐的 PCM 段，识别任务随后以可见错误失败。按审查纪律，此项不阻塞合并，可登记后续修复。

未发现 owner 三元键串扰、HTTP 结果走 WebSocket 出站、缺 sink 时静默丢结果、或 E1 默认启用 HTTP 业务入口的问题。
```

<!-- source-check: refs/heads/card/http-e1-review-a-261001@d52f8687cb2ed90114547674d84875244576126e docs/sessions/261001-http-files/reviews/E1-owner-review-A-verdict.md EV-A2 -->
```text
- **处置**：建议后续将秒数先按旧语义量化为采样点，再乘 float32 stride；切点 stride 与 overlap bytes 都必须按采样点换算。此轮不改被审实现。
```

- 该 verdict 承担结论的篇幅到此为止；「已审实现与不变式」「未验证范围与后续接线」两节不复制，原文在归档 ref。
- 恢复命令：
  `git show d52f8687cb2ed90114547674d84875244576126e:docs/sessions/261001-http-files/reviews/E1-owner-review-A-verdict.md`

## 2. 证据 B：M6 在 `9024008` 时点的历史否决

- 当前时点对照：基线 `docs/sessions/261003-http-completion/m6-final-merged-acceptance.md:12` 把完成
  结论冻结在 merge `796104c371c672609cc38ef17d472ef383228cf7`；`:68` 的冻结边界声明结论不覆盖之后的主干。
  **两个时点互不覆盖**：下述否决在该时点成立，不因后续验收而失效；后续验收也不回洗该时点的缺口记录。
- source：`refs/heads/card/http-m6-final-evidence-audit-261005@4565bfccc030ea9465e1e2971b497198dbfebeab`
  路径 `docs/sessions/261003-http-completion/m6-final-evidence-audit.md`
- 基线状态：`MISSING_AT_BASE`，去向量为 `archive-pointer-current-dependency`。

<!-- source-check: refs/heads/card/http-m6-final-evidence-audit-261005@4565bfccc030ea9465e1e2971b497198dbfebeab docs/sessions/261003-http-completion/m6-final-evidence-audit.md EV-B1 -->
```text
- **源码基线**：`902400887445603a58f7dc960a24e809ca779a0a`；本表按该树核查。
- **Goal 状态**：`goals/http-integration/M6-qa.md` 仍为「进行中」。本盘点不改 Goal、不缩减五轮或双环境要求。
- **判定口径**：表中「达」只表示该组的跨边界断言存在，且 902 主干 hosted 全套测试 job 成功一次；不代表 M6 整体完成。
```

<!-- source-check: refs/heads/card/http-m6-final-evidence-audit-261005@4565bfccc030ea9465e1e2971b497198dbfebeab docs/sessions/261003-http-completion/m6-final-evidence-audit.md EV-B2 -->
```text
- **总体**：十二组已有可追溯测试，902 hosted 的 `tests/` job 单轮成功；原完成条件仍**未达**：没有同一隔离服务的并发/取消/重启完整矩阵五轮，也没有同一 902 源码在 hosted runner 与无会话 bare shell 各执行该矩阵五轮的证据。当前 skip 只可报已知历史事实：旧 499+3 的三项为 ForceAligner×2、silero-VAD/onnxruntime×1；902 hosted 的 skip 数和真实原因未由安全结构查询证实。
```

- 十二组逐组证据表与「下一步最小运行边界」承担的是该次盘点的细节，不承担当前结论，不复制；原文在归档 ref。
- 恢复命令：
  `git show 4565bfccc030ea9465e1e2971b497198dbfebeab:docs/sessions/261003-http-completion/m6-final-evidence-audit.md`

## 3. 关联未证实的泛称引用（如实标注，不强贴）

- 基线 `docs/sessions/261001-http-files/design.md:5` 写「独立规划终审历史没有完整覆盖」，**未点名任何
  文件**。候选 `docs/sessions/260930-http-file/reviews/eng-outside-verdict.md`
  （`refs/heads/card/http-eng-outside-260930@69bee18d0c6d225bd4b0e472bc3ada97bd7fa543`）是一份计划级
  独立逻辑挑战，结论为「实施前补足计划」。
- **关联未证实**：本卡没有找到证据证明该文件就是 `:5` 所指的那次终审，也没有证据证明它不是。因此
  本附录只保留指针与下述一行结论原文，**不把它当当前缺陷、不当当前结论的依据**。
- 去向量为 `archive-pointer-association-unverified`，未升级为证据。

<!-- source-check: refs/heads/card/http-eng-outside-260930@69bee18d0c6d225bd4b0e472bc3ada97bd7fa543 docs/sessions/260930-http-file/reviews/eng-outside-verdict.md EV-C1 -->
```text
共 3 条计划级 finding；均可在现有锁定行为内补足，不要求新增平台、自动重试或改变 WS 契约。其他检查到的 commit 顺序、offset ACK、结果与 DONE 同事务、重启不自动重跑、容量拒收与 WS 兼容约束已有明确计划条款，因此不另列猜测。
```

- 恢复命令：
  `git show 69bee18d0c6d225bd4b0e472bc3ada97bd7fa543:docs/sessions/260930-http-file/reviews/eng-outside-verdict.md`

## 4. 纯旧过程：只留指针（无当前消费者）

以下两份是 M6 五轮矩阵的**过程**审查，不承担当前 M6 验收结论。当前验收所称「H1 两份完整审查 +
H2 精确增量审查」在基线树已有同名文件（`reviews/m6-h1-full-review1-verdict.md`、
`reviews/m6-h1-full-review2-verdict.md`、`reviews/m6-h2-increment-verdict.md`），与下列过程 verdict
**不是同一文件**；全仓 `git grep` 对下面两个路径 0 命中，无人引用。

| 路径 | source | 恢复命令 |
| --- | --- | --- |
| `docs/sessions/261003-http-completion/reviews/m6-repeat-matrix-review1-verdict.md` | `refs/heads/card/http-m6-matrix-cold-review1-261005@03e8e48dd89f1fda14a72a467f5b8dc0546db09e` | `git show 03e8e48dd89f1fda14a72a467f5b8dc0546db09e:docs/sessions/261003-http-completion/reviews/m6-repeat-matrix-review1-verdict.md` |
| `docs/sessions/261003-http-completion/reviews/m6-repeat-matrix-increment-verdict.md` | `refs/heads/card/http-m6-matrix-increment-review-261005@1c566b54f88db8b047b42665118a32a681e969c5` | `git show 1c566b54f88db8b047b42665118a32a681e969c5:docs/sessions/261003-http-completion/reviews/m6-repeat-matrix-increment-verdict.md` |

## 5. 在途，不属本卡（#82）

`docs/sessions/261003-http-completion/reviews/windows-http-integrity-review1-verdict.md`、
`windows-http-integrity-posix-verdict.md`、`windows-http-integrity-native-verdict.md` 与
`progress/windows-http-integrity-fix-progress.md` 归 **PR #82**（head 分支
`card/http-windows-integrity-pr-delivery-261005`，盘点时点为 open）交付。本卡**不复制、不重复交付、
不视为已解决**，去向量为 `in-flight-issue-82`。

## 6. 摘录逐字校验

`source-check` 注释后的围栏内容必须与对应 source 的 Git 对象**连续完整行字节**一致（顺序、相邻关系、
空行都参与判定；不是行集合，也不是子串包含）。随仓复算入口：
[`docs/development/known-issues/artifact-disposition-261006.md`](../../development/known-issues/artifact-disposition-261006.md)
的「公开自包含复算入口」一节——把那段代码存成 `verify_artifact_disposition.py` 放仓库根即可运行，
第 3 关就校这 5 段摘录，并带首字符变异负控。校验只依赖 Git 对象，不依赖工作区文件。

第 3 节的 `EV-C1` 原文行在首轮是截断的（只取到「……改变 WS 契约。」），本轮已改为**整行原文**
（后续半句一并保留），以便连续字节判定成立。后续审查又发现「行集合」判据会放过重排，现已改为连续字节判定，
并实测换序反例会失败。

**摘录的用途边界**：这 5 段只用于**指定的历史判断 + 适用 SHA**（PCM 量化 P2 的分级、M6 两个时点的并列）。
它们**不是完整审查结论**；承担完整审查结论的文件仍以原对象指针为准
（`git show d52f8687cb2ed90114547674d84875244576126e:docs/sessions/261001-http-files/reviews/E1-owner-review-A-verdict.md`）。

覆盖限制：该入口依赖**持有本地归档对象的仓库**；新克隆未取齐历史对象时，对应来源报
`OBJECT_UNAVAILABLE`（对象不可用），不是「来源缺路径」，脚本逐条打印、不静默通过。