# PR64 第二轮专项核实：stereo PCM 字节计量

failure-visibility: p2-only

- 任务执行状态：completed。此行 verdict 与执行器任务完成状态正交。
- 审查对象：`4de4a7ffa44dfb50b48c252510927c4b2166cc77..b65d6aced9969bd7e8a144dd4708f0b579969495`，固定 H0。
- 专项 finding：`correctness_stereo_pcm_byte_measurement`（工具标注 major）。
- 独立结论：major 所称「`decoded_pcm_bytes` 数值错误」未获实测支持；没有 P1。存在一个 P2 语义清晰度问题：WAV 快路径按声道帧数报告目标 mono PCM 字节，但注释/规范读起来像是 `soundfile` 实际产出了 mono buffer。仅记录，不在本卡修复。

## 分母分别是什么

| 名称 | 实际定义 | stereo 实测 |
|---|---|---:|
| CLI `decoded_pcm_bytes` | 报告的目标格式为 16 kHz mono float32 时，每帧 4 字节；WAV 快路径取帧数乘 4 | 6,400 字节 |
| `soundfile` 已加载数组 | WAV 解码原声道数组的 `nbytes`，形状为 frames × channels | `(1600, 2)` float32，12,800 字节 |
| 独立 FFmpeg mono 产物 | `-ar 16000 -ac 1 -f f32le` 真正写出的文件字节与帧数 | 6,400 字节、1,600 帧 |
| SDK / 服务消费者 | SDK WS 实际转码产物、HTTP 原文件上传、服务端 HTTP 实际流式 PCM 解码，各有自己的产物口径 | WS `f32le` 6,400 字节；默认 FLAC 9,012 字节且回解码 1,600 samples；HTTP 上传原 WAV 6,444 字节；服务端解码器输出 6,400 字节/1,600 samples |
| 内存峰值 | CLI 未量 CPU/RSS；SF 数组 `nbytes` 不是进程峰值，也不是 CLI 字段承诺 | 未测，保持 unknown |

## 可复现的实际证据

- 环境：Python 3.12.3、SoundFile 0.14.0、NumPy 2.5.0、FFmpeg 6.1.1。合成输入是 16 kHz、1,600 帧、双声道各自非零且彼此不同的 PCM16 WAV；另有同帧数 mono 对照。没有使用任何真实媒体、部署中的服务进程、识别模型或密钥。
- `python3 /tmp/pr64-stereo-review-dlg-20261005-033327-aee7ae/probe.py`：H0 `_decode_pcm_bytes` stereo 返回 `(6400, 0.1)`，mono 对照也返回 6,400 字节/0.1 秒。探针将真实 FFmpeg mono 输出落成 `stereo-ffmpeg-normalized.f32le` 并以实际文件长度和 4 字节帧数核对，不用内存估算作黄金值。
- 独立 producer 命令：`ffmpeg -nostdin -hide_banner -loglevel error -i /tmp/pr64-stereo-review-dlg-20261005-033327-aee7ae/stereo-nonzero.wav -ar 16000 -ac 1 -f f32le /tmp/pr64-stereo-review-dlg-20261005-033327-aee7ae/stereo-ffmpeg-normalized.f32le`。实际文件为 6,400 字节、1,600 帧。
- `python3 /tmp/pr64-stereo-review-dlg-20261005-033327-aee7ae/consumer_probe.py`：调用仓库 SDK `client._transcode` 真正跑 FFmpeg，分别记录 `f32le` 和默认 `flac`；也直接执行服务端 `FileSourceDecoder` 的真实 ffmpeg/chunk 路径。两路 PCM 都与独立 FFmpeg 文件逐字节相同，服务端 `samples_emitted=1600`。这调用的是 H0 消费者代码，不启动原服务或识别模型。
- `probe.py` 的判据先比 helper 值和独立 FFmpeg 实际文件字节，再喂入 `frames × channels × 4 = 12,800` 的 known-bad 值；比较按预期抛出断言，证明判据能将坏分母判红。
- 同一探针以匿名 WAV 输入运行真实 `_baseline_http_ws.py` CLI，HTTP 端连接本机合成响应 stub：进程退出码 0、stdout `status=ok`/`decoded_pcm_bytes=6400`，私有 JSON `status=ok`/`decoded_pcm_bytes=6400`/`f32le/16000/mono`。SDK HTTP PATCH 实际发送 6,444 字节，逐字节等于源 WAV；stub 仅返回合成识别结果，不代表真实模型质量。私有 JSON 在 `0700` 目录中，文件权限 `0600`。
- 原始 WAV 与 PCM 产物、CLI 私有 JSON、探针代码均保存在 `/tmp/pr64-stereo-review-dlg-20261005-033327-aee7ae/`；汇总读数在该目录 `evidence.json`。未把音频字节、转录、哈希或凭据写入 stdout、verdict 或 Git。

