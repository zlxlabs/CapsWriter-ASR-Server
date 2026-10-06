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
- 本轮更新命令：`pwsh -NoProfile -File .\deploy\update.ps1 -Ref cb74d8f2a333d231cbd7e36ccff8c305b4ab89b6 -Python python -TaskName CapsWriter-Server -Port 6016 -ModelType qwen_asr`，退出码 `0`。脚本最后一行：`更新完成：task=CapsWriter-Server model=qwen_asr port=6016 git_sha=cb74d8f`。完整 stdout/stderr 保存在开发机私有 cache。更新后 `/health`：`{"status":"ok","git_sha":"cb74d8f","model":"qwen_asr","worker_alive":true}`；TCP 7016 可连接。
- SDK 冒烟：开发机经 Windows 6800H HTTP 入口（7016）提交 3.14 秒 PCM16/16 kHz/单声道音频；submit/status/result 均退出 `0`，status 为 DONE 且 job 一致，结果文本 48 字符。精确命令见私有执行报告。

## 2. Mac Studio / capswriter-server / 6016

- 升级前 `/health`：`{"status":"ok","git_sha":"1d00130","model":"paraformer","worker_alive":true}`；磁盘 HEAD `1d00130c1cd1ad8717008adb9d95bd1c7f0a0ab7`；7016 无监听。
- 备份：`实例目录\ecosystem.config.cjs.bak-20261006-cb74`；SHA-256 `b2f458b29d23e8e0dcdb4af3225462e71bd3b67538543d85faac596a688f1987`。
- 配置新增 `CW_HTTP_PORT=7016`、`CW_HTTP_DATA_DIR=HTTP 数据目录（卡面约定值）`，保留 `CW_MAX_TASK_SECONDS=28800`；数据目录已创建。
- 更新命令：`DEPLOY_PYTHON="$PWD/venv/bin/python" CW_MODEL_TYPE=paraformer DEPLOY_PROCESS_NAME=capswriter-server DEPLOY_PORT=6016 ./deploy/update.sh cb74d8f2a333d231cbd7e36ccff8c305b4ab89b6`；退出码 `0`，最后输出 `更新完成：process=capswriter-server model=paraformer port=6016 git_sha=cb74d8f`。
- 环境重载：`pm2 startOrReload ecosystem.config.cjs --only capswriter-server --update-env`，退出码 `0`。
- 更新后 `/health`：`{"status":"ok","git_sha":"cb74d8f","model":"paraformer","worker_alive":true}`；PM2 online；7016 正在监听。
- SDK 冒烟（3.14 秒 PCM16/16 kHz/单声道）：submit `python -m capswriter_asr http submit "$CACHE/smoke-hello.wav" --url http://127.0.0.1:17016 --resume-file "$CACHE/studio-6016.resume.json"` 退出 `0`；SSH 本地转发 17016→Studio 7016。status `python -m capswriter_asr http status --url http://127.0.0.1:17016 --resume-file "$CACHE/studio-6016.resume.json"` 退出 `0`、DONE；result `python -m capswriter_asr http result --url http://127.0.0.1:17016 --resume-file "$CACHE/studio-6016.resume.json" --out-dir "$CACHE/results/studio-6016" --format txt` 退出 `0`，文本 47 字符。

## 3. Mac Studio / qwen-asr-server / 6017

