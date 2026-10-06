# DESIGN-note：#87/#76/#85/#81 四项工单根治的设计固化（含基线最小复现）

- 会话：`261006-issue-root-fixes`
- issue：#87（WS 解码错误传播）、#76（SDK 停滞判据）、#85（测试资源回收）、#81（历史产物清账）
- 基线：`origin/master` `e849c21748392ad848131e07ff17d32e4cc83a8b`（含 PR #84、#86）
- 阶段：planning（本卡只设计与复现，不实现修复、不改测试代码）
- 本轮实测 scratch：`/tmp/capswriter-261006-preflight-dlg-20261006-023326-a6bee5/`
- 首版 commit：`7664c17`（事实订正见本文件末尾「文档订正记录」）

## 目标

把用户已授权的四条根治方向固化成可实现、可验收的 spec，并在最新主干上用有边界探针核实缺陷真实路径，使后续四张实现卡不再靠工单推断开工。

## 非目标

- 本卡不实现任何生产修复、不改 `tests/`、不开 PR、不 merge、不动 #82 范围。
- 不新增看门狗/重试/fallback/progress 协议，不复活旧 gate/workflow/锁文件，不写全仓孤儿扫描工具。
- 不部署、不访问生产、不替下游升级 SDK；不把 SDK 合入当作 #76 关单。

## 为什么不是分区 / 删除 / 约定

- **分区**：#87 的缺陷在 WS 路径的 `AudioDecoder` 公共迭代接口上；HTTP 用的是独立实现 `FileSourceDecoder`（`core/server/http_file_runner.py`），**不是同一接口的第二消费方**，其「迭代读完 + `finish()` 检查退出码」已整体保证失败可见。把两者写成共享契约会逼出一批没有证据的改动，因此本批 HTTP 不改。
- **删除**：本批就是**删冗余**——删掉 #76 的**逐帧 send 时限**（一次 send 的耗时不是任务是否推进的证据），删掉 #87 中**「`_END` 无条件当正常结束返回」**带来的歧义（已知非零退出 / 未对齐必须沿迭代传播）。删的是这两处冗余判据，不是「有界失败」设施本身：自动总预算、idle 上限、错误码、取消纪律全部保留。
- **约定**：靠文档要求调用方「不要在发送阻塞时长时间不发结果」无法执行；停滞必须由 SDK 自己按真实双向进展判定。

## 方案要点与已否决方案

### 卡 A：#87 解码错误沿迭代传播（范围限 WS 路径）

- **唯一现已知的失败条件是 `_reader_error`**：ffmpeg 非零退出、f32le 输出未按 4 字节对齐、以及读取协程捕获的其它异常。这些必须沿迭代传播——`pcm_chunks()` 在遇到 `_END` 且 `_reader_error` 非空时抛 `decode_failed`，不得静默 `return`。
- **stderr 有内容不等于错误**：returncode 0 的 ffmpeg 同样可能写日志。`_stderr_tail` 只用于错误消息的细节补充，禁止把「stderr 非空」独立当作失败条件。
- 合法 EOF（returncode 0 且 `pending` 为空）：迭代正常结束，`finish()` 正常返回，二者不得混淆。
- `finish()` 保持「幂等 + 复抛已记录错误」：迭代已抛过错误时 `finish()` 仍以同一 `decode_failed` 结束，调用方不依赖抛错位置。
- **无明确 error 帧的真正分支（按源码核对）**：`_feed_compressed`（`core/server/connection/ws_recv.py:256-275`）见 `cache.decoder_task` 正常完成即 `return False` → 其调用方是 `message_handler`（`:381-382`）→ `message_handler` 的 `False` 又被 `ws_recv.py:613` 的 `if not await message_handler(...)` 直接 `return`，整条接收协程结束且**不发任何错误帧**。这才是要修的分支。
- 不要混为一谈的另外两处：`message_handler` 内的 `if not await cache.decoder_task: return False`（`:393-394`，末帧路径）同样是静默结束；而 `_receive_compressed_frame`（`:401-419`）发现消费协程在末帧前结束时，是 `consumer.result()` 之后抛 `RuntimeError('压缩音频消费协程在末帧前结束')`，走 `internal` 路径，**不是**「无 error 帧」那条分支。
- 修法方向：解码任务非正常结束一律当作错误，复用既有 `queue_error_and_close(..., e.code, e.message, False)`（`ws_recv.py:616-621` 一带的现成写法）发出真实 `decode_failed` 帧，发完回收 decoder 任务。
- **HTTP 本批不改**：`core/server/http_file_runner.py` 的 `FileSourceDecoder`（`:136-170`）是独立类，`pcm_chunks()` 迭代读尽后检查未对齐、`finish()` 检查 returncode，迭代 + finish 整体已保证失败可见。**只有未来实测出独立缺口才另开卡处置**，不得机械套 WS 改法。
- 并发收尾：末帧、取消、错误三条路径都不留协程/子进程（`AudioDecoder.cancel` 已是公共出口，`_read_stdout` 的 `_END` 投递在异常路径也执行）。
- 测试资产：WS 端到端错误帧用**独立新文件** `tests/test_ws_decode_failure.py`。卡 A 与卡 C **不得同时改** `tests/test_ws_progress_watchdog.py`，保持真实精确的并行 Scope。

