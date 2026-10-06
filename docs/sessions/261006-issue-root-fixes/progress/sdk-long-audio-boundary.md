# 17501 秒长音频：本地真实消费边界实测（#76）

只量当前服务 + 当前 SDK 在本机的真实行为。不改源码/配置/阈值/SDK 预算，不推生产配置，
不替下游升级。服务端识别走**既有 fake ASR worker**（假引擎，非真实模型推理）。

## 结论

| 项 | 实测真实值 |
| --- | --- |
| 17501s 素材真实结果 | `AsrError(code="audio_too_long", retryable=False)` |
| 服务端真实错误消息 | `解码后样本数 230402304 超过时长上限 14400s` |
| 服务端真实消费上限 | **14400s**（来自真实抛错处的 `max_seconds`，非源码常量推断） |
| 服务端 task_end | `status=failed code=audio_too_long duration_s=14400.144 elapsed_s=25.664 segments=959 encoding=flac` |
| SDK 自动预算（真实调用值） | `duration=17501.0s → budget=70124.0s`（`_auto_budget` 实参实返，未改公式） |
| SDK 端是否被预算杀掉 | 否。终态是服务端协议错误帧，不是 SDK `timeout` |
| 正向对照（3s < 14400s） | `Transcript(is_final=True, duration=3.0)`，task_end `status=done segments=1` |
| 全量上传 | 13 帧 / 音频字节 3343556（= 素材全量），末帧 `is_final=true` |
| 进程回收 | 运行期采样命中解码子进程；停服后该 pid、fake worker pid、服务主进程均已消失 |

SDK 的 4.9h 退出**在本机这套配置下没有复现为 SDK 预算/超时**：预算实算 70124s（19.5h），
远大于 14400s 的服务端上限，先被服务端挡下的是 `audio_too_long`。本卡不解释历史成因。

## 现场身份与环境值长度

- 证据采集于 git `b52cf2477d9ba4759665274c08a195dc17104cab`（`v2.6-555-gb52cf24`）；
  仓库 `zlxlabs/CapsWriter-ASR-Server` 的本卡临时 worktree（本地绝对路径不入库）。
  首轮采集在同一代码内容上、基线提交 `dccca739131ac95e54f75bf5611508aa7ff3c20a` 完成。
- 服务端 `config_server.__version__=2.6`；SDK 包版本 0.1.0；
  SDK 实现文件 `sha256=d9b800d8a48afb174ea030a8d3de2cbc85a4de454b2aafa6dfe6e88e1ccfa5b4`。
- 环境值长度（dotenv 语义，空串=未设置，用值长度不用键是否存在）：`CW_MAX_TASK_SECONDS`、
  `CW_MAX_INFLIGHT_SEGMENTS`、`CW_MAX_TASKS`、`CW_MODEL_TYPE`、`CW_PORT`、
  `CW_SEGMENT_TIMEOUT`、`CW_UPLOAD_IDLE_SECONDS` 七个键 value_len **全为 0**。
  故 14400s 是无环境覆盖时服务端真实读到的值，且该值由真实抛错消息回显给出，不由源码常量推断。

## 素材（真实 producer bytes，两轮共用同一份，未重新生成）

ffmpeg 一次生成：`anullsrc=r=16000:cl=mono`，`-t 17501 -c:a flac -compression_level 8`（耗时 9.9s，限额 120s 内）。

| 文件 | 时长 | 大小 | sha256 |
| --- | --- | --- | --- |
| `long_17501.flac` | 17501.000000s / 16kHz / 单声道 / flac | 3343556 B | `bb3db8f87d9f11a82e436ea3e5a612e5e096dfe72497c190b71a4bab94cb27f5` |
| `short_3s.flac` | 3.000000s / 16kHz / 单声道 / flac | 8752 B | `15e2ff6a239d2b75b3e5632e4c0a36949dd6ddf7001f25d785ca84c5b86c5657` |

素材经 SDK 自己的 `_transcode` 往返后仍是 3343556 B，与 SDK 实际上传的音频字节数逐字节相等。

## 线上帧证据（纠正后的序列化边界）

**纠正说明**：首轮探针把 `_audio_frame` 的**实参** `samples_total` 记成了线上字段。真实实现
（`sdk/capswriter_asr/client.py`）是 `if is_final: frame["samples_total"] = samples_total`——
非末帧的 wire 里**根本没有**这个字段。第二轮探针改为**解析真实返回的 wire**、原样转发不改写，
并把帧字节落盘后回读核对。缺失即记为缺失。

17501s 这轮 13 帧的线上字段实测：`samples_total_present` = 12 个 `false` + 末帧 1 个 `true`。

| 位置 | index | 线上 `is_final` | 线上 `samples_total` | wire 字节 | wire 文件 sha256 |
| --- | --- | --- | --- | --- | --- |
| 首帧 | 0 | false | **不存在**（payload 无此键） | 349724 | `0c4154c684c912a80f98bf9b5fedfd26a8c448b035a016995fee21de85478e86` |
| 上传倒二帧 | 11 | false | **不存在**（payload 无此键） | 349724 | `48586d2c02bc3a78a3b8290fe9120b4de074f12e24ace7bde18c58780e4fae97` |
| 上传末帧 | 12 | true | `280016000` | 263995 | `5e5e638e0e8fcc91a30cbef67c2c0b8f6b0276323bca6b9e99a693314d040d34` |

