## HTTP 段超时生命周期隔离
- 当前阶段：implementing
- 本段结论：待验证前提 1 由 `tests/test_ws_progress_watchdog.py::test_s5_segment_timeout_fails_only_that_task_and_keeps_server_alive` 支持：超时后慢推理返回，worker 子进程仍能处理后续任务；新 HTTP 集成复现已在 89a5192 上红，修复后通过。
- 关键决策与已否决方案：HTTP 成功落库 FAILED 后直接继续监控循环，复用 WS「只终结当前任务」策略；不杀死或重启仍可工作的 worker。
- 下一步唯一动作：完成 WS 终态 task_id 迟到帧准入前丢弃并验证。
