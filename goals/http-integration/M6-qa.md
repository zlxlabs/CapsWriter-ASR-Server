---
lane: http-integration
id: M6
slug: qa
status: 已完成
owner: pi协调
order: 1
priority: 高
depends_on: [http-core/M4, http-sdk/M5]
merged_pr: 83
---

# 里程碑进度：http-integration/M6：HTTP 边界 QA

- **预期产出**：12 组 producer、重启、并发、错误和旧 WS 验收，含至少五次并发回归。
- **当前范围**：只验证隔离服务与真实客户端/文件/进程边界，不访问生产端口、模型或录音。
- **关键决策**：反向注入必须以 AssertionError 变红；ImportError/恒真断言不算；CI/bare shell 消费环境都要覆盖。
- **已知阻塞**：无阻塞，M6 已收口。两段历史保留不改写：原 #63 CLOSED 未 merged；候选 `5db84d3` 所在 PR #73 已于 2026-10-05 合并（`3d26d90b`）完成十二组边界 QA 收口，不再处于 ready 等待；五轮并发/取消/重启矩阵与留存证据由 PR #83 收尾，head `75a1317`，合并主干 `796104c3`（2026-10-06T01:29:53Z，非 squash）。Draft 期 SKIPPED 的 primary/OCR 与 hosted runner 获取失败均不算批准或红。
- **推进前必须拿到的证据**：
  - [x] 真实 SDK/CLI producer body、subprocess argv/env、文件字节和 Queue pickle payload 均有断言；环境：CI 标准/tmp 与无会话裸 shell（`env -i` 白名单八键，child 观测会话键 absent）；入口：`pytest tests/`（SDK PATCH/落盘 SHA、跨连接领取、丢 202 唯一恢复、未确认后缀、SIGTERM 重启、持久 fullResult、同 worker HTTP+WS、取消/IO 交错、容量缩常量、PCM oracle 两参数、末段 finalfail 各 1 次，五轮含旧 WS 回归）。
  - [x] 同一隔离服务执行并发/取消/重启矩阵至少 5 次且旧 WS 回归通过；环境：CI hosted runner（run#37339081182，artifact 11356924649）与无会话裸 shell（源 `c6a1738`）分别独立跑满 5 轮×4 相位，互不代充。
- **完成条件**：12 组验收均有可追溯 fixture/命令/环境，真实 skip 原因单列，不能用 draft 绿代替行为证据。

## 2026-10-06 正式验收收口

- 合并事实：PR #83 head `75a1317905e607aebb279bffcb31a9e6839b00d0`，merge `796104c371c672609cc38ef17d472ef383228cf7`（parents `6aa76f6c`+`75a1317`，19 文件 +2250/-4）。CodeHead `77940745`（实现树）与 merge、head 是三个不同身份，不可互代。
- 正式 Ready gate run#37364843281 的 primary/ocr-minimax/quality/resolve/gate/ledger 全 SUCCESS（notify 非必需 skipped）；旧 Draft gate run#37364159057 的 primary/OCR skip 不作批准。合并后主干 CI run#37399462648（push，head `796104c`）三个 job 全 SUCCESS。
- 审查资格：H1 两份完整审查 + H2 精确增量审查（p2-only，无应用 P1），不靠新增验收文档刷审查次数。
- 证据定位与分层（含真实 P2 与 unknown、假引擎不等于 ASR 质量、schema-only 消费者不等于认证任意 JSON）：`docs/sessions/261003-http-completion/m6-final-merged-acceptance.md`。
- 本次只回写里程碑状态；M7、生产部署、Windows 平台与真实 ASR 质量未被此验收代替，仍未完成。
- 冻结边界：本条完成结论只覆盖合并主干 `796104c3` 及其真实运行与审查。此后主干已前移到 `d251618e`（改了 `core/`、`sdk/`、`tests/` 运行源码），不在上述非文档 340 集合等价、全量 511 passed 双臂、裸壳与 Hosted 真五轮的覆盖内；本 Goal 记的是「M6 在 `796104c3` 历史时点真实完成」，不是「在最新主干上再次全量验证 M6」。
