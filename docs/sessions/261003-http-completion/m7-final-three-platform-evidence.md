# M7 最终同 SHA 三平台真实服务证据

记录日期：2026-10-05（UTC+8）。冻结源 `492fe191e3f9568ea178b61970c732c9d37c4e29`。
**本轮结论：partial / 不能声称 M7Done。** Linux 与 Mac Apple Silicon 已用真实 `CapsWriterServer.start`、真实 Paraformer/Punct、仓库 SDK CLI 跑完私有短素材的 HTTP 与默认 WS v2；Windows 因 prep 脚本未留下可解析 SSH Host 别名未开机；可信独立人工参考未取得，不做质量评分；231.552 秒素材在已授权父目录未找到。

旧 Linux 首测、cpu-model-smoke、platform-prep 与亲报告不改写。#72 仍 OPEN。

## 1. 源与权重身份

- 本轮新独立目录消费 `git archive` 与可 `rev-parse` 的 492fe checkout，不是 33 轮 `3d7436c` 快照。
- 13 个运行模块（`start_server.py`、`config_server.py`、`core.server.app` / `state` / `http_server` / `http_store` / `http_file_runner` / `process_manager` / `server_manager` / `engines.factory`、SDK `client` / `http_client`、`scripts/_baseline_http_ws.py`）archive 与 checkout 字节 SHA-256 一致。
- archive tar 10 168 320 字节；远端自包含 shallow checkout tar 11 366 400 字节。health 短 SHA `492fe19`，是冻结 40 位前缀。
- 权重只读引用既有隔离 cache，公开只记名称与大小：Paraformer `model.onnx` 243 371 218、`tokens.txt` 84 160；Punct `model.onnx` 294 372 519、`tokens.json` 4 207 480。未重装、未新 GPU。

## 2. 服务启动契约（Linux / Mac）

每机独立 settings 对象：`CW_ADDR=127.0.0.1`、自选高位 `CW_PORT` / `CW_HTTP_PORT`（非 0）、自有 `CW_HTTP_DATA_DIR`、`CW_MODEL_TYPE=paraformer`、`CW_ONNX_PROVIDER=CPU`、一层线程。子进程环境 16 个白名单键，未 `source .env`。未改公共 Config 源码，未碰原生产 cwd / systemd / 计划任务。

| 平台 | health | git_sha | 模型 | worker | 协议/角色 |
| --- | --- | --- | --- | --- | --- |
| Linux | ok | `492fe19` | paraformer | true | 2 / server |
| Mac arm64 | ok | `492fe19` | paraformer | true | 2 / server |

Windows：prep `ssh_classify.py` 把非 `mac-mini` 的主机标成 `windows-known-host`；该字符串不是可解析 SSH Host。`run-mac.sh` / `run-windows.ps1` 只有远端私有路径，没有 Host 别名。未扫描网络、未读 profile。Windows 本轮 **未启动服务**。

## 3. 私有短素材物理测量

匿名 `private-wav-01` / `private-mp4-01` 均为 77.184 秒；源字节 2 469 966 / 18 974 961。独立 FFmpeg `16 kHz mono f32le` 与工具解码 PCM 均为 4 939 776 字节。未使用 SoundFile 原立体声 buffer 当归一化分母。231.552 秒三倍 WAV 在已授权父目录按 7 409 708 字节未找到，本轮不测、不拼接。

仓库 SDK CLI `scripts/_baseline_http_ws.py` 真实发送。WS 为文本 JSON + Base64，二进制帧 0。HTTP create 控制 JSON + PATCH 源字节一次、重发 0；完成态 SQLite `DONE`。fresh fixture ID，结果 0600。无自动重识别。

### Linux（Python 3.12.3，SDK 0.1.0，httpx 0.28.1，websockets 15.0.1，FFmpeg 6.1.1）

| 夹具 | 协议 | 墙钟秒 | token/ts | 应用层 producer |
| --- | --- | ---: | ---: | --- |
| wav-01 | WS v2 | 3.032 | 107/107 | 6 文本帧；JSON UTF-8 1 972 515；Base64 1 971 176；解码 1 478 372；binary 0 |
| wav-01 | HTTP | 3.904 | 107/107 | 控制 JSON 200；3 PATCH / 2 469 966 body；请求 20；重发 0；job DONE |
| mp4-01 | WS v2 | 3.509 | 104/104 | 11 文本帧；JSON UTF-8 3 619 954；Base64 3 617 520；解码 2 713 120；binary 0 |
| mp4-01 | HTTP | 3.845 | 123/123 | 控制 JSON 201；19 PATCH / 18 974 961 body；请求 36；重发 0；job DONE |

