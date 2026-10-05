# 项目记忆

本文件记录 CapsWriter-Offline-with-AI 的仓专属事实，供以后在本仓工作的会话阅读。
内容于 2026-09-03 从 Claude Code 自动记忆迁出，技术细节原样保留，不替换现行设计文档。
条目可能已过期，阅读时请对照代码与提交日期。

## ASR 负载均衡代理架构

本条事实于 2026-06-30 得到（归档 frontmatter 无 `modified` 字段，取正文中的部署/修正日期）。

ASR 负载均衡代理 v3 已实现并部署（2026-06-30, PR#1 700e9b5 + PR#2 4be000f），路由公式于 2026-06-30 修正（d346b4c）。

关键架构决策：
- **Per-task 独立后端 WS 连接**：Server 的 `AudioCache`（`ws_recv.py:27`）是 per-websocket 的，不按 task_id 隔离。多个 task 共享一条后端连接会导致音频数据混合损坏。这是 Codex cross-model review 发现的致命缺陷，推翻了最初的"连接池"设计。
- **Least-connections 路由公式（2026-06-30 修正）**：`score = (active_tasks + 1) / weight + latency * 1e-6`。active_tasks 为主确保任务均匀分散到所有后端，latency 仅作同等负载时的 tiebreaker。**之前的公式** `(active_tasks + 1) * latency / weight` 因 latency 方差 10-300x 导致所有任务堆积到延迟最低的单台后端（Mac Studio），其他设备闲置——这是 tg-archiver 3 路并发测试发现的生产问题。
- **EWMA 截断重置（2026-06-30 修复）**：`record_processing_latency` 中 latency > 300 被丢弃时，同时重置 `avg_latency=0` 和 `latency_samples=0`。之前截断不重置导致僵尸 avg_latency 永久惩罚后端。
- **EWMA 样本过期**：`last_latency_time` 追踪最后一次样本时间，超过 `latency_ttl_seconds`（默认 300s）的旧样本视为过期，重置为冷启动状态（回退 peer median）。防止后端长时间空闲后旧延迟信号失真。
- **网络感知诊断**：记录任务端到端延迟（`monotonic()` 从 `_open_task_session` 入口到收到 `is_final`）和推理延迟双指标日志。端到端延迟仅日志不喂 EWMA。
- **Cooldown 恢复**：unhealthy 后端 cooldown_seconds（默认 60s）后自动重置 consecutive_failures=0 和 healthy=True。全部 unhealthy 时降级路由到 active_tasks 最少的后端。
- **不用 ping/pong 做健康检查**：Server 推理时可能阻塞 event loop，ping 超时会误杀正常工作的后端。
- **max_size=None**：与 Server 保持一致，不限制 WS 消息大小。
- **音频重发已 defer**：Codex 指出协议复杂度高（task_id 重写、部分结果去重、内存管理），待权重路由稳定后再做。详见 TODOS.md。

**Why:** 原 v3 公式虽然修复了零分陷阱，但 latency 方差（异构设备+异构音频时长）导致 latency 完全压制 active_tasks 的负载均衡效果。least-connections 是 nginx/HAProxy 的标准做法，对批量转录场景最优。

- **`/status` HTTP 端点（2026-06-30, 145d814）**：在 WebSocket 同端口通过 `websockets` v16 `process_request` 回调拦截 HTTP 请求。`GET /status` 返回 JSON，`GET /status?html` 返回格式化页面。显示后端原始字段（active_tasks、healthy、avg_latency、weight 等），不显示计算后 score（因 least-connections 下 score 不直观）。任务完成历史用 `collections.deque(maxlen=1000)`，记录成功和失败任务。deque 放在 `ProxyServer` 层（全局唯一），因 `TaskRouter` 是 per-client 的。
- **日志改进（2026-06-30, 71deb45）**：`datefmt` 加日期前缀；`TruncatingFileHandler` 替换为标准 `RotatingFileHandler(backupCount=5)`，旧类已删除。

**How to apply:** 路由公式现在以 active_tasks 为主，不再需要担心 latency 压制。EWMA 仍保留用于日志和 tiebreaker，截断时自动重置避免僵尸值。如需让快机器自动多分任务，用 config_proxy.py 中的 weight 配置。`curl http://proxy:6020/status` 查看集群状态。

## 已知限制与重开判据（条件式跟踪登记）

本节登记三条**条件式跟踪**条目：它们不是「已知没修的缺陷」，而是「**等某个信号出现才需要做**」。

### 为什么这些条目不该挂在 open 列表里

一张 open issue 断言的是「这件事需要做」。而本节三条断言的是「等某个信号出现才需要做」。把它挂在 open 列表里是**类别错误**，代价有两层：一是每个周期都要重新判断一遍同样的问题；二是真正需要看的单会被淹没——2026-10-05 的分诊里，8 张 P2 挂单把真正该看的 #76（WS 长音频 4.9 小时无 final）埋掉了。

**条件式跟踪的正确形态**：判据落到仓内可 grep 的地方（本节）；信号触发时**开新单**（带实测证据），不复活旧单。旧单号只作为出处引用。

**本节不删的三个理由（三个消费者）**：
1. **每月分诊复核**：到点按下面的阈值逐条过一遍，判定「仍不触发」。
2. **信号触发时开新单的人**：需要在新单的描述里回引本节条目与出处 issue 号，直接抄判据原文，不重新推导。
3. **将来被问「这条为什么没修」的人**：能查到当时裁决的是「有阈值、有触发器」，而不是「当时没人管」。

### 登记表

阈值与判据逐字保留裁决原文，未改写、未四舍五入。

