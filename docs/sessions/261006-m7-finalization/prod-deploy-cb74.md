# 生产部署证据：cb74d8f 与 HTTP 文件入口

执行日期：2026-10-06。目标 ref：`cb74d8f2a333d231cbd7e36ccff8c305b4ab89b6`。

## 1. AMD 6800H Windows / CapsWriter-Server / 6016

- 升级前 `/health` 白名单字段：`{"status":"ok","git_sha":"6b7a2b8","model":"qwen_asr","worker_alive":true}`。
- 升级前磁盘 HEAD：`6b7a2b82fbc3ebe862250a8804902e5bf37f9211`。
- 端口检查：7016 无监听；llama b10621 的 `ggml.dll`、`ggml-base.dll`、`llama.dll` 均已存在。
- 配置备份：`实例目录\run_server.bat.bak-20261006-cb74`；备份 SHA-256 `B073E99D70FCAA5115ECF997A4E7C4F9AEE8CDB8BAA8A436DAFB8B03896D6127`。
- 配置：`CW_HTTP_PORT=7016`、`CW_HTTP_DATA_DIR=HTTP 数据目录（卡面约定值）`；当前已重新配置并创建目录。首次失败后曾恢复备份，再按本轮要求重加变量；原备份保留且未覆盖。
- 原生 PowerShell 首次调用 `deploy/update.ps1 -Ref cb74d8f2a333d231cbd7e36ccff8c305b4ab89b6 -Python python -TaskName CapsWriter-Server -Port 6016 -ModelType qwen_asr` 退出码 `1`；退出时 `/health` 已为目标 SHA，按卡回滚。
- 诊断证据：原生 `powershell.exe` 版本 `5.1.22621.3672`，`Invoke-WebRequest.Parameters.ContainsKey("SkipHttpErrorCheck")` 为 `False`；PowerShell 7 为 `7.6.0`。原生 5.1 首次调用退出码 `1` 时 `/health` 为 `{"status":"ok","git_sha":"cb74d8f","model":"qwen_asr","worker_alive":true}`，仍按卡面回滚。
- 首次回滚命令 `deploy/update.ps1 -Ref 6b7a2b82fbc3ebe862250a8804902e5bf37f9211 -Python python -TaskName CapsWriter-Server -Port 6016 -ModelType qwen_asr` 退出码 `1`；回滚后磁盘 HEAD 为 `6b7a2b82fbc3ebe862250a8804902e5bf37f9211`，配置与备份 SHA-256 相同。
- 首次回滚后 `/health`：`{"status":"ok","git_sha":"6b7a2b8","model":"qwen_asr","worker_alive":true}`；计划任务 Running，7016 无监听。
- 本轮更新命令：`pwsh -NoProfile -File .\deploy\update.ps1 -Ref cb74d8f2a333d231cbd7e36ccff8c305b4ab89b6 -Python python -TaskName CapsWriter-Server -Port 6016 -ModelType qwen_asr`，退出码 `0`。脚本最后一行：`更新完成：task=CapsWriter-Server model=qwen_asr port=6016 git_sha=cb74d8f`。完整 stdout/stderr 保存在开发机私有 cache。更新后 `/health`：`{"status":"ok","git_sha":"cb74d8f","model":"qwen_asr","worker_alive":true}`；TCP 7016 可连接。SDK 冒烟待全部实例升级后执行。

## 结果与偏差

原生 PowerShell 5.1 缺少更新脚本使用的 `-SkipHttpErrorCheck` 参数，实测此参数不存在；切换为用户指定的 PowerShell 7 后更新脚本退出码为 0、目标健康字段通过。Windows 6016 当前已升级并开启 HTTP。接下来继续按卡顺序部署 Studio 6016、Studio 6017、proxy，再只读查询 Mac mini 并进行 HTTP 冒烟。

## 收尾

### 踩到的坑

原生 PowerShell 5.1 不支持更新脚本传入的 `-SkipHttpErrorCheck`，解释了此前“脚本返回 1、服务却已启动”的表象；用 PowerShell 7 重跑后退出码 0 且健康检查通过。

### 闸与绕过

无闸绕过。遵守脚本非零触发回滚并停止的硬约束。

### 与卡面的偏差

先按失败规则回滚；取得 PowerShell 7 修正授权后从 Windows 6016 重新部署成功。目前其他实例、Mac mini 查询及 HTTP SDK 冒烟待执行。仓内仅本证据文档。

### 最贵的一步

Windows 的 PowerShell 兼容性诊断、按要求回滚，以及使用 PowerShell 7 成功重新部署并验证健康状态。
