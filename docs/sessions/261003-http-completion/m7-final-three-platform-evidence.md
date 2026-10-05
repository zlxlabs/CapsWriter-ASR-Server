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

## 7. 新 bootstrap 未测矩阵核验（2026-10-05，f705 → 本轮）

本节只记录本派发 `dlg-20261005-054600-e8f4a5` 的新增核验，运行源仍固定为
`492fe191e3f9568ea178b61970c732c9d37c4e29`；不把旧 Linux/Mac 采集或两套
`493 passed` 重新计入本轮，也不改写上面的历史结论。

- 私有上下文由拥有者权限 `0600` 的 Python 进程加载；target、prep 根和精确文件
  字段只作为原生参数/探针输入，未打印私有路径、主机、音频或参考正文。三条
  231 秒授权文件在 Windows 目标上的 `Path.Exists` 均为 false；没有拼接、重建、
  重识别或把相邻文件当替代。
- Windows 原生只读 SSH 连接返回成功；prep 根是目录，Python 可执行文件存在，
  `numpy`、`sherpa_onnx`、`soundfile` 导入初验均成功。精确的
  `successfulrun-windows.ps1` 与 `correction-161729-pointers.json` 不在该根；
  根下虽然有其他脚本名，但按续卡约束不把它们当成功路径 fallback。因此没有
  启动 Windows 服务、没有声称 Windows launcher/probe PID、PeakWorkingSet64、
  两协议或停止语义已测。
- WeNet/AISHELL fixture 的清单行由私有 Python 进程分别解码：data-list 167
  字节、wav.scp 99 字节、text 84 字节，data-list 与 text 的参考字段均为
  36 字节且逐字节一致，绑定校验成立；参考正文仍只落在私有 `0600` 文件。
  这证明材料绑定，不证明音频可消费。
- 对固定 revision `d17059667d6afe0680d19b3a4948ab825ef25105` 的唯一匿名 GET
  已落盘为私有 `0600` 文件，实际响应体 31 字节且不是 RIFF WAV；首次探针在
  未保存 HTTP 状态前解析失败，未重试、未补凭据。故没有真实 WAV、没有人工
  gold 消费、没有 CER，也没有从该失败响应派生 MP3/AAC/M4A/Opus。
- 因授权 231 秒文件和可消费 gold 都缺失，三平台 231 长样本、同源四 codec、
  可信质量基线及 explicit weaknet（真实服务首次失败、owner 新 SDK 进程
  offset 恢复）本轮均保持 `not run / blocked`；没有 synthetic listener、
  synthetic response、自动重试或伪造续传数据。新阶段结论仍为
  `partial / failed`，不能声称 M7Done。

## 8. 输入误述纠正后的续测（2026-10-05，本派发）

本节只追加 `dlg-20261005-061542-5da58f` 的新观测。运行源仍固定
`492fe191e3f9568ea178b61970c732c9d37c4e29`。不改写第 1–7 节当时的缺项结论，
也不把那些缺项回填成当时已测。未改 App/SDK/collector/tests/CI/config/Goal。

### 8.1 三个被误述的输入（已按纠正消费，不是缺 runner / 缺素材 / GET 失败）

- 所谓 `successfulrun-windows.ps1` 是描述词被拼成文件名。Linux 缓存里真实参考
  脚本与指针文件存在且可读；它们不是 Windows prep 根必须同名的前置。Windows
  prep 根已有 Python / numpy / sherpa_onnx / soundfile，本轮在 owned 新子目录
  用冻结源启动真实 `CapsWriterServer.start`，未把相邻 `win-step2.ps1` 当 runner。
- 授权 231 s 三条路径是 **Linux 源**（结构字段 `absolute_path`）。
  `full_x3.wav` 头为 RIFF，时长 231.552 s、7 409 742 字节；`full.wav`
  2 469 966 字节 / 77.184 s；`000_video.mp4` 18 974 961 字节。已拷到本轮
  Mac/Windows owned 目录，未在 Windows 上用 Linux 绝对路径判缺，未拼接、未全盘扫。
- WeNet 固定 revision `d17059667d6afe0680d19b3a4948ab825ef25105` 树上该 path
  为 git 符号链接（mode `120000`，31 字节）。沿官方树解析相对目标后一次 blob GET，
  目标 mode `100755`、137 036 字节、RIFF、16 kHz mono、4.281 s。参考字段 36 字节
  与绑定文本一致。未对匿名 URL 重试、未补 key。派生容器（Linux ffmpeg 实跑）：
  MP3 25 605、AAC 34 090、M4A 34 693、Opus 36 838 字节。

### 8.2 Linux（本轮新 231 / gold / 弱网；不重跑已有 77 s 四 case）

health：`492fe19` / protocol 2 / role server / paraformer / worker_alive。
Paraformer `num_threads` 消费值为 4，provider `cpu`；未把环境键存在写成 1 线程。
SDK CLI 真实发送。独立 ffmpeg 16 kHz mono f32le 与工具 PCM：231 s 均为
14 819 328 字节。

| 夹具 | 协议 | 墙钟秒 | token/ts | producer |
| --- | --- | ---: | ---: | --- |
| wav-03（231.552 s） | WS v2 | 9.340 | 340/340 | 17 文本帧；JSON UTF-8 5 897 076；Base64 5 893 328；解码 4 419 964；binary 0 |
| wav-03 | HTTP | 10.282 | 340/340 | 8 PATCH / 7 409 742 body；重发 0；job DONE |
| gold wav | WS / HTTP | 1.287 / 1.112 | 13/13 | CER 0.0；HTTP 1 PATCH / 137 036 |
| gold mp3 | WS / HTTP | 0.612 / 0.745 | 13/13 | CER 0.0；HTTP 1 PATCH / 25 605 |
| gold aac | WS / HTTP | 0.716 / 0.776 | 13/13 | CER 0.0；PCM 278 528（时长 4.352 s，与 wav 273 984/4.281 s 不同） |
| gold m4a | WS / HTTP | 0.616 / 0.766 | 13/13 | CER 0.0；PCM 274 432（时长 4.288 s） |
| gold opus | WS / HTTP | 0.656 / 0.781 | 13/13 | CER 0.0；PCM 与 wav 同 273 984 |