非末帧 payload 键集固定为 8 个：`data, encoding, is_final, seg_duration, seg_overlap, source,
task_id, time_start`；末帧为同样 8 个再加 `samples_total`。`seg_duration=15.0`、`seg_overlap=2.0`
（SDK 默认，未改）。三份 wire 文件回读均 `reread_matches_forwarded_object=true`，即落盘字节就是
实际转发给 SDK 发送路径的字节。

称「上传尾帧」而非「错误附近帧」：服务端错误发生在解码推进到 14400s 之后，与上传末尾帧在时间上并不相邻。

**为什么 wire sha 与内容 sha 不同**：wire 里含每次运行随机的 `task_id` 与 `time_start`，故 wire sha
逐轮变化；音频内容 sha 与运行无关，两轮完全一致——首/倒二/末帧分别为
`103e4fba0f8cbd9506f1c4536801428cbbada6c30317afaedb8aeb6ebb5c3162`、
`7660a8a582ebda7aca53602511d39dac114a926f705b443dc5c07ecb2a9f19f5`、
`007f3222bdfbd8f5ee8234fe22cddc7d91d19f96320d36795d50fb3dfd34fec6`。

**不是伪报 17501 元数据**：末帧线上 `samples_total=280016000 = 17501×16000`，来自 SDK 对同一字节流的
真实解码；服务端 `audio_too_long` 消息里的 230402304 是服务端自己解码器数出来的，与 SDK 元数据相互独立。
上传中途收到 955 条中间结果、末条 `duration=14325.0s`，说明服务端确实边收边解、边解边出结果。
整次调用墙钟 43.2s（外部执行限额 300s 内完成）。

## 日志采集方式（观测手段，非产品机制）

探针在真实 logger 上**额外挂了一个 FileHandler 并把级别设为 INFO** 用于收集 task_end 等行。
这是采集手段：**产品文件零修改**，产品 logger 配置未被改动；采集到的这份日志**不代表**原部署的
console/文件配置（原部署 logger 的真实验证是另一条线，见 #87 的单独验证，本卡不复述、不代跑）。

## 源码 ↔ 既有长期测试（本卡不新增 checker/接口/日志/配置）

| 真实行为 | 既有断言 |
| --- | --- |
| 服务端 `_check_task_duration` → `audio_too_long` | `tests/test_protocol_v2.py::test_frame_limit_and_decoded_duration_limit`（`CW_MAX_TASK_SECONDS=10`） |
| 解码超长时的解码/抛错先后与背压 | `tests/test_decoder_abort.py:335`（`CW_MAX_TASK_SECONDS=5`） |
| SDK 预算 = 解码时长×4+120（取解码样本数，非容器时长） | `tests/test_sdk_samples_total.py::test_deadline_uses_decoded_sample_count` |
| 未知类型/异 task_id 回帧被忽略 | `tests/test_sdk_client.py:246` |
| `audio_too_long` 在协议错误码集合内 | `core/protocol.py:22` + `sdk/capswriter_asr/client.py:65` |
| `samples_total` 只在末帧序列化 | 协议定义见 `core/protocol.py`；本卡实测见上表 |

17501s 端到端实测**没有**长期自动断言（既有测试都用小阈值替身与短音频），按「不加新 checker」只留本文件与探针产物。

## 证据产物（均保留，未提交、未删除）

- 首轮（实参口径，序列化边界有误，仅留作过程记录）：
  `/tmp/cw76probe/probe_17501.py`（14764 B，`sha256=93c22891…40a2`）、
  `/tmp/cw76probe/probe_result.json`（10290 B，`sha256=4d28e0c3…cf31`）、`/tmp/cw76probe/server_probe.log`。
- 纠正轮（wire 口径，本文件表格与结论的数据源）：
  `/tmp/cw76probe2/probe_17501_wire.py`（`sha256=eafaf7be…aab1`）、
  `/tmp/cw76probe2/probe_result.json`（`sha256=5701d2ae…63d2`）、
  `/tmp/cw76probe2/wire_frames/{first_frame_00,second_last_frame_11,last_frame_12}.json`、
  `/tmp/cw76probe2/server_probe.log`。
- 复算：`PROBE_REPO=<repo> PROBE_OUT=/tmp/cw76probe2 PROBE_MATERIAL_DIR=/tmp/cw76probe timeout 300 python3 /tmp/cw76probe2/probe_17501_wire.py`

harness 选项沿用既有 `ManagedFakeServerHarness` + 仓库既有 e2e 测试的假引擎设置，未改任何产品配置。
采集过程中前两轮曾报 `inference_failed`（假引擎准备阶段未完成），**原因未复核、结论保持未知**，
不据此对产品行为下判断；纠正轮与首轮末轮的 17501s 终态一致。

## 本结果**不等于**

不等于下游已 pin 该版本、不等于生产已升级、不等于真实 ASR 引擎在长音频上的性能表现、
不等于 4.9h 历史退出的根因已被证实。