# M7 平台准备进度（m7-platform-prep）

状态：**已完成**（准备就绪；不代表任何平台已通过三平台基线验证）

## 本卡做了什么

1. 在两台目标机各建一个**本卡私有**目录：私有 CPython 3.12、私有虚拟环境（服务端 CPU 依赖集 +
   SDK 依赖）、私有 uv 缓存、私有 ffmpeg 入口、私有脚本与日志。不写生产 repo/`.env`/venv/shebang/
   计划任务/服务定义/launchd/systemd/注册表/全局包，不改 PATH 与 shell profile，不升权限。
2. 从已知的 Linux 私有 cache **只读**复制 CPU Paraformer 与 Punct 权重到两台机器的私有模型目录，
   逐文件重算字节数与 SHA-256；传输件先校验 SHA-256 再解包。
3. 在派发时已 merged 的基线提交上做只读验证副本，用**真实业务代码**（音频解码器 + 真实 ffmpeg
   子进程）解一段 0.25 秒合成音频到 16 kHz 单声道 f32le，锁下消费者指纹；import 真实 CPU 后端
   （onnxruntime / sherpa-onnx）并读 provider 与 device。
4. 校验隔离性：macOS 逐条校验 POSIX mode，Windows 逐条校验实际 DACL（1907 目录 + 17177 文件）。
5. 收尾只读采样确认：两台机器 PATH 未被改、shell profile mtime 未变、生产进程与计划任务未被触碰、
   本卡没有派生后台常驻进程，也没有请求生产 HTTP 端点。

## 关键实测结论

- 三平台 Python 3.12 + 依赖版本完全一致；onnxruntime 均为 CPU 路径（Windows 未用生产的 DirectML 版）。
- **ffmpeg 必须有同名入口**：wheel 内二进制名带平台与版本后缀，业务代码用 `shutil.which("ffmpeg")`
  精确名查找，直接把二进制目录加进 PATH 会失败；已用私有 `bin/ffmpeg`（Windows 为 `ffmpeg.exe`）修正，
  修完三平台 `available_encodings()` 才有 `flac/ogg_opus`。
- **同一段输入，跨平台解码字节不同**：样本数与字节数三平台一致（4000 / 16000），但 macOS 的 ffmpeg
  7.1 与 Linux/Windows 构建产出的 PCM SHA-256 不同。未来跨平台对照不能拿解码 PCM 字节当等价判据。
- 权限检查真的会红：Windows uv 缓存里有一个 wheel 带了额外的 `OWNER RIGHTS` 条目，逐文件扫描报出后
  按最小 DACL 修正，重扫为 0。
- 本卡自己造成的破坏已修并复跑：macOS 上一条 `chmod 600` 铺全树把私有解释器执行位也去掉了，
  消费者脚本立刻 `Permission denied`；改为「目录 0700 / 数据 0600 / 可执行 0700」后重跑通过。

## 明确没有做

- 没有启动任何 ASR 服务、没有构造识别器、没有加载权重做推理 → **模型 runtime 就绪未验证**。
- 没有跑 77 秒素材、没有 CER/WER、没有参考稿 → **质量未验证**。
- 没有测最终 merged SHA（未来合并后的代码才需要重测）→ **正式三平台基线仍未开始**。
- 没有准备 Windows GPU（DirectML/Vulkan）路径，生产同构方式也未验证。

## 产物位置

- 公开文档：本目录 `m7-platform-prep.md`（匿名版本，含版本/指纹/未验证清单）。
- 私有交接：每台机器本地私有目录里的 `private-manifest.json`（含主机绝对路径、venv 解释器路径、
  私有 ffmpeg 入口、模型路径与逐文件 SHA-256），**不入仓**。
- 私有脚本/日志/传输件：同一私有目录下的 `scripts/`、`logs/`、`payloads/`。

## 下一步（不在本卡）

正式三平台基线卡片读取各机私有 manifest，用最终 merged SHA 重装依赖、重校验权重指纹，
再按各自口径启动隔离实例做正式量测。