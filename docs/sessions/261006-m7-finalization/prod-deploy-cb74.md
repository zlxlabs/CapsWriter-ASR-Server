# 生产部署证据：cb74d8f 与 HTTP 文件入口

执行日期：2026-10-06。目标 ref：`cb74d8f2a333d231cbd7e36ccff8c305b4ab89b6`。

## 1. AMD 6800H Windows / CapsWriter-Server / 6016

- 升级前 `/health` 白名单字段：`{"status":"ok","git_sha":"6b7a2b8","model":"qwen_asr","worker_alive":true}`。
- 升级前磁盘 HEAD：`6b7a2b82fbc3ebe862250a8804902e5bf37f9211`。
- 端口检查：7016 无监听；llama b10621 的 `ggml.dll`、`ggml-base.dll`、`llama.dll` 均已存在。
- 配置备份：`实例目录\run_server.bat.bak-20261006-cb74`；备份 SHA-256 `B073E99D70FCAA5115ECF997A4E7C4F9AEE8CDB8BAA8A436DAFB8B03896D6127`。
- 曾新增 `CW_HTTP_PORT=7016`、`CW_HTTP_DATA_DIR`（HTTP 数据目录采用卡面约定值），并创建该数据目录；升级失败后按备份原样恢复了 `run_server.bat`。备份保留。
- 更新命令（仓库目录内）：`.\deploy\update.ps1 -Ref cb74d8f2a333d231cbd7e36ccff8c305b4ab89b6 -Python python -TaskName CapsWriter-Server -Port 6016 -ModelType qwen_asr`；SSH/PowerShell 进程退出码：`1`。
- 退出码为 1 时观测到 `/health`：`{"status":"ok","git_sha":"cb74d8f","model":"qwen_asr","worker_alive":true}`。依卡面规定，脚本非零即回滚并停止，不以健康端点覆盖退出码。
- 回滚命令（仓库目录内）：`.\deploy\update.ps1 -Ref 6b7a2b82fbc3ebe862250a8804902e5bf37f9211 -Python python -TaskName CapsWriter-Server -Port 6016 -ModelType qwen_asr`；SSH/PowerShell 进程退出码：`1`。回滚后磁盘 HEAD 为 `6b7a2b82fbc3ebe862250a8804902e5bf37f9211`，配置与备份 SHA-256 相同。
- 回滚后 `/health` 白名单字段：`{"status":"ok","git_sha":"6b7a2b8","model":"qwen_asr","worker_alive":true}`；计划任务为 Running，7016 无监听。
- HTTP 冒烟未执行；按失败即停止规则，不再升级 Mac Studio、proxy 或进行后续冒烟。

## 结果与偏差

部署未完成，需由主脑调查 PowerShell/更新脚本返回码 1 的原因后重新派发。虽升级后与回滚后健康端点分别显示目标版和原版，两个更新脚本调用均返回非零，因此按卡面执行了回滚并停止。Studio 三个实例、proxy、Mac mini 的状态均未查询或更改；Mac mini 的一次只读 pm2 查询也因停止规则未执行。

## 收尾

### 踩到的坑

PowerShell 远程调用两次均返回退出码 1，尽管升级后与回滚后的 `/health` 分别报告预期版本；不能只看健康端点忽略脚本非零。

### 闸与绕过

无闸绕过。遵守脚本非零触发回滚并停止的硬约束。

### 与卡面的偏差

只处理 Windows 6016 并完成回滚；其余实例、Mac mini 查询及三次 HTTP SDK 冒烟均未执行。仓内只新增本证据文档。

### 最贵的一步

Windows 更新与回滚各运行一次仓内 `deploy/update.ps1`，并分别确认白名单 `/health` 与回滚配置校验。
