# M7 三平台真实 CPU 模型加载与单次推理前置冒烟

## 结论边界

本记录是 M7 真实模型验证的前置 smoke，不是最终服务端验收、模型质量基线、准确率/CER 结论，也不把模型输出当参考答案。三台机器均在隔离任务环境中用本仓 `3d7436c499829eb8bb92fc3757b6e4968c88e548` 的完整源码快照，真实构造 Paraformer 和 Punct 引擎，并各做一次短 PCM ASR 与一次标点调用；三台结果均为 `green`。

本轮没有启动、覆盖、重启、停止或扫描原服务，没有全局安装、修改全局 PATH、修改原虚拟环境，也没有触碰正式模型评审、PR、门禁或凭据。

## 固定输入、模型与源码证据

探针实际读取同一份 0.25 秒、16 kHz、mono、little-endian float32 PCM：

| 字段 | 值 |
| --- | --- |
| PCM 字节数 / float32 数 | 16000 / 4000 |
| PCM SHA-256（三平台） | `6d04345a9f7e19fde275ac78272365022ec4a5ac6be4440db0e5d8b3e7580bea` |
| finite / maxabs | `true` / `0.2499646246433258` |
| 生产者输出 | 新任务自己的私有输入夹具；未把识别文本作为期望值 |

模型文件在三台平台均按实际 factory 路径枚举，并对文件字节做了校验；权重从既有隔离只读缓存引用，未重新传输两份大权重：

| 角色 | 字节数 | SHA-256 |
| --- | ---: | --- |
| Paraformer `model.onnx` | 243371218 | `f36a0433bcf096bd6d6f11b80a3ac8bed110bdca632fe0d731df8d1a84475945` |
| Paraformer `tokens.txt` | 84160 | `6abd232d5b0b0ae29c062a06c658c199514f30d89c963d96e4beec2587b9bc7a` |
| Punct `model.onnx` | 294372519 | `e93593a6dbd69a07f8734ef269dbe861a379755f8d1c8354719432116f2c44bd` |
| Punct `tokens.json` | 4207480 | `c960ab87bccea4aa15cf49a59f71973c2c330b46668048cd8da253749ec71ee3` |

子进程从本任务新建的 Git 源码快照加载，manifest 指定提交为 `3d7436c499829eb8bb92fc3757b6e4968c88e548`；10 个实际加载模块均通过“加载文件相对快照路径 + SHA-256 与该提交正本字节相同”的校验。包含 `config_server.py`、`core.server.state`、`EngineFactory`、Paraformer engine、CT-Transformer Punct engine 及其包初始化文件；没有把旧 `820c3a2` 快照当作本轮源码证据。

## 安全 argv/env 与真实调用

各平台只记录非敏感白名单参数，路径以角色名代替：

```text
python model_smoke_probe.py
  --model-root <isolated-read-only-model-root>
  --snapshot-root <new-3d743-source-snapshot>
  --source-manifest <new-source-manifest>
  --pcm <new-synthetic-pcm>
  --output <private-result>
  --pid-file <private-pid-file>
```

子进程环境白名单为 `PYTHONPATH=<new-source-snapshot>`、`CW_MODEL_TYPE=paraformer`、`OMP_NUM_THREADS=1`、`ORT_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`TOKENIZERS_PARALLELISM=false`。Paraformer config 实际记录为 `provider=cpu`、`num_threads=1`、`sample_rate=16000`、`feature_dim=80`、`decoding_method=greedy_search`；没有 GPU、云 API 或 provider credential。

真实 API 顺序是：

1. `EngineFactory.create_asr_engine("paraformer")`，由本仓 `ParaformerEngine` 调 sherpa-onnx 的 Paraformer factory；
2. `create_stream()`、`accept_waveform(16000, float32_pcm)`、`decode_stream()` 完成一次真实 ASR；
3. `EngineFactory.create_punc_engine()` 构造本仓 `CTTransformerPuncEngine`，对探针自造的中文短句调用一次 `punctuate()`。

## 三平台结果

| 平台 | Python | 模型/推理耗时 | CPU 峰值内存 | ASR 消费结果 | Punct 消费结果 | 进程 |
| --- | --- | ---: | ---: | --- | --- | --- |
| Linux | 3.12.3 | 2.489 s | 932.32 MiB | `RecognitionResult`；text 为 `str`，长度 1；token/timestamp `1/1`，finite | `str`，长度 12 | rc=0，超时=false，已退出 |
| Mac Apple Silicon | 3.12.15 | 1.254 s | 1021.14 MiB | 同上 | 同上 | rc=0，超时=false，已退出 |
| Windows | 3.12.12 | 2.891 s | 331.71 MiB | 同上 | 同上 | rc=0，超时=false，已退出 |

Linux 和 Mac 的峰值来自探针进程自身 `ru_maxrss`；Windows 的峰值来自同一任务 runner 按探针真实 PID 采样的 `WorkingSet64`。三者均低于本轮 2 GiB 目标；加载与推理总预算为每台 180 秒，均未接近超时。ASR 文本内容、标点内容和音频字节均没有打印到报告或标准输出。

Windows 新任务根的 ACL 复核为 owner 类别 1、admin/system 类别 2、`otherCount=0`、Deny 0；Linux/Mac 新任务根为目录 0700、文件 0600。所有自有探针 PID 均确认退出；未杀任何父派发组或原服务进程。

## 判据与已知坏输入

以下判据在每个平台都实际执行，不能由“返回 0 且文件存在”替代：

| 坏夹具 | 期望 | 三平台结果 |
| --- | --- | --- |
| 将 Paraformer 权重路径换成不存在文件，再走真实 `EngineFactory.create_asr_engine` | factory 构造异常，判红 | `missing_weight_red=true` |
| 用 64 个 `0` 作为 `model_source_sha`，对实际权重做校验 | 来源哈希不匹配，判红 | `wrong_model_source_sha_red=true` |
| 将 `123` 交给结果可消费类型判定 | 非法输出类型，判红 | `invalid_output_type_red=true` |

有效输入同时满足模型四文件存在且 SHA/尺寸正确、PCM 16000 字节且 finite、源码 10/10 字节校验通过、真实 ASR/Punct API 返回可消费类型；stderr 没有被用来掩盖 backend 硬错，子进程非零或超时会使该平台失败。

## 未测事项

- 没有以模型输出做 gold/reference，没有准确率、CER、可懂度或最终质量结论。
- 没有启动完整 WebSocket/HTTP 服务，没有做 SDK、server、工具版本共同 SHA 或生产门禁验收。
- 没有补装 native DLL、系统 VC++ runtime、全局 PATH 或另一 engine fallback；本轮真实 CPU 依赖已经可加载。
- 本轮源快照 `3d7436c` 只是本次可复现输入，不是声明最终合并 server/tool SHA；正式质量测量仍需等待其约定的最终固定源。
