# M7 三平台前置环境准备记录（非生产部署）

本文件记录为「未来三平台正式统一版本基线」准备隔离依赖环境与同源模型权重的实测结果。
本卡**没有**启动任何 ASR 服务、没有加载模型做识别、没有测 77 秒素材，也不构成任何平台的
质量或运行时就绪结论。正式三平台量测必须在未来最终 merged SHA 上重做。

## 1. 范围与不变量

| 项 | 本卡实际做的事 |
| --- | --- |
| 代码版本 | 只用派发时已 merged 的基线提交做**只读验证副本**（`src/repo-*`，不 git init、不指向生产 clone） |
| 依赖环境 | 每台机器一个**本卡私有**目录：私有解释器、虚拟环境、uv 缓存、私有脚本、私有日志 |
| 模型权重 | 从已知的 Linux 私有 cache **只读**复制，复制后逐文件重算字节数与 SHA-256 |
| 隔离边界 | 不写生产 repo/`.env`/虚拟环境/shebang/计划任务/服务定义/launchd/systemd/注册表/全局包；不改 PATH 与 shell profile |
| 执行内容 | 只有包安装、import、`ffmpeg -version`、一条 0.25 秒合成音频解码 |
| 未执行 | 不构造识别器、不起服务、不读 77 秒素材、不做质量判定 |

## 2. 目标平台（匿名）

| 平台代号 | 系统/架构 | 原有生产状态（只读采样） | 本卡动作 |
| --- | --- | --- | --- |
| `linux-ref` | Linux x86_64 | 无 ASR 监听；是本卡的权重来源与参照 | 只读复制源 + 本地参照消费者指纹 |
| `mac-arm64` | macOS arm64 | 生产端口 6016/6017/6020 **均无监听**；部署目录非 git；系统无 ffmpeg、无 Python 3.12 | 全量准备（私有解释器/venv/权重/消费者检查） |
| `win-x64` | Windows x64 | 计划任务运行中，监听 6016；三个 python 进程均早于本卡启动；系统 Python 3.11.7 | 只在私有目录准备（不重启、不改计划任务） |

`mac-arm64` 是唯一完全空闲的候选；`win-x64` 是生产在跑的主机，本卡只做旁路准备。

## 3. 私有环境与依赖版本

三个平台的私有虚拟环境安装同一组依赖（服务端 CPU 集合 + SDK 依赖 + 私有 ffmpeg 轮子），
`pip check` 全部通过。

| 包 | `linux-ref` | `mac-arm64` | `win-x64` |
| --- | --- | --- | --- |
| Python | 3.12.3 | 3.12.15 | 3.12.12 |
| numpy | 2.5.3 | 2.5.3 | 2.5.3 |
| soundfile | 0.14.0 | 0.14.0 | 0.14.0 |
| rich | 15.0.0 | 15.0.0 | 15.0.0 |
| colorama | 0.4.6 | 0.4.6 | 0.4.6 |
| httpx | 0.28.1 | 0.28.1 | 0.28.1 |
| websockets | 15.0.1 | 15.0.1 | 15.0.1 |
| sherpa-onnx | 1.13.8 | 1.13.8 | 1.13.8 |
| onnxruntime | 1.30.0 | 1.30.0 | 1.30.0 |
| gguf | 0.19.0 | 0.19.0 | 0.19.0 |
| imageio-ffmpeg | 0.6.0 | 0.6.0 | 0.6.0 |
| aiohttp | 3.14.3 | 3.14.3 | 3.14.3 |
| 其余（watchdog/pypinyin/srt/tqdm/requests/pyyaml/nagisa/soynlp） | 三方一致 | 三方一致 | 三方一致 |

解释器来源：两台目标机都装了**本卡私有**的 CPython 3.12（不写系统 PATH、不写 shell profile），
`mac-arm64` 的 uv 用 `INSTALLER_NO_MODIFY_PATH=1` 安装到私有目录，安装前后 shell profile 的
mtime 均未变化；`win-x64` 复用机器上已有的用户级 uv 可执行文件，但把 `UV_CACHE_DIR`、
`UV_PYTHON_INSTALL_DIR`、venv 全部指向私有目录，没有升级或改写该 uv。

## 4. 真实 CPU 后端（import 实测，非 stub）