| 条目 | 为什么现在不修（裁决） | 重开信号与阈值 | 谁看 | 出处 |
| --- | --- | --- | --- | --- |
| **#61 HTTP 容量计费边界**（`bug` / P2 / 落点：本仓） | 三条已复现、接受不修：<br>① 创建/PATCH 自身的 SQLite 元数据与 WAL 增量未完全纳入 DB guard；<br>② 非终态源 ENOENT 同样释放声明预留；<br>③ 逐 PATCH 全历史 uploads/stat 扫描。<br>**另有「EXPIRED partial 仍扣未写尾的物理余量，可能长期误拒」这条待验证规格风险，当前不能被描述成已验证正确。** | **重开信号与阈值（任一即重开）**：<br>**信号 1（保守预留导致误拒）**：真实 HTTP 入口出现源存在且未过期却被容量闸拒绝的任务，**7 天窗口内 ≥ 1 例**；取证须同时记录 declared 源额度、当时物理余量、`EXPIRED` 与否三个值。<br>**信号 2（DB guard 缺口的真实后果）**：物理余量闸已触发后 DB/WAL/SHM 继续增长，随后出现 `SQLITE_FULL` / `disk I/O error`，**任一例**。<br>**信号 3（非终态源 ENOENT 释放预留）**：出现**一次经账本证据确认的额度双花**；无法用账本对上的不算。<br>**信号 4（全历史扫描性能）**：**先量真实生产行数与单请求耗时**；单请求 P95 > 1s 或每小时清理单次 > 5 分钟 / 内存 > 500MB 时重开。**在量出真实行数前不得升 P1，也不得假设「源文件最多数千」。**<br><br>触发时开新单的动作是：新单引用本条目，并附信号 1/2/3/4 中对应的那一份实测证据（信号 1 附三个取证值；信号 2 附 `SQLITE_FULL` 原始错误；信号 3 附账本对账记录；信号 4 附实测行数与单请求耗时），不在新单里重述本节阈值。 | HTTP 主线主脑在 M7 收口及后续容量相关改动时顺带复核；每月分诊复核一次。 | issue #61（已关闭，重开时开新单不复活） |
| **#72 基线工具超大媒体内存上界与 recovery 清理顺序**（P2 / 落点：本仓） | 本批授权素材最大 231.552 秒（解码 14,819,328 字节），执行机可用内存约 38 GiB，未观察到 OOM；`RLIMIT_AS=256MiB` 下合法大 WAV 触发 `MemoryError`（说明无任意内存上界，不代表现有样本会出事）。`run_http` 在最终校验与私有结果独占写入前删除 recovery，冲突时留下已完成远端任务但无本次采集产物。与 #61 的关系：C 的修法与 #61 容量语义是同一条容量账本上的两面，重开时合并考虑。 | **重开判据（任一即重开）**：<br>**A 规模**：单条授权输入 > 232 秒，或单次解码 PCM > 15 MB（16k mono s16le 约 32 KB/s 推算）。出现更大授权素材的那张卡就是触发器，必须回引本条。<br>**B 内存**：实际执行机可用内存 / 该次输入解码上界 < 4。<br>**C 恢复**：真实出现「远端任务已完成、私有结果已存在，但本次新采集产物丢失且 recovery 已删」——即丢失超出「可再生成的实验采集结果」这一层。任一例。<br><br>触发时开新单的动作是：新单引用本条目与对应判据（A 附该卡的素材秒数与解码字节数；B 附执行机可用内存与该次解码上界两个数；C 附远端任务完成、私有结果存在、本次采集产物丢失且 recovery 已删四项现场证据）。 | M7/基线线主脑在派任何扩大实验规模的卡时；每月分诊复核 A/B 当前值。 | issue #72（已关闭，重开时开新单不复活） |
| **#56 跨 ffmpeg 版本验证**（`enhancement` / P2 / 落点：本仓） | 两端实测均为 ffmpeg 6.1.1；`flac` 偏差 0、`ogg_opus` 偏差 104 样本（该 104 是**修复前**的扫描数字，与 design.md 的「最大偏差 522 样本」同源，旧 `ffprobe` 容器时长路径的产物，非当前同版本偏差），容差 16000 样本 ≈ 1 秒。后果是响亮的 `decode_failed`（消息带声明值与实际解码值），非静默错结果。<br>**本单提出的验收方案已核实测不到跨版本**：SDK 声明值走 `shutil.which("ffmpeg")`，测试期望值 `_decoded_sample_count` 用同一 `PATH`，`_capture_server` 只捕获帧不做服务端解码——换 ffmpeg 版本得到三方同版本。正确形态是**一次性手工矩阵**（编码版本 A × 解码版本 B × {flac, ogg_opus}），数字入库，不建常驻 CI job。 | **重开判据（任一即重开）**：<br>**(a)** 下游 SDK 宿主机或服务端任一方 ffmpeg 主版本不再是 6.x；<br>**(b)** 出现一次 `decode_failed` 且错误消息里「声明值 − 实际解码值」不等于 0；<br>**(c)** 计划收紧 `SAMPLES_TOLERANCE`（design.md 已列为非目标、「另议」）。<br>触发时开新单的动作是：(a) 由复核者在版本变更当天开新单并贴出两端 `ffmpeg -version` 实际输出；(b) 由触发者当场开新单，附该次 `decode_failed` 完整错误消息中的声明值与实际解码值；(c) 由提出收紧者在 design.md「另议」转为提案时开新单。 | 每月分诊复核 (a)；(b)(c) 由触发者当场开新单。 | issue #56（已关闭，重开时开新单不复活） |

### 使用这份登记表时

- 命中任一信号 → 按该行的「触发时开新单的动作是」开**新单**并回引本条目；不复活出处 issue。
- 逐条过完均未命中 → 该条目维持关闭，本节不做任何改动。
- 阈值变更需带实测依据并在本节同表内留痕，不以「看起来更合理」为由调整。
