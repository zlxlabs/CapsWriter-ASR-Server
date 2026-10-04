# PR64 ready 事件 primary 事实分诊

## 结论

本次对象是 PR64 在 `ready_for_review` 事件产生的 run `37188220228`、attempt `1`，不是 draft 绿 run、旧 callback run 或同 head 的 pin15/latest 成功 run。固定审查范围为 `820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..4e8ecaa69417bb4883b2d19c2352bc1b62f15a0b`；head、PR base 和 run head 三者一致。

机器终态是**真实 primary 审查完成后给出 finding**，不是模型错误、准备失败、产物发布失败或聚合器误判：

- primary job `111394720008` / step 9 `Run review-primary` 为 `failure`；其后 `Annotate primary findings`、`Upload canonical primary audit`、`Upload primary review diagnostics` 均为 `success`。
- producer 在规范化后的失败输出中写出 3 条 finding：`major=1`、`minor=1`、`nit=1`，三条均指向 `scripts/_baseline_http_ws.py`。finding ID 只保留哈希，不在本文回显。
- aggregator job `111395476226` 读取了匹配本 run/attempt 的 primary audit；其机读行是 `gate_result=fail`、`classification=code_fail`、`reason_code=primary_findings`、`primary=executed`。
- GitHub Actions artifact API 的 `total_count=0` 不能作为零 finding 证据；本门禁的 canonical audit 走 Silo。当前调查环境没有 Silo 读取凭据，因此没有填造 audit JSON 的 `executedModel`、逐 finding `line/trigger/evidence` 等缺失字段。

因此，本次不派产品修复、不重跑 Actions、不申诉 gate。当前 gate 红是新 ready 事件的真实主审红；主干基线 API 不可用，无法判定同作业/首失败步骤是否为继承红，不能声称 streak 或继承关系。

## producer → 发布 → consumer

实际使用的可复用工作流是 `zlxlabs/gate/.github/workflows/gate-v2.yml@v2`，run 记录的实际 SHA 为 `6fd21e0ab5a27a279fe5cd15dd74edaa0b079fe9`。

1. `Run review-primary` 以 `PAYLOAD_ONLY` 模式运行 gate-hub 的 primary producer。producer 先对 model result 做 redline calibration 和 verdict normalization，再构造 `primary_review` audit；`verdict=fail` 时合法退出码为 1，不等于 setup failure。
2. `Upload canonical primary audit` 以当前 repository/head/run/attempt 组成的 canonical 名称写入 Silo，步骤成功；随后 aggregator job 按当前 attempt resolve、download，并执行 audit identity 校验。
3. aggregator 的 `AGENT-GATE-VERDICT-V1` payload 是 `fail/code_fail/primary_findings/executed`。这条 payload 不是人类可读摘要的关键词推断，而是消费者实际写出的机器字段。
4. GitHub check annotations 共 4 条，仅保留数量、位置和摘要哈希；它们不是 primary audit 的替代品。GitHub artifact `total_count=0` 只说明 GitHub artifact 通道为空。

安全证据指纹：

| 对象 | 状态/计数 | SHA-256 |
|---|---:|---|
| PR body | 3467 bytes | `3e2a6622733abd9a8eef458af0ea3489997d4a22717a51f4addf6bf4bca60fba` |
| primary job log | 233266 bytes / 3910 lines | `d6be763d03d8f964d1f77f83a14a2960ad710387e77ef148007a0b0499408a34` |
| aggregator job log | 152273 bytes / 2589 lines | `75871cabf4d0d8884cf8a0b70f71e418efb9ce7ecffe023aacb3a0fcfea83cd0` |
| annotations JSON | 4 entries | `20ed166460a1f6145be119535d073c6f7bce4bc302f2785a49fa8d1721fdf29a` |
| machine terminal verdict | 1 entry | `04a53ebeaeadc082a947bc369deffc4ebe2b69cccd21beddd4110de84ecb2e15`（该行） |

## findings 分诊

| machine finding | 工具严重度 | 安全位置 | 本仓两问 | 处置 |
|---|---|---|---|---|
| ID hash `fe1532bbb12091457abc2d909bfb56b179eddf093aa0bcfe119f1518f3f2dc41` | `major` | `scripts/_baseline_http_ws.py`；canonical line 未从 Silo audit 取到 | 精确 machine trigger 仍 `unknown`。对“16 kHz 双声道 WAV 的 decoded-size 快速路径”这一可证伪解释做了真实 loopback 探针：0.1 s、1600 frames、6444 bytes、2 channels，CLI 实际返回 `status=ok`，报告 `decoded_pcm_bytes=6400`，等于目标单声道 float32 的 6400 bytes；因此该解释没有重现错误结果。未观察崩溃、静默错误、数据损坏或越权后果。 | 不判 P1，不自修；待取得只含合法字段的 audit 证据后再决定 `refuted` 或真实等级。 |
| ID hash `9e16f96927c702ef6b44556ff810570f585108975186dfe630338e09b28c4bbe` | `minor` | `scripts/_baseline_http_ws.py`；canonical line 未取到 | producer 安全主题仅显示 HTTP/recovery/result；精确 trigger/evidence 未从 Silo audit 读取，不能补写。 | 记录为非阻塞 unknown，不扩设计。 |
| ID hash `992aac98a7e890c7aadde2c02947280b8a0dd24128d12e384cb8c21f6bf34743` | `nit` | `scripts/_baseline_http_ws.py`；canonical line 未取到 | 未取得精确 trigger；不满足 P1 两问。 | 非阻塞 unknown。 |

探针证据的关键不变式是：基线只报告“解码为目标单声道 float32 后的字节数”，不要求工具保留一份 PCM 缓冲。双声道输入的 soundfile 原始二维 float32 缓冲为 12800 bytes，而目标单声道输出长度为 6400 bytes；当前实现报告的是后者。因此，不能仅凭“没有显式 downmix buffer”把这条解释升级为 P1。

## 未知与建议

- `executedModel`：当前 producer/aggregator 可见安全输出没有该字段；Silo audit 正文没有本地读取权限，保持 `unknown`。
- canonical audit 的完整 `result.findings[*]`：producer 已证明数量和 severity 分布，逐 finding 的 `line/trigger/evidence/acceptance` 未取到，保持 `unknown`。
- provider 原始响应、日志原文、凭据、URL 参数、样本和 stdout：未纳入本文。
- 建议下一步采用客观证伪回执：只提供 `command`、匿名 `output`（计数/长度/哈希/合法枚举）、机器 `pointer` 和 `result`，先补齐 major finding 的真实 trigger/evidence，再决定是否开一个边界明确的修复卡。本卡不发送该回执。
- 不建议为这次真实 `primary_findings` 红做正常 rerun；rerun 会产生新的 review attempt 和 finding 身份，不能替代缺失的 audit 字段，也有门禁/评论/产物副作用。
