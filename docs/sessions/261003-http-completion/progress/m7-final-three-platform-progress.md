# M7 最终三平台进度

- Dispatch-Id：`dlg-20261005-042235-e1a489`
- 阶段：verifying
- Base / 冻结源：`492fe191e3f9568ea178b61970c732c9d37c4e29`
- 角色：叶测量执行器（脚本/采集/Doc 未再派发）

## 结论

partial，**不能声称 M7Done**。Linux 与 Mac 已在独立目录用 492fe 真实 `CapsWriterServer.start` + 真实 Paraformer/Punct + 仓库 SDK CLI 完成 77.184 秒 WAV/MP4 的 HTTP 与默认 WS v2；Windows 未开机；可信独立人工参考未取得；231.552 秒素材未找到。

## 已完成

- 新独立 `git archive` + checkout，13 个 server/SDK/collector 模块与 archive 字节一致；health `492fe19` / protocol 2 / role server / paraformer / worker_alive。
- Linux 四次采集与独立 FFmpeg 16 kHz mono f32le 4 939 776 字节对齐；HTTP SQLite 2×DONE；TERM 后子进程 gone，只读重开仍 DONE。
- Mac 四次采集同样 DONE/final；TERM 0。跨平台 token 与 WS 解码字节有差，只记录。
- 组合源两套均为 `493 passed, 3 skipped`：固定 `websockets==15.0.1`（261.69 s）与 uv 解析 17.2（252.52 s）；skip 为 aligner:53/:62 与 segmenter:208。
- 未改 App/SDK/collector/tests/CI/config/Goal/旧证据；未动生产服务。

## 失败 / 未测

- 三个公开候选未得到官方人工文本与音频绑定；私有素材无 CER。
- Windows：prep 只有 `windows-known-host` 标签，不是 SSH Host。
- 231 s 素材、Goal 7 公开格式派生、弱网手工重连、Windows PID/PeakWorkingSet64。
- 派发主干 CI 基线不可用，继承红未能判定。

## 现场

- 工作树 `card/http-m7-final-three-platform-261005`，起点即 492fe。
- 无交接单。巡检存活探针不可用；memory 命中多设备与部署条目，只用来理解已有 prep 路径，未读 profile。
- 本仓仍开 #72/#69/#68/#67/#65 等，不在本卡范围。

## 本派发新 bootstrap 记录（2026-10-05）

- 本派发 `dlg-20261005-054600-e8f4a5` 从 f705 新工作树启动；运行源仍为
  `492fe191e3f9568ea178b61970c732c9d37c4e29`，本轮只追加文档证据。
- Windows 原生 SSH 只读连接成功；prep 根存在，Python、`numpy`、
  `sherpa_onnx`、`soundfile` 初验成功。精确成功 runner、correction 指针和
  三条授权 231 秒文件均不存在，未使用相邻脚本或通用目录名替代，Windows
  完整服务/两协议/PID/PeakWorkingSet64 保持未测。
- WeNet/AISHELL manifest 三行在私有进程内解码，data-list/text 参考字段
  36 字节逐字节一致并以 `0600` 私有文件保存；唯一匿名 GET 的 31 字节响应
  不是 RIFF WAV，未重试，故 gold/CER 与四 codec 不成立。
- 231 长样本、可信 gold、四 codec 和 explicit weaknet 没有真实 producer
  输入，保持 `blocked/not run`；本阶段仍 `partial`，不声称 M7Done。