Linux `/proc`：worker `VmHWM` 926 512 kB，主进程 113 248 kB，Manager 35 232 kB（各进程峰值，不是同一时刻总峰）。测量结束后同采样 RSS 合计 860 192 kB。worker CPU `utime+stime` 50.27 s（`clk_tck=100`），主进程 1.61 s。TERM 后主进程与两子进程 `/proc` 均不在；只读重开 SQLite：`jobs` 2×DONE、`uploads` 2×COMMITTED、`results` 2，无再次模型处理。

### Mac Apple Silicon（prep 私有 CPython 3.12.15 / 既有 venv；FFmpeg 为 prep 私有入口）

| 夹具 | 协议 | 墙钟秒 | token/ts | 应用层 producer |
| --- | --- | ---: | ---: | --- |
| wav-01 | WS v2 | 1.725 | 99/99 | 6 文本帧；JSON UTF-8 1 972 509；Base64 1 971 176；解码 1 478 370；binary 0 |
| wav-01 | HTTP | 1.547 | 99/99 | 控制 JSON 200；3 PATCH / 2 469 966；请求 12；重发 0；DONE |
| mp4-01 | WS v2 | 1.646 | 98/98 | 11 文本帧；JSON UTF-8 3 619 954；Base64 3 617 520；解码 2 713 119；binary 0 |
| mp4-01 | HTTP | 1.941 | 98/98 | 控制 JSON 201；19 PATCH / 18 974 961；请求 29；重发 0；DONE |

Mac `ps` RSS（测量结束瞬时，**不是** `ru_maxrss` / 全时峰）：主进程 133 888 KiB，resource_tracker 9 376，Manager 30 432，worker 866 336 KiB。TERM 退出码 0。跨平台 PCM 样本数/时长一致，WS 解码字节与 Linux 差 2，符合既有「不同 ffmpeg 构建」观察，不声称波形相等。token 数也与 Linux 不同，只记录，不评协议优劣。

## 4. 可信参考与 Goal 7 派生

三个已公开候选资料源（Common Voice HF datasets-server / Mozilla clips API；OpenSLR 33 `resource_aishell.tgz` 1 246 920 字节，仅 lexicon+speaker.info；WeNet `test_wavs` 与具名 AISHELL wav）均未得到「官方人工标注文本 + 对应音频」绑定。HF 出现 401/404，未使用任何 key。私有 77 s 素材未经人核，`reference_status=not_provided`，无 CER。因此 **无质量基线、无 MP3/AAC/M4A/Opus 公开 human 派生 fixture**。不把模型输出当 gold。

## 5. 组合源 CI（本工作树 HEAD=492fe）

共享锁 `~/.cache/caps-http-261005-fullsuite.lock`，`flock --timeout 600` + `timeout 900`，一 suite 一 release。排队与执行分开：本轮锁等待可忽略（两套墙钟 263 s + 254 s，总进程 517 s）。栈：Python 3.12.3、pytest 9.1.1、pytest-asyncio 1.4.0、aiohttp 3.14.3、httpx 0.28.1。

| 套件 | 结果 | 耗时 | skip |
| --- | --- | ---: | --- |
| `websockets==15.0.1` | 493 passed, 3 skipped, 163 warnings | 261.69 s | aligner:53、aligner:62、segmenter:208 |
| 未 pin `websockets`（uv 实际解析 17.2） | 493 passed, 3 skipped, 163 warnings | 252.52 s | 同上三个资源 skip |

三 skip 均为既有资源缺失，无 HTTP decode skip。不借用 b65 的 487 主张 493。本数是 492fe 工作树真实消费。

## 6. 未完成 / 失败项

- 不能声称 M7Done：缺可信 gold；Windows 真实服务未跑。
- 231.552 s 素材缺失。
- Windows PeakWorkingSet64 / launcher 与 probe PID 分列未测。
- 弱网手工 reconnect 未做（Goal 仅要求显式弱网时才做）。
- #72 recovery 落盘顺序不修；fresh ID 不是修复。
- 派发时主干 CI 基线 `gh api` 不可用，继承红未能判定。
