# OCR 连续无 envelope：持有仓 issue 取证

审查纪律：同机连续 ≥3 次 OCR `skipped` 须立/更新 issue，不阻塞独立人工审查，但不能无限失效而指标全绿。本卡只记证据指针，不修包装器、不新扫描、不断因。

## 动作

- 持有仓：`zlxlabs/gate-hub`
- 检索：open issue 同指纹已存在，**评论现有 issue，未新建，未 close/reopen 旧单 48**
- issue：https://github.com/zlxlabs/gate-hub/issues/1276 （`#1276` OPEN，标题「本地 OCR 包装器连续三次卡在 primary/start，无 JSON envelope」）
- 评论：https://github.com/zlxlabs/gate-hub/issues/1276#issuecomment-5996359745 （id `5996359745`）
- 包装器归属：对持有仓 `scripts/review/ocr-review` 做 `readlink`，**不是软链**，是仓内常规可执行文件；其 `exec python3 scripts/review/ocr_quota_preflight.py local-review …`
- 未要求新增 retry / fallback / pool / 配置；cause=unknown

## 三次 skipped（不得当 clean）

1. **Codex 五轮矩阵独立审查执行器报告**：审查对象 `6aa76f6c6935e9cef00afc1bcbcf8327e7c95488..da81cacc13061be8a7693775ebca7e413a29a189`。包装器约 8 分钟 stdout 0 字节，有界等待中断、退出码 130；记 skipped / no envelope。背景摘要在该报告中**声称** 580 字节（本卡未独立按字节复核，不把声称标成真测）。随后独立审完整 diff。
2. **增量审查仓内 verdict**（公开分支尖 `1c566b54f88db8b047b42665118a32a681e969c5`）：两次主腿观察时段内无 stdout envelope，后一次于五分钟上限中断；OCR `skipped`，coverage/verifier 未知。卡面另称某任务 TIMEOUT/report0 仅为**任务终态**；指定 verdict 未出现该字段，**不把 OCR 写成 timeout 根因**。
3. **Cursor 五轮矩阵独立审查执行器报告 + 仓内 verdict**（公开分支尖 `aafb9ef2526cc0e70d73ff9bf77d3400e9a6c470`，对象 `6aa76f6c6935e9cef00afc1bcbcf8327e7c95488..337689689c9b2a314548b70667e447841bf070ad`）：约 6 分钟 stdout 0，stderr 仅 `leg=primary event=start`，无完整 JSON envelope；status skipped。同轮独立测试 12 passed。不得表述为扫干净。

stdout 无 envelope = 包装器或上游等待未知。不断言额度、模型缺陷或认证失败。

## 正交与未决

- 人工审查仍是独立流程；OCR 不可用 ≠ 任务结果。
- 指定私有材料未删除、未外泄机器路径。
- 派发基线不可用（`gh api request failed`）：继承红**未能判定**；本卡无业务 App/CI/Goal/PR 改动，无新红。
- 期望：未来扫描给出完整 `reviewed` / `reviewed_fallback` / `skipped` JSON envelope，或及时失败。