| 平台 | onnxruntime providers | device | sherpa-onnx |
| --- | --- | --- | --- |
| `linux-ref` | Azure / CPU | CPU | import 成功，`OfflineRecognizer` 存在 |
| `mac-arm64` | CoreML / Azure / CPU | CPU | 同上 |
| `win-x64` | Azure / CPU | CPU | 同上 |

`win-x64` 的私有环境刻意用 CPU 版 onnxruntime 而不是生产用的 DirectML 版：三平台正式基线
要同模型同 CPU 路径。`mac-arm64` 列出 CoreML 只是 wheel 自带 provider，**不表示**本卡走过它。

## 5. ffmpeg：真执行，不是查路径

业务解码器用 `shutil.which("ffmpeg")` 找可执行文件，找不到就直接报错。因此「装了 ffmpeg」这件事
必须由真实消费者代码来判定。

| 平台 | 来源 | `ffmpeg -version` 首行版本 |
| --- | --- | --- |
| `linux-ref` | 私有 wheel（`imageio-ffmpeg` 0.6.0 内置二进制） | 7.0.2-static |
| `mac-arm64` | 私有 wheel（系统无 ffmpeg） | 7.1 |
| `win-x64` | 私有 wheel（另有系统自带便携版，只读参考，未采用） | 7.1-essentials_build |

实测踩到的真问题：wheel 内二进制文件名带平台与版本后缀（如 `ffmpeg-macos-aarch64-v7.1`），
`shutil.which("ffmpeg")` 按精确名查找，直接把二进制目录加进 PATH **找不到**，
`mac-arm64` 的消费者检查第一次就是这样失败的。修法是在私有 `bin` 目录放一个同名入口
（POSIX 用符号链接、Windows 复制成 `ffmpeg.exe`），并让消费者检查在 `which` 返回空时
直接失败退出，不静默继续。修完后三平台的 `available_encodings()` 都返回
`f32le / s16le / flac / ogg_opus`。

## 6. 模型权重：只读复制 + 逐文件校验

来源是 Linux 已知私有 cache 里的 CPU Paraformer 权重，本卡没有下载任何其它模型。
三台机器（Linux 参照、macOS、Windows）解包后逐文件重算，结果完全一致：

| 文件（相对模型根） | 字节 | SHA-256 |
| --- | --- | --- |
| `Paraformer/.../model.onnx` | 243371218 | `f36a0433bcf096bd6d6f11b80a3ac8bed110bdca632fe0d731df8d1a84475945` |
| `Paraformer/.../tokens.txt` | 84160 | `6abd232d5b0b0ae29c062a06c658c199514f30d89c963d96e4beec2587b9bc7a` |
| `Punct-CT-Transformer/.../model.onnx` | 294372519 | `e93593a6dbd69a07f8734ef269dbe861a379755f8d1c8354719432116f2c44bd` |
| `Punct-CT-Transformer/.../tokens.json` | 4207480 | `c960ab87bccea4aa15cf49a59f71973c2c330b46668048cd8da253749ec71ee3` |

四个权重文件的 SHA-256 与本卡源 cache 的私有 manifest 逐字一致。完整清单见私有 manifest
（9 个文件，含随权重复制进来的 README/配置/示例脚本）。

传输件（权重打包、只读验证副本打包、合成音频）在两台机器上都先校验 SHA-256 再解包，
不匹配即以 `BASELINE_PREP_FAILED phase=... errorclass=sha_mismatch` 非零退出。

## 7. 实际消费者验证指纹

消费者检查做的是**真实业务代码**做的事：在只读验证副本里 import 音频解码器，用真实 ffmpeg
子进程把同一段 0.25 秒 flac 解成 16 kHz 单声道 f32le，并统计输出字节数与 SHA-256。
输入字节在三个平台上是同一份（从 Linux 侧生成后复制过去，逐平台校验 SHA-256）。

| 平台 | 解码样本数 | 解码字节 | 解码输出 SHA-256 | 消费者进程峰值 RSS |
| --- | --- | --- | --- | --- |
| `linux-ref` | 4000 | 16000 | `a1f23ca8864232373e378b21cb4506f7d6333162bf008a877aba8626dea9b46f` | 66.9 MiB |
| `mac-arm64` | 4000 | 16000 | `2559d2e8b387fccaefb6bf1a4af2a9c85d9c65074ae8b6064b54585dfafd1db7` | 59.2 MiB |
| `win-x64` | 4000 | 16000 | `a1f23ca8864232373e378b21cb4506f7d6333162bf008a877aba8626dea9b46f` | 62.4 MiB |