- 升级前 `/health`：`{"status":"ok","git_sha":"1d00130","model":"qwen_asr_mlx","worker_alive":true}`；磁盘 HEAD `1d00130c1cd1ad8717008adb9d95bd1c7f0a0ab7`；7017 无监听；llama b10621 三个 macOS 动态库均存在。
- 备份：`实例目录\ecosystem.config.cjs.bak-20261006-cb74`；SHA-256 `4aceb59a007b5976cf4d563aea8f0b4153958ea96ebd44da9306d32188294adf`。
- 配置新增 `CW_HTTP_PORT=7017`、`CW_HTTP_DATA_DIR=HTTP 数据目录（卡面约定值）`，保留 `CW_MAX_TASK_SECONDS=28800`；数据目录已创建。
- 更新命令：`DEPLOY_PYTHON="$PWD/venv/bin/python" CW_MODEL_TYPE=qwen_asr_mlx DEPLOY_PROCESS_NAME=qwen-asr-server DEPLOY_PORT=6017 ./deploy/update.sh cb74d8f2a333d231cbd7e36ccff8c305b4ab89b6`；退出码 `0`，最后输出 `更新完成：process=qwen-asr-server model=qwen_asr_mlx port=6017 git_sha=cb74d8f`。
- 环境重载：`pm2 startOrReload ecosystem.config.cjs --only qwen-asr-server --update-env`，退出码 `0`。
- 更新后 `/health`：`{"status":"ok","git_sha":"cb74d8f","model":"qwen_asr_mlx","worker_alive":true}`；PM2 online；7017 正在监听。
- SDK 冒烟（3.14 秒 PCM16/16 kHz/单声道）：submit `python -m capswriter_asr http submit "$CACHE/smoke-hello.wav" --url http://127.0.0.1:17017 --resume-file "$CACHE/studio-6017.resume.json"` 退出 `0`；SSH 本地转发 17017→Studio 7017。status `python -m capswriter_asr http status --url http://127.0.0.1:17017 --resume-file "$CACHE/studio-6017.resume.json"` 三次退出均 `0`，RUNNING、RUNNING、DONE 且 job 一致；result `python -m capswriter_asr http result --url http://127.0.0.1:17017 --resume-file "$CACHE/studio-6017.resume.json" --out-dir "$CACHE/results/studio-6017" --format txt` 退出 `0`，文本 48 字符。

## 4. Mac Studio / capswriter-proxy / 6020

- 升级前磁盘 HEAD `6b7a2b82fbc3ebe862250a8804902e5bf37f9211`；`/health`：`{"status":"ok","git_sha":"6b7a2b8","model":null,"worker_alive":null}`；PM2 online。
- 升级前 `/status`：3 个后端，2 个健康的 v2 后端 SHA 为 cb74d8f，另 1 个 v1 后端不健康且无 SHA；活动任务数 0。
- 更新命令：`DEPLOY_PYTHON="$PWD/.venv/bin/python" CW_MODEL_TYPE=proxy DEPLOY_PROCESS_NAME=capswriter-proxy DEPLOY_PORT=6020 ./deploy/update.sh cb74d8f2a333d231cbd7e36ccff8c305b4ab89b6`；退出码 `0`，最后输出 `更新完成：process=capswriter-proxy model=proxy port=6020 git_sha=cb74d8f`。无配置改动。
- 更新后 `/health`：`{"status":"ok","git_sha":"cb74d8f","model":null,"worker_alive":null}`；PM2 online。
- 更新后 `/status`：2 个健康 v2 后端均为 cb74d8f，1 个原有 v1 后端仍不健康且无 SHA；活动任务数 0。

## Mac mini（只读）

- 仅运行一次 `pm2 status qwen-asr-server`，退出码 `0`；PM2 表格无进程行，未找到该名称（不存在）。未更改 Mac mini。

## 结果与偏差

原生 PowerShell 5.1 缺少更新脚本使用的 `-SkipHttpErrorCheck` 参数，切换 PowerShell 7 后 Windows 6016 更新成功。四个目标实例均为 cb74，两个 ASR HTTP 入口均完成 SDK submit→status→result，结果文本非空。proxy `/status` 有 2 个健康 v2 后端（cb74）和 1 个原有不健康 v1 后端。Mac mini 未注册 qwen-asr-server。

## 收尾

### 踩到的坑

原生 PowerShell 5.1 不支持更新脚本传入的 `-SkipHttpErrorCheck`，解释了此前“脚本返回 1、服务却已启动”的表象；用 PowerShell 7 重跑后退出码 0 且健康检查通过。

### 闸与绕过

无闸绕过。遵守脚本非零触发回滚并停止的硬约束。

### 与卡面的偏差

首次 Windows 调用非零后按卡回滚；取得 PowerShell 7 修正授权后重部署成功。proxy 状态中原有 v1 后端仍不健康，两个 cb74 v2 后端在线；未升级 Mac mini。仓内仅本证据文档。

### 最贵的一步

Windows PowerShell 5.1/7 兼容性诊断与回滚、Studio 两个 ASR 环境重载，以及 qwen_asr_mlx 文件任务完成前三次状态查询后领取结果。
