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

## 里程碑 3：增量结果大小估算

- 当前阶段：implementing
- 本段结论：sink 对固定元数据序列化小骨架，并对文本、token 与 timestamp 的变化后缀增量计数；实际超过 64 MiB 仍以 `result_too_large` 失败。新隔离、顺序、上限与 backpressure 测试通过（34 passed）。
- 关键决策与已否决方案：大小计算按紧凑 UTF-8 JSON 的字符串转义、数组元素和逗号计数，保持与原序列化字节数等价；最终落库仍由 HttpStore 做其既有完整上限校验。
- 下一步唯一动作：运行全仓 `python -m pytest tests/ -q` 并处理本卡引入的失败。

## 里程碑 4：全量验证与范围阻塞

- 当前阶段：blocked
- 本段结论：定向测试曾通过 34 项；全量测试 553 passed、3 skipped、8 failed。两条 HTTP 生命周期 AST 断言仍要求旧的直接 await/确认结构，相关测试文件不在本卡范围，seq=1 扩权申请等待决策。
- 关键决策与已否决方案：不在 scope 批准前改 `tests/test_http_release_invariant.py`；全量测试中的 systemd/HOME 运行环境红与一次 worker-crash 红均因基线不可用而不能归为继承红，worker-crash 单测后续单跑通过。
- 下一步唯一动作：将已提交并推送的实现、完整测试状态与 scope 阻塞写入派发报告。
