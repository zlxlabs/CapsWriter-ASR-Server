# M7 三平台环境补齐（准备固定源 e117）

任务卡：`m7-platform-prep-finish`。准备固定源是 `e117f0249b2cd503308fa1d682a72dcc6949b432`（已含 SDK #70）。**e117 只是准备用的代码固定源，不是最终服务端运行 SHA，不能当模型质量完成。** 本卡不跑 77 秒真实 ASR、不加载识别权重、不做 CER、不全量 pytest、不审新模型、不等待 PR #62 / #64 合并、不把本环境准备当代其门禁。#71 未碰。

结论先说：**Linux / MacMini / Windows 三台私有隔离环境都具备「同一份合成 WAV → e117 `FileSourceDecoder` → 16 kHz mono float32」的真实消费能力（ready）。** 模型质量测量仍未做，三平台 **不是** ready-for-measurement。某台 blocked 不会再卡另外两台；本卡没有出现 blocked。

## 1. 生产者（一份字节，三台同 SHA）

私有 stdlib `wave` + `struct` 脚本生成确定 0.25 s / 48 kHz / mono / 16-bit 正弦 WAV（≤1 MiB），子进程 argv 为 `producer.py` + 输出文件名；环境白名单只记 `PATH` 元素个数。该文件复制到各已访问的隔离根后，三台消费者读取到的 source SHA-256 均为：

`d37adedba974df02b9a9105be9d0c5d5e55ad2f45ae0fc9b8954492804e7ec20`（24044 字节）。

合同比对读的是消费者实际打开的文件哈希，不是两边手写同一个期望值。负例：同长度全零 PCM 比对为 **RED**；把 source SHA 换成 64 个 `0` 比对为 **RED_wrong_source_sha**；正确消费者为 **GREEN**。私有 `contrast.py` 记录 `teeth_ok=true`。

此前 Linux / Mac 各自生成过 WAV，source SHA 不同；**不能**把那次差异归因于 FFmpeg 版本。本卡用的是新的同一份生产者字节。

## 2. 消费者（真实 argv / 加载源 / PCM）

三台都用 e117 的 `FileSourceDecoder`（`inspect.getsource` SHA-256 均为 `a8b9bd03…846eb634`），不初始化模型。实际 argv 安全枚举均为：

`<ffmpeg-bin> -nostdin -hide_banner -loglevel error -i <source> -ar 16000 -ac 1 -f f32le pipe:1`

FFmpeg 只出现在本任务子进程 `PATH`（或隔离根 `bin`），未改用户全局 `PATH`、未改原服务。

| 平台 | 解码器 Python | 任务 PATH 中的 FFmpeg | PCM 字节 / float32 | PCM SHA-256 | NaN/Inf | maxabs |
|---|---|---|---|---|---|---|
| Linux | 3.12.3 | 7.0.2-static（隔离根 binary） | 16000 / 4000 | `6d04345a…e7580bea` | 0/0 | 0.2499646246433258 |
| MacMini | 3.12.15 | 8.1.2（已知安装根命中，默认 SSH PATH 无此命令） | 16000 / 4000 | `b5f74804…8ba327fb` | 0/0 | 0.2499646246433258 |
| Windows | 3.12.12（隔离 venv） | 7.1 essentials（隔离根 binary） | 16000 / 4000 | `6d04345a…e7580bea` | 0/0 | 0.2499646246433258 |

跨平台：Linux 与 Windows PCM **全哈希相同**，`maxAbsDiff=0`。MacMini 与二者全哈希不同，同长度 4000 样本的 `maxAbsDiff=4.470348358154297e-08`（约 1 ULP）。输入字节、解码器函数 SHA、argv 标志一致，FFmpeg 构建不同；**无法再分解成纯构建差或纯数值差，记 unknown，不把「全哈希必须一致」写成应用 P1，不用字幕/模型输出当金标准。**

MacMini 前序失败只证明默认消费 PATH 没有 `ffmpeg`，不证明二进制不存在：已知根 `/opt/homebrew/bin/ffmpeg` 可执行（符号链接，模式 0755）。Windows 前序一次探针 rc=1 且 stdout/stderr 均为 0 字节，**不证明离线**；本次单次有界 SSH 分类为 `command_exec`，rc=0。

## 3. 依赖与权重（非空值 + 真实消费，不只键存在）

| 检查 | Linux | MacMini | Windows |
|---|---|---|---|
| 同输入 decoder | ready | ready | ready |
| `uv pip check` | rc=0（隔离 venv） | 无 uv/pip，未为拼命令重建环境 | 无 uv；用 venv 的 `importlib.metadata` |
| 包元信息（非空版本） | 与下列一致（venv 实装） | numpy 2.5.3 / httpx 0.28.1（requires 12 条）/ websockets 15.0.1 / onnxruntime 1.30.0（requires 6）/ sherpa-onnx 1.13.8（requires 1） | 同左 |
| backend + SDK 模块 | e117 工作树导入 ok | 隔离快照树导入 ok；本卡解码走 e117 源副本 | 同 MacMini |
| Paraformer `model.onnx` | 243371218 字节，`f36a0433…4475945` | 同左 | 同左 |
| Punct `model.onnx` | 294372519 字节，`e93593a6…2c44bd` | 同左 | 同左 |

权重只核 size/hash/非空，**未加载**。隔离代码快照目录名仍是旧提交 `820c3a2`，只证明模块能导入；测量解码器用的是 e117 源。最终合并后的 server SHA 仍缺，质量测量不能开始。

权限：Linux / MacMini 隔离根 POSIX 0700、属主为当前用户。Windows 不报 POSIX 模式；对该用户专属根做真实 ACL：Allow ACE 3、Deny ACE 0，权利种类 FullControl 计数 3（匿名计数，无 SID/账户名）。

## 4. 原服务与未做项

- Windows 已知计划任务 `CapsWriter-Server`：消费前 `Running`，消费后仍 `Running`。未覆盖、未重启、未杀。
- MacMini 非交互 PATH 上没有 pm2；已知 brew 根上 `pm2 pid` 为空，原进程 PID 记 unknown。未读原服务日志、未改 pm2。
- Linux 工作机不在授权生产 ASR 清单里；未对生产单元做启动/停止。本派发 user unit 仍是本任务自己的现场。
- 未扫网、未猜主机、未读 profile/settings/.env/凭据/session，未追 CLI 令牌。
- 未改共享 Git 配置、未全机 freeze、未开 PR、未标 ready、未合并、未写验收账。

负责人后续（本卡不代替）：

1. 质量测量要等最终合并代码与工具 SHA，再跑真实 ASR / CER；本卡明确 **未完成模型质量**。
2. PR #62 / #64 规范问题正文与主审失败不在本卡范围。
3. MacMini 原 pm2 进程 PID 若需要运维核对，由负责人在交互会话 PATH 下查，不作为 decoder ready 的前置。
4. MacMini 与 Linux/Windows 的 1 ULP PCM 差保持 unknown，测量脚本不要用跨构建全哈希当通过条件。

私有归档（隔离根，不进 git）含 manifest 元哈希、安全 JSON、可复现命令指针；不含原日志、完整环境、脚本里的敏感值。
