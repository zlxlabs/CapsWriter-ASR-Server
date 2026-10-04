<!-- succeeded -->
# M7-A 真实基线工具独立首审 verdict

failure-visibility: p2-only

## 结论

固定范围的冷审已完成。发现两项 P2、一项 P3；没有满足 P1 两问的 finding。采集成功只代表数据采集流程完成，不代表识别质量合格；未用真实录音、模型或未核实参考稿作质量结论。

- 固定提交范围：`820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..3329467c9c6694d790c2378f534a57919f2f6afa`
- 风险等级：`internal`
- 仅读取 collector、tests、producer fixture、guide、实际 SDK 与原协议；新增的 Linux evidence 和实现 progress 文件只看见路径，未读取内容或数字。
- 范围 `git diff --numstat` 合计 1084 行新增，其中本审可读的 collector/test/fixture/guide 共 995 行。派卡的 400/650 行字段与固定审查范围不是同一计数口径；本轮按卡面要求完整审固定 SHA，没有改实现。

## Findings

### P2-1：Linux CLI 命令少列两个导入期依赖

**违反的不变式：** 指南列出的隔离命令应能启动 CLI；依赖失败须经统一失败出口给出非零 `BASELINE_FAILED`，不能在入口外直接崩溃。

`_baseline_http_ws.py:33` 顶层导入旧脚本的 `_cer`；该模块导入 `core.protocol` 会初始化 `core`，继而需要 `rich` 和 `colorama`。指南 Linux 命令 `docs/guides/http-baseline.md:51-52` 只列 `numpy`、`soundfile`、`websockets`、`httpx`，没有列 `rich`、`colorama`；同页测试命令第 64 行却包含这两个包。

在临时 systemd 单元的隔离环境按 CLI 依赖清单启动，真实执行分别在导入期遇到 `ModuleNotFoundError: rich` 和 `ModuleNotFoundError: colorama`。异常发生在 `main()` 的 `try` 之前，进程非零退出但没有 `BASELINE_FAILED`。临时环境补齐二者后，HTTP/WS CLI 成功完成合成边界捕获。错误没有包含输入、参考稿或凭据内容。

定级为 P2：文档化主路径确实触发，但失败可见且只阻止本次本机基线采集；操作者补齐依赖即可继续，没有静默错误数据。现有 tests 没有锁住这条隔离依赖契约。

### P2-2：HTTP 超时遗留恢复文件，同 fixture ID 无法直接重跑

**违反的不变式：** 一次失败的采集不应留下没有运行手册出口、且会阻止下一次显式运行的持久状态。

`_run()` 为每个 fixture 固定使用 `<fixture-id>.http-recovery.json`（`scripts/_baseline_http_ws.py:457`）。`run_http()` 的清理语句在 `try/finally` 之后（第 273 行），只会在整段调用成功后执行；超时会跳过它。实际 SDK `submit_file_http()` 在恢复文件已存在时直接报 `recovery_exists`（`sdk/capswriter_asr/http_client.py:586-588`）。

临时 loopback HTTP 服务实测：一次短截止时间运行返回非零 `BASELINE_FAILED`、stdout 为空，但留下恢复文件；同一 fixture ID 的下一次显式 CLI 运行立即以 `recovery_exists` 失败。实际文件权限为 `0600`，父目录为 `0700`；文件正文未读取。指南没有说明如何安全恢复、清理或为重跑选择新的匿名 ID。定级为 P2：真实可触发且阻止同 ID 继续测量，但不会把失败伪装成成功，也没有对外数据损坏；可用新 ID 或受控人工处置恢复。没有要求加入自动重试。

### P3-1：新增模块含未使用的 `shutil` 导入

**违反的不变式：** 新增代码不应保留无消费者的导入。`rg` 在 `scripts/_baseline_http_ws.py` 中只找到 `import shutil` 一处；该模块没有引用它。没有证据表明当前 lint gate 会因此失败，故列为 P3，不阻塞。

## 四问

1. **计量是否来自真实 producer？** 是。HTTP 包装点读取 HTTPX 实际 Request body，WS 包装点读取 SDK 实际 `send()` 参数；系统d 与裸 shell 都由 CLI 驱动真实 SDK、loopback 网络、ffmpeg 和文件写入。HTTP PATCH/控制 JSON 的报告字节数与本机服务实际收到的请求对上。HTTP 上传原始 WAV 字节、解码后的单声道 PCM、WS JSON UTF-8、Base64 字符数、Base64 解包后的压缩 FLAC 字节分别统计；未把 FLAC 解包字节命名为 PCM，也未声称 TCP/TLS 总流量。

   SDK 当前默认编码为 `flac`，collector 显式传 `flac`；真实发送帧是包含 `encoding`、末帧 `samples_total` 与分段参数的 JSON 文本帧。健康端点版本号没有代替实际发送帧契约。当前 SDK transport retries 为 0，collector 每次创建一个上传；计量器的重复 offset 单元测试只验证同一偏移、相同 body，跨 upload ID 的重复路径在该单次 producer 调用中不可达。成功报告中的发送计数与服务端捕获一致；失败运行不落成功 JSON，未保存部分尝试与完成发送的双计数。

