
## 1. 代码初审（冻结 SHA 45c0c2c）
- 按先读的协议与 guide 对照：`status=ok` 是采集/落盘状态；token/timestamp 计量字段不构成识别质量判定；HTTP source、PCM、WS FLAC Base64 JSON 口径在文案中分开。
- 初审了本轮新增的 guide、collector、producer fixture 与测试；冻结增量内没有服务实现或 SDK 改动。
- 初步未见把空 timestamps 的单调结果当作覆盖，或把非单调/越界指标升级为 quality pass 的代码路径。
- 待外证核实的候选：成功后复用同 fixture ID 可能撞独占私有 JSON；fixture 形态目前未单独写 SDK package version。均暂列 P2 候选，不改实现。
- 下一步：独立跑真实 CLI/网络消费、CI 对照和断言反向变异，再收口定级。
