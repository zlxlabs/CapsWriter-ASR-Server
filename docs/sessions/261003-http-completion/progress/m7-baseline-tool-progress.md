# M7 基线工具进度

更新时间：2026-10-04（UTC+8）

## 当前阶段

- 工具实现前的现场核查已完成；工作树为独立派发分支，起始 HEAD `820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2`，无在途改动。
- 既有 `_baseline_asr.py` 是 WS v1 Base64 JSON 客户端；本卡保留旧入口，新增工具调用 SDK 默认 WS v2 与 HTTP SDK producer。
- 同一私有素材的 MP4 音轨与 16 kHz WAV 解码后均为 1,234,944 samples（77.184 秒）；PCM 相关系数约 0.99999997，但逐样本不相等。字幕末尾 77.040 秒，落在视频 77.184 秒内。
- 字幕没有可核实的人工标注或生成来源记录；仅可标记 `unverified`，不作为正确率真值。
- 当前 Linux checkout 没有模型权重。只读检查确认生产 Mac 上运行的 Paraformer 服务健康、代码版本为 `6b7a2b8`，权重文件非空；这个运行实例只作为权重来源，本卡不会在生产机启动/改动服务。

## 已完成的工具单元

- 完成 `scripts/_baseline_http_ws.py` 初版：固定 loopback、server health/模型/SHA 校验、真实 SDK 默认 WS v2 与 HTTP producer 计量、私有 JSON 输出、无自动重试和 `BASELINE_FAILED`。
- 新增 6 个定向测试及 `tests/fixtures/http_baseline_producer.json`。两条独立红验分别抓到 SRT 未归一化、WS SDK 实际帧遗漏 `model` 字段；修复后定向测试 `6 passed`。
- HTTP CLI 测试在真实本机 TCP 假服务前运行子进程，断言 SDK 实际 POST/PATCH/commit 请求、上传源 body、选项、重发计数、退出码、stdout 隐私和落盘 JSON 字节。假 ASR 返回与正式 Linux 模型测试严格分开。
- 已建立早 draft PR #64；PR 保持 draft。
- 按授权从正在运行的 Paraformer 主机只读复制四个模型/词表文件到私有 Linux cache；四个文件均与之前探测到的路径和非零字节数对应。未对来源主机启动服务、写文件或重启。
- 卡面全量命令使用 Python 3.12.3 与 `websockets==15.0.1` 退出码 0：`452 passed, 3 skipped`，约 4 分钟。3 个 skip 全部是既有 ForceAligner/VAD 模型依赖缺失；没有 HTTP decode skip。
- 同一全量命令将 websockets 约束改为未 pin，实际解析 `17.2`，退出码 0：`452 passed, 3 skipped`，约 3 分 46 秒；skip 与 15.0.1 完全相同，没有 HTTP decode skip。
- Linux 独立服务 venv 已按 `requirements-server-linux.txt` 安装并通过 `uv pip check`；Python 3.12.3、sherpa-onnx 1.13.8、ONNX Runtime 1.30.0，`CPUExecutionProvider` 可用。基线 SHA 的 detached server worktree 已建立，模型目录软链只存在于该隔离树且未进入主分支。
- 隔离服务固定在完整 SHA `820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2` 并只监听 loopback；health 的模型、协议版本、worker 状态和短 SHA 前缀与预期匹配。先后完成 3 秒无语音 WAV 的 WS v2/HTTP smoke，再逐个完成 77.184 秒 WAV 与 MP4 的 WS v2/HTTP 测量；4 项均以 `DONE` 结束，详细匿名数字见 `docs/sessions/261003-http-completion/m7-linux-baseline-evidence.md`。
- WAV：WS v2 1,972,515 JSON UTF-8 字节、HTTP 2,469,966 PATCH body 字节；MP4：WS v2 3,619,954 JSON UTF-8 字节、HTTP 18,974,961 PATCH body 字节。HTTP 重复 body 均为 0。各协议耗时、DONE/token/timestamp 与未核实参考稿差异均已落匿名 evidence；完整正文、路径、音频哈希、字幕和模型响应只留私有目录。

