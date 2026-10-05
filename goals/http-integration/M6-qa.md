---
lane: http-integration
id: M6
slug: qa
status: 进行中
owner: pi协调
order: 1
priority: 高
depends_on: [http-core/M4, http-sdk/M5]
merged_pr: null
---

# 里程碑进度：http-integration/M6：HTTP 边界 QA

- **预期产出**：12 组 producer、重启、并发、错误和旧 WS 验收，含至少五次并发回归。
- **当前范围**：只验证隔离服务与真实客户端/文件/进程边界，不访问生产端口、模型或录音。
- **关键决策**：反向注入必须以 AssertionError 变红；ImportError/恒真断言不算；CI/bare shell 消费环境都要覆盖。
- **已知阻塞**：M4 产品已随 PR #60/#62 合并，M5 客户端已合并，真实 HTTP 业务入口可用。当前 QA 候选 `5db84d3` 的两版本 482 passed/3 skipped、裸 env -i 与 systemd 六条 e2e 均通过，PR #73 已 ready；剩余完整正式 gate、精确合并、合并主干验收及最终并发矩阵证据，不能用旧草稿 SKIPPED 当批准。原 #63 CLOSED 未 merged，现 #73 正常接续。
- **推进前必须拿到的证据**：
  - [ ] 真实 SDK/CLI producer body、subprocess argv/env、文件字节和 Queue pickle payload 均有断言；环境：CI 标准/tmp，入口：pytest tests/。
  - [ ] 同一隔离服务执行并发/取消/重启矩阵至少 5 次且旧 WS 回归通过；环境：CI hosted runner 与无会话裸 shell。
- **完成条件**：12 组验收均有可追溯 fixture/命令/环境，真实 skip 原因单列，不能用 draft 绿代替行为证据。
