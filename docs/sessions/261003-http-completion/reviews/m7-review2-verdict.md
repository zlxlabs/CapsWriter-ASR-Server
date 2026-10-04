# M7 baseline 工具独立终审

failure-visibility: p2-only

## 判定

**P2-only，接受本轮不修；没有 P1。** 本审查只针对冻结提交 `820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..45c0c2c40abf743437eb2deedce8c407855b7bd5`，风险级别 internal。未追审查中的分支 HEAD；没有修改服务代码、SDK、部署配置或原 producer fixture。

## 契约与实现索引

- 原协议 [`docs/reference/protocol.md`](../../../reference/protocol.md#L76)：文件 final 结果的 `tokens`/`timestamps` 必须等长，空识别可为两个空数组；timestamp 可重复，且不承诺固定粒度。HTTP 上传是原始文件字节。错误帧/连接异常不得当成功。
- 指南 [`docs/guides/http-baseline.md`](../../../guides/http-baseline.md#L3)：`status=ok` 是采集与落盘结果，不是识别质量通过；HTTP source、16 kHz mono PCM、SDK 发出的 PATCH body 与控制 JSON 分开计量；WS v2 按 SDK 默认 FLAC 路径量实际 `send()` 的 JSON UTF-8 字节，Base64 音频字节另列。指标不包括 headers/TCP/TLS/WebSocket frame 开销。
- 采集器 [`scripts/_baseline_http_ws.py`](../../../../scripts/_baseline_http_ws.py#L223)：`run_ws_v2` 明确调用实际 SDK `transcribe_file(..., encoding="flac")`；`run_http` 使用 SDK HTTP producer。`PayloadMeter.record_ws` 区分文本 JSON 与 binary，`record_http` 读取 HTTPX 已序列化的 Request body。健康检查要求 loopback、server SHA/model/worker 状态；帧编码要求实际依据 SDK `_check_server` 和真实 `send()`，没有从 health 单独猜帧 type。
- SDK 来源：[`sdk/capswriter_asr/client.py`](../../../../sdk/capswriter_asr/client.py#L213) 负责 v2 health/encoding 校验，`_audio_frame` 与 `_transcript` 位于 249、284 行；[`sdk/capswriter_asr/http_client.py`](../../../../sdk/capswriter_asr/http_client.py#L572) 的 `submit_file_http` 使用 `retries=0` 并先持久化 recovery，状态查询与结果反序列化位于 677、739、782 行。HTTP final 结果校验 `is_final`、字段类型及 token/timestamp 等长。
- 私有输出 [`scripts/_baseline_http_ws.py`](../../../../scripts/_baseline_http_ws.py#L364)：Unix 私有目录拒绝 group/other 权限；最终 JSON 用独占创建及 `0600`。`_result_metrics` 在 385 行把 token 数、timestamp 数、单调性、token 覆盖、server/source 时长范围各自记录；`safe_summary` 在 538 行只投影匿名 ID、字节/指标与文件名，不含 transcript、source path 或 credentials。外层异常以 `BASELINE_FAILED`、异常类型/错误码写 stderr 并非零退出。
- Producer golden [`tests/fixtures/http_baseline_producer.json`](../../../../tests/fixtures/http_baseline_producer.json#L1)：保留 HTTP SDK producer 的创建 JSON、原始 PATCH 字节与 commit 请求，以及 `client.py::_audio_frame via transcribe_file` 的 v2 文本帧。测试 [`tests/test_http_baseline.py`](../../../../tests/test_http_baseline.py#L138) 从本机 TCP 捕获真实 SDK HTTP 请求后逐项与 golden 比较；173 行测试通过实际 WebSocket `send()` 比较 v2 帧。当前 SDK package version 为 `0.1.0`，固定 CLI 环境为 `websockets 15.0.1`、`httpx 0.28.1`；未把包版本写进 JSON fixture 本体，版本可由同一冻结 SHA 的 `sdk/pyproject.toml` 和本次运行记录还原。
- 质量字段测试在 [`tests/test_http_baseline.py`](../../../../tests/test_http_baseline.py#L323)：覆盖空、非单调、端点、越界、非均匀形态。CLI HTTP 集成测试在 218 行，实际经过 SDK/网络边界，核 stdout 私密内容排除、private JSON 序列化字节及 `0600` 权限。空参考稿在 338 行发请求前失败。

## 真实消费验证

用 0.25 秒合成 WAV 和 loopback HTTP/WS stub，ASR 计算由 stub 提供，不作识别质量推断。执行指南的 `uv run --no-project --python 3.12` 依赖路径，通过干净 env allowlist 真正启动 CLI；在裸 shell 和 transient systemd 各跑了 HTTP、WS v2 的空、非单调、多 token、端点、越界、非均匀五种结果，共 20 次 CLI。argv、env key、请求 payload/帧、stdout 摘要及 private JSON 哈希保留在仓库外本机合成 trace；Authorization 值未归档。

20 次均返回采集状态 `ok`。40 次被 CLI 调用的 ffmpeg 子进程看到显式 marker；wrapper 随后执行真实 `/usr/bin/ffmpeg`。SDK 版本为 `0.1.0`，CLI 环境 `websockets 15.0.1` / `httpx 0.28.1`，ffmpeg 为 `6.1.1`。实际 WS `send()` 收到的是一条包含 `encoding=flac`、`samples_total` 的 JSON 文本帧，`data` 解码为 FLAC；没有 binary frame。HTTP PATCH body 与 synthetic WAV 容器字节相同；PCM 与 FLAC 解包计数分列，没有把源容器、PCM、Base64、JSON、binary 或网络开销混为一个数字。

每种时间戳形态都贯穿真实 SDK 反序列化、最终 private JSON 与 stdout。空列表的单调指标为 `true`，但覆盖为 `false`；非单调与越界结果仍显示 `status=ok` 并保留相应 false 指标，未作为 quality gate。端点 timestamp 允许 `0` 与音频末端值。无 reference 输出 `not_provided`/CER `null`；合成 SRT 只标 `unverified`，CER 仅表示与该稿差异。`--reference-status verified` 是操作者提供的来源标记，工具不替操作者鉴真，也不代表 ground truth。

全部 20 组私有目录/文件权限分别为 `0700`/`0600`；逐份读取最终私有 JSON 字节并核对与实际文档序列化一致。stdout 未出现 synthetic 私有正文、输入路径或 marker。没有 Windows 环境，因此没有以 Unix mode bits 推断 Windows ACL。

## Recovery 与同 ID 分诊

真实 HTTP CLI + SDK stub 验证：提交后状态一直 RUNNING 导致调用超时，CLI 返回非零，recovery 保留且权限 `0600`；同 fixture ID 再跑得到 `recovery_exists`，没有新的上传请求；SDK `http status` 只发一次 job-status GET、不取正文；换新 ID 会发出独立上传并取得新 job。这四种状态没有互相伪装，HTTP transport retries 为 0。

**P2（接受不修）**：同一个成功 fixture ID 在同一 private dir 已有 `<id>-http.json` 后再次运行，CLI 会新建一个 HTTP job、取得结果，之后独占创建 JSON 报 `FileExistsError`；旧 JSON 不变，但该新任务的 recovery 已在 HTTP 成功路径清除，不能从 CLI 本地恢复。此路径由 owner 复用本地 fixture ID 触发；失败明确可见，属于 loopback 单用户工具，不会静默覆盖旧文件或伪报成功；用新的 anonymous fixture ID 可以重测。按 internal P1 两问：第一问“能触发”已在真实 CLI 路径实测；第二问“后果不可接受”不成立，后果是一次可见失败和重复本地计算，数据可用新 ID 重测，因此不升 P1。本轮只记录，不扩修复范围。

## CI 与外部扫描

- GitHub run `37177435228`、head `587f219da747f4c378d72b0ce9933bf0d4875c91`：固定 `websockets==15.0.1` 的 job `111362889352` 在 `运行 pytest` 失败，同 run 的未钉 websockets job 成功。按错误白名单只提取到 `AssertionError` 与 `tests/test_http_supervision.py::test_real_process_body_idle_timeout_is_not_fatal_and_releases_port`；失败栈落在 `_wait_for(HTTP_LISTENER_READY=)`，发生在 idle-body 请求前。底层启动原因 **unknown**，没有读取或回显 raw stderr/body。
- 该存量测试在本机 CI 等价依赖下，以清洁 shell 与真实 transient systemd，分别用固定 15.0.1 和 latest 17.2 运行；四次均为 `1 passed`。全套 pinned 15.0.1 与 latest 17.2 各为 `457 passed, 3 skipped`；skip 是本机未安装对齐器/VAD 模型依赖。历史红未复现，也不据此猜 CI 根因。派发卡提供的主干基线查询不可用，因此“继承红/新红”比较标记为未能判定。
- PR 64 当前 head 仍为冻结 SHA、状态 draft。两套 CI tests 均 SUCCESS；gate primary 与 OCR 为 SKIPPED。这个 draft 状态没有完整主审结论。
- 隔离输入的新 OCR envelope：`status=reviewed`、`coverage=complete`、`findings=[]`、`reason=primary_selected`；二次 verifier 因没有 finding 而 `verify_status=skipped`。它是完成扫描且无 finding，不表述为 skipped scan。

## 四问与范围结论

1. 只审 `820c3a2..45c0c2c`；新增范围是 guide、collector、producer fixture、tests。原 Linux evidence、原 progress、实现报告、前 review/verdict 和录音/字幕未读。
2. 新增 `PayloadMeter` 与 transport wrapper 用于从 SDK 外部观察 HTTPX 的实际序列化 body 和 WebSocket 的实际 `send()`；本次两个协议路径分别消费，未发现仅为未来场景通用化的新增层。
3. 没有新增 fallback、retry 或质量通过状态。HTTP 的完成状态轮询是当前任务内等待；超时后保留 recovery，之后只有显式 status 查询或新的 fixture ID 才有后续网络动作。
4. summary 与 private JSON 由同一组结果指标投影，不存在第二个独立质量判定点。非单调、空、越界形态保留为事实字段而非合成总体验收值。

结论：本 delta 没有 P1；只有上述 owner ID 复用的可见 P2，接受不修。failure-visibility 固定为 `p2-only`。
