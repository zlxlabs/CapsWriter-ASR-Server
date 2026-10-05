---
lane: http-core
id: M4
slug: resources
status: 已完成
owner: pi协调
order: 4
priority: 高
depends_on: [http-core/M3]
merged_pr: 62
---

# 里程碑进度：http-core/M4：资源边界与重启清理

- **预期产出**：上传、解码、队列、结果和磁盘配额；部分上传/任务重启收敛；终态源音频清理与活跃引用保护。
- **当前范围**：落实已锁定的资源起点和 7 天源音频策略，不新增自动重跑或删除任务记录/结果。
- **关键决策**：容量不足明确拒收；源音频只在终态 7 天且无活跃引用时清理；结果独立保留。
- **已知阻塞**：M4 产品与合并主干验收已完成。资源/容量增量 PR #60 合并 `820c3a2`，七天终态清理/故障回收 PR #62 合并 `4de4a7f`；不代表 M6/M7、生产部署或任意规模性能验收已完成。
- **推进前必须拿到的证据**：
  - [x] 精确时钟覆盖 TTL 前后、活跃引用和重启顺序；环境：实际合并主干 `4de4a7f` 的裸 shell/systemd 隔离测试矩阵，入口：周期清理/HTTP/真实识别子进程夹具。终态 7 天、引用释放、部分源与结果保留、SQLite 重开和 fatal/TERM 资源收尾均有实际测试。
  - [x] 物理磁盘/SQLite WAL/结果预留越界明确拒收；环境：隔离数据目录及合并主干完整测试，入口：实际 HTTP upload/commit。C1 结果/WAL 预留、共享准入与物理 margin 负例在当前套件通过；未将边界夹具误报为 GiB 体量压测。
- **完成条件**：清理不误删活跃源，删源后结果仍可读，重启不重置期限，资源超限无静默降级。

## 2026-10-05 正式收口证据

- 产品提交：PR #62 精确 head `7a3a964` 完整正式 gate `37251805186`（primary/quality/aggregate/OCR/ledger SUCCESS），合并主干 `4de4a7ffa44dfb50b48c252510927c4b2166cc77`。
- 主干 CI `37252990501` 三个 job SUCCESS：Python 3.11 SDK 两种 WS 各 61 passed，Python 3.12 全量 476 passed/3 skipped/149 warnings。
- 该主干两套本地全量实际各 476 passed/3 skipped，WS 15.0.1 与 17.2，测试执行预算每套 900 秒；裸环境与 systemd 的真实生命周期和 SDK→TCP→FFmpeg/FileRunner→worker/persisted result 边界已执行。识别 fixture 为明确 stub，不外推模型质量。
- 证据：`docs/sessions/261003-http-completion/c1-merged-acceptance-evidence.md`、`c2-merged-acceptance-evidence.md`；每个关键不变量均有代码与已执行测试定位。
- 文档头 `26ad16a9` 不等于产品 merge；新子派发的精确两 SHA 文档 precheck 原 900/1200 预算为 green。旧 scope red JSON 引用另一对象且实际旧提交署名存在，旧 JSON/父报告保持，原因仍未知；no-signal-lines 不替应用测试，resume integrity unknown 不改成 clean。
- 元数据 overshoot、超大历史 scan/stat 成本、显式 stop/fatal 重叠等接受的边界仍见 #61；没有生产重启、生产认证、全面 no-leak 或任意规模性能承诺。