### 卡 B：#76 SDK 以真实双向任务进展判停滞

- 连接建立后立即进入进展监视，不再等 `upload_done` 才启动 `idle_watch`。
- 「进展」= 成功发送一帧 **或** 收到一条可识别的、与当前 `task_id` 匹配的已知消息（`result` / `error`）。
- 未知 `type`：按协议忽略，**不得延长 idle**。记录现有行为差异——现实现 `_receive`（`sdk/capswriter_asr/client.py:301-305`）在解析前就把任意消息塞进 `idle_messages`，即未知类型当前会刷新；本卡收窄它属于有意的行为变更，须在测试里显式锁定。失败形态要求：收窄后应在 **idle** 上暴露，而不是拖到等总预算才失败（总预算只是绝对墙钟兜底，不能当成设计出来的判据）。
- 上传结束后发送不再刷新（上传已无剩余动作）。
- 有中间结果的背压不因单次 send 时长失败：**删除逐帧 `asyncio.wait(timeout=idle_timeout)` 这一判据**，改为「距上次真实进展超过上限」。`idle_timeout` 本身保留，语义变为「距上次真实进展」的上限。
- 保留自动预算 `duration*4+120` 与显式 `deadline_total` 绝对墙钟上限，数值与默认值一字不改。
- 异常裁决：沿用现有 `FIRST_COMPLETED` + `ordered`（upload → receive → idle）上抛，不得只在 `gather(return_exceptions=True)` 清理里把 send 错误吞掉。
- 错误消息只报阶段 / 计数 / 距最后进展时间；不得由「send 阻塞」直接断言是服务端责任。
- 保留 #65/#67 的取消传播纪律：`asyncio.wait` 而非 `wait_for`，`finally` 取消并回收全部子任务。

### 卡 C：#85 受控子进程可靠有界回收

- 工单原文「先 stop 后 kill」与源码不符：`tests/test_ws_progress_watchdog.py` 的 S1/S2 `finally` 已是先 `_force_kill_ffmpeg` 再 `server.stop`。**待证机制**：具体卡死点仍未实测，本卡不写结论。
- **根治点是资源 owner，不是单个测试的 `finally`**：`tests/harness/server.py` 才是真正持有与回收受控子进程的 owner（`ManagedFakeServerHarness`、`ManagedHttpServerHarness`，含 `killpg` 收掉自己 fork 出去的 Manager 与识别子进程）。禁止把根治做成「只在某个测试的 `finally` 里补一刀」。
- 契约：主体断言失败时仍有界非零退出；受控子进程全部被回收；原始异常在报告里可见。
- 不以 `SIGCONT` 作为杀已暂停进程的必要步骤；不以外层 `timeout` 代替内部正确回收；只按记录的 pid / 进程组回收，不按进程名匹配全局对象。
- 测试资产：受控子进程回收回归用**独立新文件** `tests/test_harness_shutdown.py`。