**跨平台结论**：样本数与字节数三平台一致，但 `mac-arm64` 的解码字节与另两平台不同 ——
差异来自 ffmpeg 构建版本不同（7.1 vs 7.0.2-static / 7.1-essentials），不是输入不同。
未来做跨平台对照时，不能拿解码后的 PCM 字节当跨平台等价判据；要跨平台比的是样本数、
时长、以及识别结果本身。

## 8. 权限

| 平台 | 检查方式 | 结果 |
| --- | --- | --- |
| `mac-arm64` | POSIX mode | 目录全部 `0700`；文件无 group/other 位（数据 `0600`，需执行文件 `0700`）；符号链接本身 `0755` 但目标 `0700`，POSIX 下链接权限位不生效 |
| `win-x64` | `icacls` / `Get-Acl` 实际 DACL | 私有根 1907 个目录 + 17177 个文件全部只授予 owner / SYSTEM / Administrators；未继承父目录任何宽权限条目 |

`win-x64` 的检查一开始**是红的**：uv 缓存里有一个 wheel 被写入了额外的 `OWNER RIGHTS` 条目，
逐文件扫描报了 1 条越界。已按最小 DACL 修正后重扫为 0 条。父目录权限本卡从未下发过任何
`icacls`，前后只做了读取。

顺带记录一次本卡自己造成的破坏与修复：`mac-arm64` 上最初用一条 `chmod 600` 铺全树，
把私有虚拟环境里解释器的执行位也一起去掉了，消费者脚本立刻 `Permission denied`；
修正为「目录 `0700`、数据 `0600`、可执行文件 `0700`」后重跑消费者检查通过。
这类回归只有真去执行那条命令才会暴露，所以最终交付态是重跑过消费者检查的状态。

## 9. 资源与残留

| 平台 | 采样项 | 值 |
| --- | --- | --- |
| `mac-arm64` | 可用内存（导入前） | 5.2 GiB / 16 GiB |
| `win-x64` | 可用内存（导入前） | 17.0 GiB / 27.7 GiB |
| 全部 | 消费者进程峰值 RSS | 59.2 – 66.9 MiB，远低于 2 GiB 上限 |

包安装与 import 全部前台串行执行，单个子进程都有超时上限；本卡没有派生任何后台常驻进程。
收尾只读采样确认：两台机器的 PATH 未被加入私有目录，shell profile mtime 未变，
`win-x64` 上现存的三个 python 进程全部早于本卡启动时间且用的是系统 Python（生产实例），
本卡没有终止任何进程、没有触碰生产服务与计划任务，也没有请求生产 HTTP 端点。

## 10. 明确未验证的部分

1. **最终 merged SHA 未测**：本卡用的是派发时已合并的基线提交做只读验证副本。正式三平台
   基线必须在最终合并提交上重跑，本文件的所有依赖版本与指纹都只是该提交的快照。
2. **模型运行时就绪未测**：没有构造识别器，没有加载权重做推理，没有验证 CPU Paraformer
   在两台目标机上真的能跑起来、内存占用多少、耗时多少。
3. **质量未测**：没有跑 77 秒素材，没有 CER/WER，没有人工参考稿。
4. **生产同构未测**：两台目标机的生产部署方式（PM2 / 计划任务、模型目录布局、系统 Python）
   与本卡私有环境不同，正式基线卡片需要自己决定用哪套解释器与权重路径。
5. **`win-x64` 的 GPU 路径未准备**：生产用 DirectML + Vulkan，本卡只准备 CPU；是否需要
   在正式基线里加 GPU 变体由主脑与用户定。

## 11. 给正式基线卡片的使用说明

- 私有目录、venv 解释器路径、私有 uv 缓存、私有 ffmpeg 入口、模型绝对路径、逐文件 SHA-256
  清单都写在**每台机器本地**的私有 manifest JSON 里（含主机路径，不入公开仓）。
  正式基线卡片请从那台机器上读取，不要把本卡的临时路径当成长期引用。
- 使用方式三条硬要求：用私有 venv 的解释器；把私有 `bin` 目录放进 PATH（否则解码器会按设计
  报错退出）；模型参数指向私有模型目录（只读引用）。
- 正式基线请重新计算一遍本文件第 6 节的权重指纹，确认未来那份权重仍是同一批字节。
- 若最终 merged SHA 改了 `requirements-server-*.txt` 或新增引擎依赖，必须重装而不是沿用本卡环境。