2. **落盘和 stdout 是否守住私有边界？** 合成 CLI 的实际 stdout 不含输入路径、参考稿路径/正文、合成识别正文或 env sentinel。实际写入 JSON 的字节与规范序列化结果逐字节相同；Linux 输出目录/文件实际权限为 `0700/0600`。已有输出文件、超时、缺失 ffmpeg 和不安全目录权限均以非零 `BASELINE_FAILED` 结束，没有 status=ok。超时遗留恢复文件见 P2-2。Windows 路径只做源码检查：代码在 Windows 跳过 POSIX mode 检查，本轮没有验证或声称 Windows ACL 安全。

3. **参考稿和识别指标是否被表述成质量结论？** 没有。来源状态是显式 `verified/unverified`；未给参考稿时状态为 `not_provided`；CER 字段标记为相对参考稿，指南明确说未核实参考稿不能代表正确率。最终 payload 要求 final 且 token/timestamp 数量一致；私有 JSON 保留时间戳、计数、单调性及服务时长/源时长区间字段。空数组时覆盖和区间字段为 false，`timestamps_monotonic` 会因 `all([])` 为 true，但没有 quality-pass 字段，指南要求同时检查数量和覆盖。仓库测试只用单 token timestamp，没有锁定空数组、多 token 非单调、区间边界或非均匀分布；这些质量形态仍属未覆盖项，不据此声称识别质量合格。

4. **是否存在未经证明的 P1、fallback 或多余抽象？** 没有 P1。OCR 的多声道 finding 经实证驳回；实际使用方式是本机串行基线，P2 项的后果可恢复。新增 meter/transport wrapper 是读取真实 SDK producer payload 所需；没有增加重试、静默降级或额外配置层。HTTP/WS 的临时服务仅 stub 识别结果，没有加载权重或触达生产。

## OCR 前置扫描与人工分诊

OCR envelope 完整：`status=reviewed`、`reason=primary_selected`、`cli_status=complete`、`coverage=complete`；核验状态 `completed`，3 项均核验，2 项确认、1 项驳回、0 项不可核验。OCR 的原始 severity 仅作输入，最终分诊如下：

- OCR `high`：16 kHz 立体声 WAV PCM 字节少算。**驳回**：代码统计的是转为 16 kHz 单声道后的目标 PCM；合成双声道 WAV 的 fast path 字节数与实际 ffmpeg `-ac 1` 解码字节数一致。
- OCR `medium`：失败遗留恢复文件并阻止同 ID 重跑。**确认，P2**：源码路径与临时服务实测一致。
- OCR `low`：未使用的 `shutil` 导入。**确认，P3**：当前没有对应 lint 失败证据。

OCR 包装命令已产生并核读完整 envelope；其外层 zsh 汇报语句使用只读变量 `status` 而退出 1，没有重发 OCR 请求。envelope 自身报告 reviewed/complete，人工分诊仍覆盖全部三项。

## 不变式测试索引与未测项

- HTTP producer 请求体/分块：`tests/test_http_baseline.py::test_http_sdk_producer_matches_retained_request_fixture`；实测本机 TCP 捕获并与 `tests/fixtures/http_baseline_producer.json` 对比。
- WS v2 producer 帧：`test_ws_meter_observes_actual_sdk_v2_send_payload`；实测 SDK `send()` 文本帧与 fixture 对比。fixture 的预编码音频字节是序列化用 synthetic bytes，不表示有效 FLAC；本轮系统d/裸 shell 又用真实 ffmpeg 对同源短 WAV 捕获到 FLAC 文本帧。
- CLI stdout/私有 JSON 字节与 HTTP producer：`test_cli_http_producer_payload_and_private_json_bytes`；实测同样对比实际写入对象。
- 归一化/空参考失败：`test_srt_normalization_removes_cues_and_merges_wrapped_text`、`test_empty_reference_fails_loudly_before_health_or_upload`。
- 重复 offset：`test_http_meter_counts_emitted_patch_and_repeated_offset_bytes` 直接调用 meter，不是 SDK 重传路径；当前 SDK 自动重试为 0，真实捕获未出现重传。
- 没有仓库测试覆盖：systemd 白名单依赖集合、私有目录拒绝宽权限、超时后恢复文件生命周期、同 ID 重跑、空/非单调/范围外 timestamps。临时验收脚本覆盖了本轮 systemd/裸 shell、权限、失败路径和两个独立红验，但不替代仓库回归测试。
- 两个独立红验均以实际 CLI 输出/服务端捕获为基准：把实收 payload 计数注入 +1 后断言触发 `AssertionError`；把实际 stdout 的参考状态改为 `verified` 或注入参考正文后隐私/状态断言触发 `AssertionError`。

## 验证记录

- `git diff --check HEAD^ HEAD`：通过；另对完整固定范围执行 `git diff --check 820c3a2..3329467`：通过。
- `tests/test_http_baseline.py`：`websockets==15.0.1` 与 `websockets==17.2` 各 6 项通过。首次隔离调用因执行命令未包含 `pytest-asyncio` 而在 conftest 导入时失败；补齐指南所列依赖后两轮通过。
- 临时 systemd 白名单环境：`websockets==17.2`；裸 shell：当前全局 `websockets==16.0`。两协议使用同一合成 WAV、实际 CLI、实际 SDK 与随机 loopback 服务。没有外网、模型权重、真实识别或真实媒体。
- `git status` 起始时干净；当前新增的仅为本 review progress 与 verdict 文档。
- 派卡注明主干基线不可用（`gh api request failed`）；本审未读取实现 Linux evidence 或其数字，也未查前审结论。
