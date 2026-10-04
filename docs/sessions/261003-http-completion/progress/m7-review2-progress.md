
## 1. 代码初审（冻结 SHA 45c0c2c）
- 按先读的协议与 guide 对照：`status=ok` 是采集/落盘状态；token/timestamp 计量字段不构成识别质量判定；HTTP source、PCM、WS FLAC Base64 JSON 口径在文案中分开。
- 初审了本轮新增的 guide、collector、producer fixture 与测试；冻结增量内没有服务实现或 SDK 改动。
- 初步未见把空 timestamps 的单调结果当作覆盖，或把非单调/越界指标升级为 quality pass 的代码路径。
- 待外证核实的候选：成功后复用同 fixture ID 可能撞独占私有 JSON；fixture 形态目前未单独写 SDK package version。均暂列 P2 候选，不改实现。
- 下一步：独立跑真实 CLI/网络消费、CI 对照和断言反向变异，再收口定级。

## 2. 外部与运行证据
- 全套 pytest：固定 `websockets==15.0.1` 为 457 passed / 3 skipped；未钉版本解析到 17.2，同为 457 passed / 3 skipped。skip 是缺本机对齐器/VAD 模型。
- 20 次真实基线 CLI 消费（HTTP、WS v2 × 五种合成 timestamp 形态 × 裸 shell、systemd）全部成功；40 次真实 ffmpeg 子进程均看到显式白名单 marker。保留实际 argv、env key、SDK payload 与 stdout/private JSON 哈希的本机合成 trace，不进 Git。
- 私有 JSON 实际字节可重读；20 组目录/文件权限分别为 0700/0600，stdout 不含 synthetic 私有正文、源路径或 marker。WS 实际 send 是 flac Base64 JSON 文本帧；HTTP PATCH 是原始 WAV 容器字节。未做 ASR 质量或三平台量测。
- 空、多 token 非单调、端点、越界、非均匀 timestamp 均经 SDK 反序列化到最终 JSON/stdout；越界与非单调仍是 `status=ok`，指标没有变成质量 gate。无参考稿为 `not_provided`/CER null；提供的合成 SRT 标 `unverified`。
- timeout / same-ID recovery / one-shot status / new-ID 试验符合文档；另发现成功后重用已产出 JSON 的同 ID 会创建新 HTTP job，最终 `FileExistsError`，新 recovery 已删。仅为 owner 误复用本地 ID，失败可见、旧 JSON 完好、可用新 ID 重测，暂定 P2 接受不修。
- CI run 37177435228 的 pinned-15 job 在 `test_real_process_body_idle_timeout_is_not_fatal_and_releases_port` 等不到 `HTTP_LISTENER_READY=`，发生于 idle-body 请求前；根因 unknown。该测试在 pinned/latest 的清洁 shell 与 transient systemd 各跑一次均通过，旧红未复现。45c 的两套 CI tests SUCCESS，primary/OCR SKIPPED（PR draft）。
- OCR 状态 `reviewed`、coverage `complete`、findings 空；它的二次 verifier 因零 finding 为 `skipped`。Windows ACL 未在此环境测量，不用 Linux chmod 代证。
- 下一步：按 P2-only 收口 verdict，完成远端提交和 clean 核验。