AAC/M4A 与 wav 的 PCM 字节不同，只记录，不声称波形相等。gold CER 0.0 是该条
官方人工稿相对本工具归一化公式的实测，**不是**语料「>95%」声明，也不是私有
77/231 的准确率（后者仍 `reference_status=not_provided`，CER unknown）。

`/proc` 同采样（各进程 VmHWM，不是同一时刻总峰）：主进程 115 660 kB，
Manager 35 248 kB，worker 927 820 kB。向已记录 launcher PID 发 SIGTERM 后
主进程与两子进程 `/proc` 均不在。只读重开 SQLite：`jobs` 7×DONE、
`uploads` 7×COMMITTED、`results` 7（231 HTTP + 五 gold HTTP + 弱网 resume 一单）。

弱网（owned loopback，首次 PATCH ACK 后切断第二次 PATCH）：第一次
`AsrError connection_lost`，recovery `confirmed_offset=1048576` /
`size_bytes=2469966`，无 job。owner 新 SDK 进程新 TCP：同 upload，后缀
1 421 390 字节，job DONE，token/ts 107/107，is_final，时长 77.184 s。
无自动重识别。

### 8.3 Mac（本轮 231 / gold / 弱网；不重跑已有 77 s 四 case）

health 同前。SIGTERM 退出码 0，进程 gone。本轮测量脚本未在该进程树上采样瞬时
RSS；不得把上一轮 77 s 四 case 的 RSS 记到本轮 231 进程。

| 夹具 | 协议 | 墙钟秒 | token/ts | producer |
| --- | --- | ---: | ---: | --- |
| wav-03 | WS v2 | 4.480 | 333/333 | 17 文本帧；binary 0；PCM 14 819 328 |
| wav-03 | HTTP | 4.376 | 333/333 | 8 PATCH / 7 409 742；重发 0；DONE |
| gold 五容器 × 两协议 | 均 ok | 0.27–0.47 | 13/13 | CER 0.0；AAC/M4A PCM 与 Linux 同差异 |

弱网：第一次 `connection_lost`，offset 1 048 576 / 2 469 966；resume 成功，
job DONE。token 计数见私有结果，公开只记 DONE + is_final。

跨平台 231 s token 数 Linux 340 / Mac 333 / Windows WS 333，只记录。

### 8.4 Windows（owned 新子目录真实服务）

health：`492fe19` / protocol 2 / role server / paraformer / worker_alive。
线程消费值 4。停止方式是 `CTRL_BREAK_EVENT`（进程组），原生退出码
`3221225786`（`STATUS_CONTROL_C_EXIT`），**不是** Unix `SIGTERM`。停止后
launcher PID 不存在。

PID 分列（CIM 子树）：launcher `11820`；其子 `7664`；`7664` 的子进程
`22184` 与 `17804`。`17804` 的 `PeakWorkingSet64` 为 929 652 736 字节；
同 PID 采样到的 `WorkingSet64` 最大约 337 305 600 字节。二者不是同一个量：
前者是 OS 峰，后者是采样瞬间。不以各进程 peak 相加冒充同时刻总峰。

| 夹具 | 协议 | 结果 |
| --- | --- | --- |
| wav-01 77.184 s | WS v2 | 5.953 s；105/105；6 文本帧；JSON 1 972 515；Base64 1 971 176；解码 1 478 370；binary 0 |
| wav-01 | HTTP | 失败。`AsrError integrity_mismatch`。recovery：UPLOADING，offset==size，无 job |
| mp4-01 | WS v2 | 5.875 s；104/104；11 文本帧；解码 2 713 118；binary 0 |
| mp4-01 | HTTP | 同上 `integrity_mismatch` |
| wav-03 | WS v2 | 15.328 s；333/333；17 文本帧；解码 4 419 962；PCM 14 819 328 |
| wav-03 | HTTP | 同上 `integrity_mismatch` |
| gold 五容器 | WS v2 | 均 ok；13/13；CER 0.0 |
| gold 五容器 | HTTP | 5 次均为 `integrity_mismatch`；offset==size；无 job |

HTTP 侧 8 次 create+PATCH 均走到 `confirmed_offset==size_bytes` 后 commit
失败，SQLite：`jobs` 0、`uploads` 8×UPLOADING、`results` 0。未把失败改成
自动重试或绕过核验。弱网第一次切断仍为声明内失败：`connection_lost`，
offset 1 048 576 / 2 469 966。owner 新进程 resume 后 commit 返回
`integrity_mismatch`，服务端报文为「源文件长度与声明不一致」；job 未
DONE。八次全量 HTTP 的 `integrity_mismatch` 未再拆分长度/SHA 子句，保持
未知，不以弱网那一条回填。

### 8.5 仍不能声称 M7Done

- Windows HTTP 文件任务在冻结 492fe 上未受理（无 job）。
- Windows 弱网 resume 没有拿到同 job DONE。
- 本轮 Mac 瞬时 RSS 未采。
- 私有 77/231 仍无人工稿，CER unknown。
- 不修 #72，不把 fresh fixture ID 写成修复。
