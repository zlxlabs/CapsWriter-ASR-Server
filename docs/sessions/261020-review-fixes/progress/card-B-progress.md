## 里程碑 1：WS 结果分发与隔离测试

- 当前阶段：implementing
- 本段结论：已在 base `89a5192` 上确认阻塞 sink 的 WS 实时结果测试断言失败，修复后新测试通过。同一 HTTP Job 的结果通过独立 FIFO 队列串行调用 sink。
- 关键决策与已否决方案：每个 Job 的消费者注册表只存在于唯一 `ws_send` 协程的局部状态，不改 `http_server.py` 装配；消费者异常由 sender 轮询并上抛，停止时取消并回收消费者。
- 下一步唯一动作：实现并验证 HttpResultSink 对累计结果大小的增量估算。

## 里程碑 2：隔离期间保留 HTTP 段背压

- 当前阶段：implementing
- 本段结论：HTTP 消费者在 sink 前确认本段；阻塞 sink 时只释放当前一个在途名额，后续结果仍留在有界的 worker 在途窗口内，WS 分发不受阻。
- 关键决策与已否决方案：不在 ws_send 投递时提前确认所有 HTTP 段，避免 sink 慢时失去原有在途段背压并无限积累结果。
- 下一步唯一动作：完成 HttpResultSink 累计结果大小的增量估算及上限语义验证。
