# PR82 原始 EOF 诊断进展

## 2026-10-06 · verifying

- 阶段：verifying；固定源码 `fce9131a256a7a8e26a48a0c0882b81444f9ee59`，运行前工作区洁净。
- 原收据核实为 503 tests / 55 failures / 24 errors / 3 skips；79 个失败/错误身份与节点索引逐项集合相等，异常消息类别为 69 EOFError、9 AssertionError、1 FileNotFoundError。
- 实测原 EOF 节点 1 passed；原模块整文件 24 passed。Manager PID 关联和错 PID 负控均通过，历史红未复现。
- 决策：不改生产、测试、harness、CI 或依赖；不把绿色复测说成根因修复/M7 完成；不以当前环境或 child 退出替历史红定因。原始 child stderr 与环境变量来源仍 unknown。
- 已否决：同一 fce 无新输入重复 full；按计数推断失败集合或因果；把被注入的 crash/timeout worker 退出解释成所选 EOF 节点的 child 首异常。
- 下一步：等三平台共同正式 SHA 与各平台真实环境收据齐备后做完整交付验证；若同一 EOF 重现，在 `running_runner_server` 的 Manager 创建、worker 启动/join 和 shutdown 边界采集 child 首次 stderr 与 parent EOF 阶段。