## 收尾状态

- 工具、测试、复现指南、匿名 Linux 实测 evidence 与阶段进度均已落盘；15.0.1 与最新 17.2 全量测试均通过（各 `452 passed, 3 skipped`）。
- Linux 首测全部完成，服务版本与工作目录 SHA 已核对，字幕保持 `unverified`。本次隔离服务已通过自有监控器停止，退出码 0 且无服务进程残留；私有模型、素材与识别结果不进入仓库。
- PR #64 的正文已补上匿名实测证据，保持 open draft；本卡不执行 ready、merge 或 deploy。下一步由 Pi 主脑独立 review，后续三平台正式基线另按最终 merged SHA 执行。

## 已知限制

- 主干 CI 基线派发时不可用，继承红暂时无法判定。
- 本卡公开记录只写匿名 fixture ID、字节数和指标；原文、素材路径/哈希、字幕与 SDK 结果正文留在派发私有目录。

## M7-A 续交补充（2026-10-04）

- 指南现列出独立 CLI 的既有导入依赖 `rich`、`colorama`，并说明 SDK 默认 WebSocket v2 使用 flac 编码的 UTF-8 JSON/Base64；`status=ok` 只表示采集完成。HTTP 超时可能已有服务端任务，指南只提供一次性的 SDK 状态查询示例，明确保留 recovery、不自动删除/重试/恢复/取消，也说明 Linux 权限结论不覆盖 Windows ACL。
- 新增 timestamp 形状测试：空列表、多 token 非单调、闭区间端点、越界和非均匀时间戳；三 token HTTP 结果通过 SDK Transcript 到 CLI 私有 JSON 字节落盘路径断言。现有静态 producer fixture 是实际 SDK 合成序列化契约；续交卡正式把它列入允许范围，但本次无需重生或修改它。脚本、SDK 与服务行为未改。
- 裸 `env -i` 和真实 systemd 用户级 one-shot unit 各执行 HTTP、WS v2 一次，共四次；均使用本轮新造的 0.25 秒合成 WAV 和本机 TCP stub，仅验证隔离 CLI、协议往返、argv/env 与私有文件权限，不代表 ASR 质量，也未读取旧素材或模型。
- 本地 targeted 两版本各 `11 passed`。全量 websockets `15.0.1` 为 `457 passed, 3 skipped, 149 warnings`；最新解析 `17.2` 同为 `457 passed, 3 skipped, 149 warnings`。三个 skip 是两项 ForceAligner 依赖和一项 silero VAD/onnxruntime 依赖缺失；无 HTTP decode skip。两条反向 AssertionError 变异均实际变红并已精确还原。
- PR #64 在 `587f219` 的 GitHub CI 中：未固定 websockets 单测 `SUCCESS`；`15.0.1` 单测有 1 项既有监督集成测试失败（`test_real_process_body_idle_timeout_is_not_fatal_and_releases_port`，456 passed/3 skipped）。测试等待 `HTTP_LISTENER_READY` 超时，捕获 stdout 含 `HTTP_DISABLED` 初始化行；测试 helper 没有把子进程 stderr 放入失败消息，故根因未定。按续交卡未重跑 CI、未改该测试/服务器、未加 timeout。gate quality、path classify 和 draft aggregator 为 `SUCCESS`；primary 为 `SKIPPED`，PR 仍是 draft。
- 最终 head `dfc1267c63575bd22a53097e6bdfcf4b40b47cae` 的新 push 自动触发 CI：`15.0.1` 与未固定 websockets 单测均为 `SUCCESS`（run#37177914589）。gate path classify、quality、ledger、draft aggregator 为 `SUCCESS`；primary 为 `SKIPPED`（run#37177914924，PR 仍为 draft）。此前 `587f219` 失败的根因仍未知；没有重跑旧 run 或更改 timeout。
- Scope-Globs 已正式由续交卡覆盖 producer fixture；续交范围的 scope 检查通过，所有实际变更文件都在授权路径中。PR #64 仍 open、base `master`、draft；禁止 ready、merge 或 deploy。