## Spec、producer 和 P1 两问

- `docs/guides/http-baseline.md:15-16` 将源文件字节、目标 16 kHz mono PCM 字节、SDK HTTP PATCH 字节、WS JSON/FLAC payload 分开定义；`scripts/_baseline_http_ws.py:354-374` 的 WAV 路径实际加载多声道 SF 数组，但只报告 frames × 4。数值对应“归一化目标 mono PCM 的字节长度”，不对应 SF 原始数组分配量。其数值与 FFmpeg 实际 mono 文件、SDK mono `f32le` 输出及服务端实际 mono decoder 输出一致。
- SDK WebSocket `_transcode` 明确使用 FFmpeg `-ar 16000 -ac 1`（`sdk/capswriter_asr/client.py:95-127`）；HTTP `submit_file_http` 上传原始源文件（`sdk/capswriter_asr/http_client.py:527-560`），服务端 `FileSourceDecoder` 以固定 `-ar 16000 -ac 1 -f f32le` 分块输出（`core/server/http_file_runner.py:86-156`）。CLI `decoded_pcm_bytes` 只写入摘要，不驱动这些 producer。
- P1 问一：会否触发？会。16 kHz stereo WAV 被当前 CLI 接受并命中 WAV 快路径；文档列出 WAV 样本且没有排除该声道类别。真实数据集的声道分布未测，不能说 stereo 非法。
- P1 问二：后果是否不可接受？没有证据表明该字段的目标 mono 字节数错误或会导致 SDK/服务音频结果错误；它与实际 mono 产物字节数一致。原始 SF 数组确实是报告数值的两倍，但 CPU/RSS 峰值不是本字段的承诺，指南明确列为未测。
- 测试锁定：`tests/test_http_baseline.py` 共 11 个 pytest case。CLI 回归只用 160 帧 mono WAV 并断言 `160 * 4`（约 218-275 行）；HTTP producer 用 8 字节 `.bin` 与 `tests/fixtures/http_baseline_producer.json` 锁请求序列化（约 138-165 行，夹具 1-33 行）；WS producer 测试对 `_transcode` 做 monkeypatch（约 172-210 行）。没有 stereo `_decode_pcm_bytes` 回归锁，已在本次物理探针补证，未新增测试。
- 结构性误读源：`_decode_pcm_bytes` 注释（355 行）称 soundfile 解码为 mono，但它只返回二维原声道数组；字段命名和指南未说明 WAV 路径只是用帧数推导目标 mono 字节数、没有物化 mono buffer。可通过文档/名称消歧，不能据此把 raw SF buffer 或 memory peak 并入该字段。此建议属 P2 清晰度，不是 major 计量错误；本卡按要求未修 P2。

## 边界与未知

只新增本 verdict。未改 App、SDK、collector、tests、旧证据/verdict/profile/env/provider keys/source gate；未运行顾问、primary rerun、PR/ready、merge 或部署；不裁决整体 M7 方案。派发时基线记录 `gh api request failed`，完整 Gate 当前仍未知。真实数据集是否含 stereo 未知；无原始音频或服务端生产进程参与此核实。
