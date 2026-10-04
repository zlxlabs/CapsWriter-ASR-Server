# C2 固定增量独立审查进度

- 固定对象：820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..9ef0e52145bc89610fb322724462955fb2fad15a；风险档 internal；未追分支后续提交。
- 阶段 1（规格与代码）：完成 design261001、M4 plan 与六个服务端/测试文件的审查；程序性偏差见阶段 4，不能标称完全冷审。
- 阶段 2（运行证据）：定向 cleanup 为 websockets 15.0.1/17.2 各 13 passed；全量固定版 459 passed, 3 skipped，最新版 17.2 裸 shell 455 passed, 7 skipped。裸 shell 5 轮、真实 user systemd 6 轮完成实际 DONE/FAILED fatal 重启；另完成 Manager/worker 已启动后的真实 RuntimeError 初始化失败探针和一轮 SIGTERM/在途 cleanup 竞态探针。
- 阶段 3（OCR 与约束力）：OCR envelope 为 reviewed_fallback，primary leg timeout、DeepSeek backup success；两条 finding 已人工按真实触发与后果分级为 P2。两处最小反向变异都令对应断言转红。
- 阶段 4（交付）：实质结论 failure-visibility: p2-only。执行器结论标记 failed：一次跨整个 docs/ 的 rg 命令命中了任务明令禁读的旧 review/evidence 片段。没有引用其内容作为证据，但“新鲜冷输入”条件无法恢复；建议重新派干净上下文复审。
- 允许写入路径仅本进度文件与 reviews/c2-fixed-review1-verdict.md；无服务端或测试代码更改。完整报告写入派发报告路径；没有 PR 操作。
- 临时真实证据保留在 scripts/tmp/c2-fixed-review1-261004/summary.jsonl。第一条反向变异记录曾含合成 pytest 断言全文，现已从本地摘要清理为断言类别；探针脚本均保留。
- 未知项：OCR finding 1 的非 RuntimeError/已结束 stop callback 精确时序；AppRunner teardown 在双 stop 时的确切先后；GitHub 基线 unavailable，继承红未知。