### 卡 D：#81 历史产物按当前消费者分类

- 逐文件给出四栏去向：当前需求是否覆盖 / 当前是否被引用 / 历史 SHA / 去向（保留进主干 / 归档 / 不合并）。
- 当前交付所依赖的最终审查结论与否决证据进主干，并标注历史适用范围；旧过程文档归档可追溯。
- 不盲合旧六文件；不删除未归档分支与部署；不把「squash 后非祖先」当代码未交付；不以待删数量当完成条件。

### 并行边与已否决方案

- 卡 A 与卡 B 无真实接口依赖：`decode_failed` 已是双方既有错误码；卡 C 独立。三卡可并行，Scope 不重叠（见拆卡表的文件级约束）。
- 本设计随卡 A 的 PR 交付；卡 B/C/D 的实现基线仍取当时最新 `origin/master`，**不以本设计分支作 Base**。
- 已否决：逐点 `await` 加超时；只关 socket 不 cancel；恢复 ping / 连接寿命上限；调大 idle 常量；新增 progress 协议；自动重试或降级；盲合全部历史分支与旧 workflow。

## 关键不变式

1. [实测·见证据 A] 非零退出的 ffmpeg 被直接消费时，`pcm_chunks()` 静默 `return`、`finish()` 才抛 `decode_failed`。现路径：`core/server/connection/audio_decoder.py:128-159`（记 `_reader_error` 后投 `_END`）与 `:172-185`（遇 `_END` 直接 `return`）。拟新增测试：`tests/test_audio_decoder.py` 断言中途非零退出时迭代即抛 `decode_failed`，并保留合法 EOF 对照（迭代正常结束、`finish()` 无错）。
2. [待新增测试] `decode_failed` 经真实 WS 到达客户端：错误帧 payload 与连接关闭顺序确定，decoder 任务与 ffmpeg 进程均被回收。拟新增于**独立新文件 `tests/test_ws_decode_failure.py`**，复用 `tests/harness/` 现有假服务端夹具。
3. [待新增测试] 卡 B 八项 SDK 矩阵（见验收路径）全部经真实 `transcribe_file` 入口，不只调内部函数。
4. [待新增测试] 卡 C：受控子进程在主体失败路径上也被回收，且退出码非零、原始异常可见。拟新增于**独立新文件 `tests/test_harness_shutdown.py`**；回收保证归属 `tests/harness/server.py` 的 owner 职责，不是单个测试的 `finally`。
5. [待新增测试] 卡 D：清账表逐文件有去向，且被当前交付依赖的证据在主干可查。

## 本轮实测证据（探针，观察级，非验收）

### 探针 A：真 ffmpeg × 直接消费 AudioDecoder（已完成，观察级）

- 脚本：`/tmp/capswriter-261006-preflight-dlg-20261006-023326-a6bee5/probe_a_decoder.py`，输出 `probe_a_out.txt`。
- 入口：`uv run --no-project --python 3.12 --with numpy --with rich --with websockets --with colorama python probe_a_decoder.py`，退出码 0。
- 合法对照：真 ffmpeg 生成的 flac（14420 字节）→ ffmpeg pid 362910 / returncode 0 / 迭代正常结束 / 消费 16000 样本 / `finish()` ok。
- 故障注入：`fLaC` 魔数 + 垃圾负载 2052 字节 → ffmpeg pid 362956 / **returncode 251** / `_reader_error` 已是 `AudioDecodeError(decode_failed)` / 但消费协程 **`returned_normally`，0 样本、迭代未抛** / `finish()` 才抛 `AudioDecodeError:decode_failed`。
- 进程回收：两例 ffmpeg 均已 `Process.wait()` 返回并取到 returncode（0 / 251），据此认定回收完成。不把 `pgrep -f f32le` 零匹配当判据——`pgrep -f` 可能自匹配命令自身，按命令行模式匹配也可能漏掉残留进程。
- 结论（观察一轮）：#87 的「错误被迭代接口吞掉、只在 finish 抛」在本主干真实成立。**故障注入形态的限定**：喂垃圾 FLAC 是「ffmpeg 启动后自行非零失败」，**不等于**生产的「上传中途死亡」形态。
- 后续验收必须用生产形态：拿到真实 pid 后中途杀死它且**不发送末帧**，再断言迭代即抛 `decode_failed` 与 WS 错误帧。本轮观察不能替代该验收。

