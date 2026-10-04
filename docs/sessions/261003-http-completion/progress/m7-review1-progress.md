<!-- succeeded -->
# M7-A 首审进度

- Dispatch: `dlg-20261004-023723-bfb264`
- 固定审查范围：`820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..3329467c9c6694d790c2378f534a57919f2f6afa`
- 阶段 1/4（固定范围与协议/SDK 契约审查）：完成；未读取实现 progress、Linux evidence、前审结论或真实音频/模型结果。
- 阶段 2/4（新增测试、真实 producer fixture、静态与 OCR 初筛）：完成；`websockets==15.0.1` 与解析到的最新 `17.2` 均通过 6 项测试；OCR envelope 为 `reviewed/primary_selected`，人工复核后 2 项确认、1 项驳回。
- 阶段 3/4（systemd 白名单与裸 shell 的 loopback 合成边界）：完成；同源 HTTP/WS CLI 捕获、私有 JSON 原始字节与权限、失败路径、两个以上 AssertionError 红验均已实测；没有连接 ASR 生产或加载模型。
- 阶段 4/4（四问、severity 与不变式测试索引）：完成；最终结论为两项 P2、一项 P3、无 P1；`failure-visibility: p2-only`。完整理由、未知项与证据见首审 verdict 及派发报告。
