## HTTP 段超时生命周期隔离
- 当前阶段：implementing
- 本段结论：待验证前提 1 由 `tests/test_ws_progress_watchdog.py::test_s5_segment_timeout_fails_only_that_task_and_keeps_server_alive` 支持：超时后慢推理返回，worker 子进程仍能处理后续任务；新 HTTP 集成复现已在 89a5192 上红，修复后通过。
- 关键决策与已否决方案：HTTP 成功落库 FAILED 后直接继续监控循环，复用 WS「只终结当前任务」策略；不杀死或重启仍可工作的 worker。
- 下一步唯一动作：完成 WS 终态 task_id 迟到帧准入前丢弃并验证。

## WS 终态 task_id 迟到帧隔离
- 当前阶段：implementing
- 本段结论：在 ws_recv 完成 task_id 解析后、请求校验与任务准入前丢弃终态 ID；本地集成复现覆盖 FAILED 后同 ID 的 5 秒迟到音频，基线重受理并红、修复后不增加活动任务且不进 worker 队列。
- 关键决策与已否决方案：终态集合保存在每条 ws_recv 连接内，并从仍在 state.tasks 的终态记录初始化；不扩展共享 ServerState。
- 下一步唯一动作：更新过时的 HTTP 段超时既有集成测试并完成全量验证。

## HTTP 子进程实际输入断言
- 当前阶段：implementing
- 本段结论：HTTP 超时测试现在检查识别子进程真实收到的序列化 Task，断言 owner_kind=http 且 socket_id 为空；缺少 ffmpeg 的环境明确 skip。
- 关键决策与已否决方案：复用现有 ManagedHttpServerHarness 的真实 multiprocessing Queue/worker 记录，不另建测试专用 producer。
- 下一步唯一动作：取得 tests/test_http_file_runner.py 范围申请 seq=1 决策后更新过时断言。

## HTTP 段超时既有断言更新
- 当前阶段：implementing
- 本段结论：按已批准的 seq=1 更新两处旧退出契约：HTTP 段超时仍可靠落库 FAILED[inference_timeout]，主服务保持存活并处理后续 HTTP Job；owner-release 探针继续验证 FAILED 持久化未成功前 owner 与运行闸门不释放。
- 关键决策与已否决方案：保留真实独立服务与标记文件阻塞的持久化探针；将假引擎延迟和段超时窗口设为可确保后续排队任务在期限内处理的值，不改其它测试。
- 下一步唯一动作：运行卡面窄测与全量测试，完成 scope 检查、提交并推送。