### 探针 B：真 SDK × 本地假服务端（未复现，机制未证实）

- 脚本：`probe_b_sdk.py`（真实 `transcribe_file`、`/health` 返回 `protocol_version=2`+`encodings=[flac]`、客户端与服务端 `max_queue=1`、服务端只发不读、每 0.3s 发一条同 `task_id` 的合法 `is_final=false` 结果）。
- 已取得的可靠事实：服务端从**实际收到的第一帧**解出 `task_id=05dafe64-…`；14 182 340 字节音频上传在预算内**未触发**逐帧 idle 误杀；12s 快照显示 38 条合法中间结果已发出，SDK `_receive` 与 `idle_watch` 均健康。
- 未复现原因：回环 socket 缓冲把整份负载吸收，背压未真正到达客户端 `ws.send`，于是被测的失败前提（发送阻塞 + 同时有有效中间结果）不成立。
- 附带观察：现实现对**任意**下行消息都刷新 idle 令牌（`client.py:305` 先 put 再解析），未知 `type` 当前确实会刷新——卡 B 收窄它属行为变更，须显式锁测试。
- 最小后续复现入口：在假服务端 upgrade 前把连接 socket `SO_RCVBUF` 降到 2048（或改用逐帧慢读服务端），保持 `idle_timeout=3`，断言 `AsrError(code="timeout")` 且消息指向 send 阶段，同时 `results_sent>0`、`bytes_received < 文件大小`。预算建议单跑 ≤60s。

## 待验证前提

1. [推断] #76 历史事故中 ffmpeg 退出的触发原因仍未确定；`SIGSTOP` 同构不等于历史根因。卡 B 的判据设计不依赖该前提，但关单叙述不得引用未证实的因果。
2. [推断] WS 整体内存有界不是本批已证明性质，不写入任何不变式。
3. [推断] 默认 `CW_MAX_TASK_SECONDS=14400` 下 17501s 样本应明确 `audio_too_long` 而非要求成功（`ws_recv.py:229-236` 已有该检查）；本轮未实测。
4. [未决] #85 具体卡死点未实测；卡 C 实现前必须先取到受控复现，否则只允许做「有界回收」清理，不允许声称修好。

## 验收路径

1. 卡 B 的 SDK 测试矩阵（全部走 `transcribe_file`，建议连续 5 轮窄测）：发送阻塞且下行静默 → 上传未完时 idle 失败；持续成功发送 → 上传中不因缺回复误报；发送阻塞但有效结果不断 → 不被 idle 误杀；上传完成且无结果 → idle 失败；未知 `type` 持续到达 → **在 idle 上暴露**、不得延长 idle；服务端错误码透传；显式总预算即使有进展也按调用方要求生效；取消后无 pending 任务与子进程。
2. 卡 A：先红（探针 A 的断言搬进 `tests/test_audio_decoder.py`，并按上文「生产形态」补 SIGKILL 且不发末帧的变体），再实现；WS 端到端错误帧用真实客户端消费，落在 `tests/test_ws_decode_failure.py`。
3. 卡 C：受控子进程复现脚本先落 scratch 再入 `tests/test_harness_shutdown.py`，主体失败路径断言退出码与回收；根治改动落在 `tests/harness/server.py`。
4. 卡 D：清账表产出后逐条核对「有去向」，不以数量收口。

## 拆卡

