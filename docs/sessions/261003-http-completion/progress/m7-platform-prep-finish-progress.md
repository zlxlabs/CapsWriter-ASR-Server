# M7 三平台环境补齐 — 进度

会话文档：`docs/sessions/261003-http-completion/m7-platform-prep-finish.md`。
准备固定源：`e117f0249b2cd503308fa1d682a72dcc6949b432`（不是最终 server SHA）。

## 里程碑 1：现场与前序

- 阶段：implementing
- 本段结论：独立 worktree，分支 `card/http-m7-platform-prep-finish-261004`，HEAD 即 e117，工作区干净。无交接单。本派发 systemd unit 是自己的现场，不构成他人占树。前序独立验收：Linux 解码可用；MacMini 默认 PATH 无 FFmpeg；Windows 一次空输出探针。权重 Linux/Mac 已同哈希。不触 #62/#64/#71，不跑 77s ASR。
- 关键决策与否决：否决把本卡当 #62/#64 门禁；否决 blind retry Windows；否决全盘搜 FFmpeg / 改全局 PATH / 动原服务。
- 下一步：量隔离根、补 MacMini 任务 PATH、Windows 分阶段 SSH、同一份生产者字节。

## 里程碑 2：三台真实消费

- 阶段：implementing
- 本段结论：
  - 生产者 WAV SHA `d37adedb…04e7ec20`，三台消费者读到同一 source SHA。
  - Linux / MacMini / Windows 均跑通 e117 `FileSourceDecoder`，argv 安全枚举一致，加载函数 SHA 一致，PCM 4000×float32，NaN/Inf=0。
  - Linux 与 Windows PCM 全哈希相同；MacMini 差 1 ULP（`maxAbsDiff=4.47e-08`），记 unknown，不升 P1。
  - 对照：正确 GREEN；零 PCM RED；错误 source SHA RED。`teeth_ok=true`。
  - MacMini：`/opt/homebrew/bin/ffmpeg` 8.1.2 存在，仅任务子进程 PATH 使用。Windows SSH `command_exec` rc=0；隔离 venv 3.12.12；原计划任务始终 Running。
  - 三台权重 size/hash 一致且非空。Linux `uv pip check` rc=0；MacMini/Windows 用已装发行版 metadata，不重建环境。
- 关键决策与否决：否决为 MacMini 全局装 FFmpeg；否决无条件重传权重（三台已有且哈希已核）；否决用 POSIX 模式代替 Windows ACL。
- 下一步：两份公开文档落盘，native git 提交推送，不开 PR。

## 里程碑 3：文档与 git

- 阶段：verifying
- 本段结论：只改本卡两份文档。Verify：`git diff --check HEAD^ HEAD`。平台状态 Linux/MacMini/Windows 对同输入 decoder 均为 **ready**；模型质量 **未完成**。私有归档留在既有隔离根，无新长期 worktree / systemd / 跨天部署引用。
- 关键决策与否决：否决开 PR/ready/merge；否决把 e117 写成最终运行 SHA。
- 下一步：交主脑；质量测量另派，且须最终合并 SHA。

## 平台状态（本卡终态）

| 平台 | 同输入 decoder | 缺项 |
|---|---|---|
| Linux | ready | 无（质量测量另计） |
| MacMini | ready | 默认 PATH 仍无 ffmpeg（任务 PATH 已显式用已知根）；原 pm2 PID unknown |
| Windows | ready | 无（质量测量另计） |

总体：**decoder 准备可前进；ready-for-measurement = 否。**
