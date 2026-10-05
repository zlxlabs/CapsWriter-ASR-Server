# M7 短素材实验范围澄清进度

- Dispatch-Id: `dlg-20261005-012732-a1b0d7`
- Base: `2b5afec637af00da9524534743d6a34002e8afb4`（已含 peer 风险表两 Doc；代码仍为 H0 `4e8ecaa69417bb4883b2d19c2352bc1b62f15a0b`）
- 角色：叶 documentation clarification；不 delegate、不新 review、不修 P2 行为。

## 本卡改动

- 新增与继承分开：peer 风险表 `docs/sessions/261003-http-completion/reviews/pr64-canonical-risk-verdict.md` 与原 `pr64-canonical-risk-progress.md` 正文不改写；进度只追加本条后续说明。
- 新写：`docs/guides/http-baseline.md` 增加「实际实验范围」，收窄「所有失败受控 / 任意大小输入」读法；失败路径写明内核 OOM 可能绕过 `BASELINE_FAILED`，当前 `MemoryError` 只是普通 Exception 的 fail-loud。
- 新写：`scripts/_baseline_http_ws.py` 仅 module docstring 与 `_decode_pcm_bytes` docstring；零条可执行语句。
- 独占落盘、fresh fixture ID、recovery 先删后写仍作为当前操作契约保留，并指向本仓 #72；不把「可再生成」写成零损失。

## 明确不是

- 不是代码强制时长上限，不是已拒超限 / 已流式 / 内存上界保护。
- 不是服务端或 SDK 文件任务协议收窄到约 232 秒。
- 不是对 B1/B2 的实现修复；#72 仍 OPEN。
- 不删 `shutil`、不改 recovery 顺序、不加 threshold/streaming/config/pool/fallback/重试。

## 跟踪

- 规范 B1/B2/B3 实测表与两问仍以 `pr64-canonical-risk-verdict.md` 为准。
- 本仓 #72 OPEN：后续扩大到超大媒体时的输入边界/计数，以及结果写完再清 recovery 的验收。
- 正式 deferred 签发：run 37224512609 failed；平台 `issue_receipt.py` 对每个 deferred 均 `deferred_not_allowed_for_tier`。本卡不改 Gate/agent-config，不重试该政策路径，不伪签 deferred。
