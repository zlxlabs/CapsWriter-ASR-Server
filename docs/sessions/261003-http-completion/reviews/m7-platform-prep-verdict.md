<!-- delegate-outcome: succeeded -->
# M7 平台准备产物独立验收

failure-visibility: p2-only

**结论：未通过，当前不能标记为就绪。** 本次只核验准备产物、实际依赖、真实音频解码消费者、权限和日志事件；不做 M7 功能代码冷审，也不加载模型或运行识别。

## 验收四问

1. **准备产物可否就绪？** 否。macOS 的真实解码消费者在当前环境找不到 FFmpeg；两个新环境的 `pip check` 都因环境内没有 `pip` 模块而退出；Windows 环境与 ACL 未能核验。已核对的权重文件只覆盖 Linux 源端与 macOS 目标端。
2. **哪些事实已独立核实？** Linux 与 macOS 的 Python 3.12 导入均通过；Linux 源端与 macOS 目标端的两份权重逐字节同 SHA；Linux 的 `FileSourceDecoder` 实际调用参数与构造参数一致，并成功解出同一份 0.25 秒输入。
3. **是否确认凭据外泄或应用 P1？** 没有在已存在的派发日志中发现凭据型记录；日志之外的模型会话记录不可由 envelope 指定，因此是否进入执行器平台上下文仍未知。已确认的事项属于操作与取证状态，不构成应用代码 P1。
4. **还缺什么才能复核就绪？** Windows 的同输入解码、依赖与 ACL 负例；macOS 可用 FFmpeg 后的 PCM 对齐；环境内可运行的依赖一致性检查；凭据事件由负责人决定是否撤销或轮换。不得把这些未完成项写成“已安全”。

## 实测指纹

- 检查的代码快照来自标记为 `820c3a2` 的归档，不等于最终运行版本 SHA；未加载权重，未验证 ASR 质量。
- 两份权重在 Linux 源端和 macOS 目标端均为实际文件，四份文件逐一匹配：
  - `Paraformer/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx/model.onnx`：243,371,218 字节，SHA-256 `f36a0433bcf096bd6d6f11b80a3ac8bed110bdca632fe0d731df8d1a84475945`。
  - `Punct-CT-Transformer/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12/model.onnx`：294,372,519 字节，SHA-256 `e93593a6dbd69a07f8734ef269dbe861a379755f8d1c8354719432116f2c44bd`。
- 两个平台实际解码探针使用的同一份 WAV 为 24,078 字节、单声道 48 kHz、12,000 帧、0.25 秒，SHA-256 `7b3a5426e7cca3bd956749144515f3d34fcd133f7b3b777d1460cca1e223bc90`。
- 准备目录里原有的 Linux 合成 WAV 与 macOS WAV 虽同为 0.25 秒、同格式，SHA 却分别为 `660386a10c9f4b3f962e8e2302c09c92950c46dc7f466d40bc9037e939be99f7` 和 `7b3a5426e7cca3bd956749144515f3d34fcd133f7b3b777d1460cca1e223bc90`。为满足同输入比较，本审计将 macOS 样本复制到私有审计目录供 Linux 消费；没有改动原输入。
- Linux 实际消费者捕获的 FFmpeg 参数为：`ffmpeg -nostdin -hide_banner -loglevel error -i <private-input> -ar 16000 -ac 1 -f f32le pipe:1`。构造参数与实际启动 argv 完全相同。输出为 4,000 个 float32、16,000 字节；NaN/Inf 均为 0，maxabs 为 0.1249694899，SHA-256 `a1f23ca8864232373e378b21cb4506f7d6333162bf008a877aba8626dea9b46f`。
- macOS 的 Python 导入通过，但 `ffmpeg_path()` 为空，真实消费者以 `JobFailure` 结束，故没有 macOS PCM 可比较。Windows SSH 单次无交互探针退出 1，未取得 stdout/stderr；没有重试或扫描网络。
- 同长度全零数组负例为 4,000 个样本，长度判据相同但内容比较为不相等，判据成功报红。由于 macOS 无 PCM、Windows 不可达，三平台 RMSE 和差异区间仍未知。
- Python 版本分别为 Linux 3.12.3、macOS 3.12.15；后端、SDK、NumPy、WebSockets、HTTPX、Rich 的指定导入均通过。两边 `python -m pip check` 均因 `pip` 模块缺失退出 1；Linux 另用只读 `uv pip check` 检查 53 个包，退出 0。macOS 当前 PATH 找不到 FFmpeg，且无可用 `uv`。
- POSIX 权限来自实际文件系统：Linux 准备根和模型源目录均为 0700，源权重为 0644 且被 0700 父目录隔离；Linux venv-local 为 0775，但其准备根为 0700，Python 实际可执行。macOS 准备根、venv、models 目录为 0700，权重为 0600，venv Python 实际可执行。Windows ACL 未核验。

## 日志与操作事件

- 已有本地日志共 3 个：标准输出 2,157 字节，标准错误和验证输出为空；任务目录内没有 session JSONL。安全扫描识别 1 条普通配置记录，凭据型记录为 0，未找到可用事件时间。
- 任务目录原权限为 0775，日志原权限为 0664；已将该任务自有目录改为 0700、三份日志改为 0600，文件字节数未改。共享父目录未改。日志之外的执行器会话及平台接收状态未知，不能据此断言未外发。
- 派发上下文记载曾有一次绕过全局 Git hook 的提交尝试后重做。现有标准输出没有足够证据证明最终准备提交实际运行过全局 hook；当前有效 hook 配置指向已安装的全局 hook 集，未见持久化的绕过配置。本审计不重写历史、不替准备提交背书。
- 凭据处置仍为 pending：本卡未撤销或轮换凭据、未停服务、未发通知。此结论与已扫描日志中的 0 个凭据型记录分开记录。
