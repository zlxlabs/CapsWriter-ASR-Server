# PR64 ready primary 分诊进度

## 本轮状态

- 范围冻结：`820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..4e8ecaa69417bb4883b2d19c2352bc1b62f15a0b`。
- 目标事件：run `37188220228` / attempt `1` / head `4e8ecaa69417bb4883b2d19c2352bc1b62f15a0b`。
- primary：job `111394720008`，仅 step 9 `Run review-primary` 失败；canonical audit 上传步骤成功。
- aggregator：job `111395476226`，机器终态 `fail / code_fail / primary_findings / executed`。
- producer findings：3 条，`major=1`、`minor=1`、`nit=1`，均在 `scripts/_baseline_http_ws.py`。
- GitHub artifact：`total_count=0`；不把它解释成 Silo audit 缺失或零 finding。

## 事实字段

| 字段 | 结论 |
|---|---|
| primary status | `verdict=fail`，且有规范化后的 finding 输出 |
| failure class | aggregator `classification=code_fail`、`reason_code=primary_findings` |
| executed model | `unknown`；当前安全日志没有字段，Silo audit 正文未取得 |
| normalized findings | 可由 producer 失败输出确认数量、严重度和文件；完整 line/trigger/evidence 未取得 |
| application verdict | 本轮未运行产品应用判定；与 gate verdict 正交 |

## 两问探针

对 major 的“16 kHz 多声道 WAV 解码大小快速路径”解释，在自 PID 随机 loopback 服务上用 0.1 秒、1600 frames、6444 bytes、2 channels 的 synthetic WAV 跑真实基线 CLI：

- 返回 `status=ok`，`decoded_pcm_bytes=6400`；
- 目标单声道 float32 长度也是 `6400` bytes；
- soundfile 二维多声道 float32 缓冲是 `12800` bytes；
- 在该解释下没有重现错误结果、崩溃、数据损坏或越权。

精确的 machine trigger 仍因 Silo audit body 不可读而是 `unknown`，所以不把这次探针写成“已证伪全部 finding”，也不派 P1 修复。

## 下一步

本轮只保留事实文档，不修产品、不修改测试或配置、不重跑 Actions。若要继续，应提交只含 `command/output/pointer/result` 合法字段的客观证伪回执，补齐 major 的真实 `line/trigger/evidence/acceptance` 后再决定是否开边界明确的修复卡。
