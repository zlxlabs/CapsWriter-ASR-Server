# PR64 规范意见风险分诊进度

- Dispatch-Id: `dlg-20261004-171017-b9ff14`
- 固定范围：`820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2` → H0 `4e8ecaa69417bb4883b2d19c2352bc1b62f15a0b`
- 规范输入：audit-safe 对象 B（8256 字节 / SHA `948ce79ae2f82db68655971195d405c2a1b4b824dd57c9f8ece20dd4543978d6`）三条 finding；未把实现方旧 review 当输入。
- 现场：worktree `card/http-pr64-canonical-risk-261005`，HEAD 即冻结 H0；无交接单。仓旁授权 `temp/full.wav`、`full_x3.wav`、`000_video.mp4` 可访问（只元数据）。`m7-platform-inventory.md` 本树缺失。
- 实测：私有 `01_decode_measure.py`（授权短素材 + 稀疏大 WAV/`RLIMIT_AS=256MiB`）与 `02_recovery_order.py`（loopback stub + 真实 CLI/SDK，同 ID 预置结果）。脚本与 JSON 留在派发 scratch，不入库。
- 结论：`failure-visibility: p2-only`。B1/B2 = P2 accepted，B3 = nit。无 P1。未改代码、未建 tracking issue、未 OCR、未 rerun PR。
- 验证：`git diff --check HEAD^ HEAD`（提交后）。主干 CI 基线未能判定。
- 后续（docs-only，本卡）：`docs/guides/http-baseline.md` 与 `_baseline_http_ws.py` 的 module/`_decode_pcm_bytes` docstring 收窄为「本批短素材实验采集」，不修 P2 行为。两 P2 跟踪本仓 #72（OPEN），不是已实现；指南 fresh fixture ID 不是 B2 修复。正式 deferred 签发路径当前政策拒绝，不伪签。