| 卡 | 范围 | 候选文件 | 现有相关测试 | 依赖 |
| --- | --- | --- | --- | --- |
| A（#87） | WS 解码错误沿迭代传播 + WS 错误帧 | `core/server/connection/audio_decoder.py`、`core/server/connection/ws_recv.py`；新增 `tests/test_ws_decode_failure.py` 与 `tests/test_audio_decoder.py` 用例。**HTTP 本批不改** | `tests/test_audio_decoder.py`、`tests/test_protocol_v2.py`、`tests/harness/`（夹具来源） | 无，先派 |
| B（#76） | SDK 双向进展判据 | `sdk/capswriter_asr/client.py`（`upload`/`idle_watch`/`_receive`）、`sdk/README.md` | `tests/test_sdk_client.py`、`tests/test_sdk_deadline_stage.py`、`tests/test_sdk_no_wait_for.py`、`tests/test_sdk_samples_total.py`、`tests/test_sdk_transcode_track.py`、`tests/test_e2e_sdk_server.py` | 无（与 A 无接口依赖） |
| C（#85） | 受控子进程有界回收（owner 侧） | `tests/harness/server.py`（真正资源 owner）；新增 `tests/test_harness_shutdown.py`。禁入 `tests/test_http_file_tasks.py`，且不得与卡 A 同时改 `tests/test_ws_progress_watchdog.py` | `tests/test_ws_progress_watchdog.py`（消费方，复用其受控子进程场景，不作为根治点） | 无 |
| D（#81） | 历史产物清账 | 文档与归档目录，不含代码 | 无 | 无 |

调用方/构造方影响：A 改迭代语义后，`ws_recv._consume_compressed_pcm`（`:239`）是迭代消费方，`message_handler`（`:327`）是 `_feed_compressed` 返回值的消费方，`ws_recv.py:613` 是 `message_handler` 返回值的消费方——三处必须同步核对。HTTP 的 `FileSourceDecoder` 与 `AudioDecoder` 之间没有继承或调用关系，不受 A 影响。B 改 `client.py` 公共等待原语，同文件内 `upload`/`idle_watch`/`deadline_watch` 与外层 `FIRST_COMPLETED` 裁决互相耦合，禁止与他卡并行改同一文件。

## 失败可见性

| 失败 | 用户看到 | 禁止 |
| --- | --- | --- |
| ffmpeg 非零退出（WS） | 客户端收到 `decode_failed` 错误帧后连接关闭 | 无错误帧直接 return、静默丢帧、把 stderr 非空当失败 |
| 解码失败（HTTP） | `decode_failed` 可见（现有 `FileSourceDecoder` 迭代 + finish 已保证） | 本批无理由改动 HTTP |
| SDK 双向无进展 | `AsrError(code="timeout")`，消息含阶段/计数/距最后进展时间 | 逐帧 send 时长判死、把 send 阻塞说成服务端责任 |
| 未知消息持续到达 | 在 idle 上暴露，不延长 idle | 拿总预算当未知消息的兜底判据 |
| 测试主体失败 | 有界非零退出 + 原始异常可见 + 子进程已回收（回收归 `tests/harness/server.py` owner） | 只在某个测试 `finally` 补一刀、挂死、SIGCONT 依赖、外层 timeout 掩盖 |
| 清账缺项 | 表格逐文件有去向 | 用待删数量当完成条件 |

## 主干基线（派发时刻）

- 主干基线不可用：gh api request failed → 继承红未能判定。
- 本卡未改任何生产代码与测试代码，未引入新红面。

## 文档订正记录

首版 `7664c17` 的设计事实经主脑复核后订正（仅文档，无代码改动）：HTTP 改为独立 `FileSourceDecoder` 且本批不改；stderr 非空不再作为失败条件；`_feed_compressed` 的 `False` 调用方订正为 `message_handler` → `ws_recv.py:613`；「删除」改为明确本次就是删两处冗余判据；卡 C 根治点订正为 `tests/harness/server.py` owner 侧并新增独立测试文件；卡 A 新增独立测试文件；回收证据去掉 `pgrep` 判据；未知 type 的失败形态改为在 idle 暴露。订正 commit 见本卡最终提交。