# DESIGN-note：全仓审查确认缺陷的修复拆分（2026-10-20）

输入：`finding-verification.md`（基于 89a5192 逐条复核：13 CONFIRMED / 1 REFUTED / 1 PLAUSIBLE）。

## 目标

HTTP 文件任务再大、再慢、再失败，都不影响同机麦克风实时听写；代理在一个后端故障时能切到其它后端；
SDK 提交大文件不再误报超时。

## 非目标

- 不改 WS / HTTP 对外协议字段与错误码词表（第 15 条已裁决为失败上抛，沿用既有失败错误码）。
- 不重做 I/O worker 的线程模型（仍是单线程串行写库），只把长操作移出它。
- 不处理第 13 条（REFUTED：死参数但结果等价）之外的 pipeline 重构；第 13 条只删死参数。
- 不改部署脚本与 `deploy/`。

## 为什么不是分区 / 删除 / 约定

- **分区**：采用。根因是「长操作（整文件 SHA-256、大结果落库）与短操作（准入计数、失败写库）、
  以及 HTTP 与 WS 结果分发，共用同一条串行通道」。修法就是分区：哈希移出准入锁与共享 I/O worker；
  HTTP 结果改由独立消费者落库，ws_send 只做非阻塞投递。
- **删除**：第 6 条直接删除过期上传的源文件（410 后已无用途）；第 13 条删死参数；
  第 11 条的历史行 stat 扫描随第 6 条的删除收敛（只扫仍有源文件的行）。
- **约定**：第 14 条只改文档，把「8 个」改成与代码一致的 `max_tasks - WS_RESERVED_SLOTS`（当前 6）且为 HTTP+WS 共享计数。

## 方案要点与已否决方案

- **要点**（按卡，文件互不重叠，可并行）：
  - **卡 A 上传存储**（`core/server/http_store.py`、`core/server/http_server.py` 的 upload/commit 路由）：
    #3 #1 #6 #11。commit 先在锁外、用独立线程做整文件 SHA-256，再进准入锁只做查重+计数+建 Job；
    过期上传清理时删源文件并不再计入预留；容量扫描只遍历仍可能有源文件的行。
  - **卡 B 结果分发**（`core/server/connection/ws_send.py`、`core/server/http_file_runner.py`）：
    #2 #12。ws_send 对 HTTP 结果只做非阻塞投递给每个 Job 的独立落库消费者；64 MiB 上限改为增量估算，
    不在每个中间段全量 `json.dumps`。fail_job 的 5 秒退出语义**保留**（卡 A 落地后它只在 I/O 真挂死时触发，属 fail-fast）。
  - **卡 C 任务生命周期**（`core/server/worker/process_manager.py`、`core/server/connection/ws_recv.py`）：
    #5 #9。HTTP 段超时与 WS 对齐：只终结该任务，不退出服务；终态任务的迟到帧在准入前按已终结 task_id 丢弃。
  - **卡 D 代理**（`core/proxy/router.py`、`core/proxy/proxy_server.py`）：#4 #7。选后端时排除本任务已试过的；
    探活单个后端的任何异常都记该后端失败并记日志，探活循环本身不因单次异常退出。
  - **卡 E SDK**（`sdk/capswriter_asr/http_client.py`）：#8。httpx 客户端显式设超时，commit 的读超时覆盖服务端 1 GiB 校验的现实耗时。
  - **卡 F 杂项**（`core/server/worker/gpu_boost.py`、`core/server/formatter/text_formatter.py`、
    `core/server/worker/pipeline.py`、`docs/reference/protocol.md`、`tests/test_http_supervision.py` 的子进程环境）：
    #10 #13 #14 #15，外加本机 `HOME` 隔离导致子进程找不到 `~/.local` 依赖的测试环境问题。
- **已否决**：
  - 把 fail_job 超时改成「重试 / 不退出」：违反 fail-fast 红线，且根因是排队而非写库本身慢。
  - 给 I/O worker 加线程数：SQLite 写入仍要串行，只是把排队挪个地方，且破坏现有写序。
  - 第 4 条「失败一次即标不健康」：会让瞬时抖动把后端整体摘掉，改的是全局策略而非本任务的重试集合。

## 关键不变式

1. [实测] HTTP commit 期间，WS 新任务准入不等待整文件哈希——卡 A 用「哈希进行中发起 WS 首帧准入，断言在哈希结束前完成」的测试锁死。
2. [实测] HTTP 最终段落库期间，同连接/他连接的 WS 结果照常发出——卡 B 测试锁死。
3. [实测] 单个 HTTP 任务段超时，其它活动任务不被置为失败、进程不退出——卡 C 测试锁死。
4. [实测] 代理首选后端连接失败后，同一任务会尝试其它健康后端——卡 D 测试锁死。
5. [实测] 过期上传的源文件被删除且不再计入预留——卡 A 测试锁死。

（以上「实测」指各卡须以复现测试先红后绿锁死；89a5192 上的红态证据见 finding-verification.md。）

## 待验证前提

1. [推断] WS 段超时「只终结该任务」时 worker 子进程仍可继续处理后续段（不是挂死）；卡 C 先核实，若 worker 实际已不可用，则 HTTP 与 WS 应统一为「重启 worker」而非「各自不同」，卡 C 停下上报。
2. [推断] commit 时上传已满额（offset==size），锁外哈希期间不会再有 PATCH 改写源文件；卡 A 先核实。
3. [推断] 卡 B 的 ws_send 解耦不需要改 `http_server.py` 的 sink 装配；若需要，走 scope-request，与卡 A 串行合并。
4. ~~待用户裁决~~ **已裁决（用户 2026-10-20）**：第 15 条采用 (a)——标点/ITN 异常不再吞掉，任务直接失败上抛（fail-fast）；
   否决 (b)「交付原文本并标记降级」（需新增协议字段）与「维持现状」。

## 验收路径

- 本机起服务端（打桩识别），并发：一个 1 GiB 上传 commit + 一个 WS 麦克风任务，WS 首帧准入延迟 < 1 秒。
- 代理双后端（不等权重），停掉高权重后端，新任务落到另一后端成功。
- SDK `submit_file_http` 上传大文件到慢 commit 的打桩服务端，拿到 job_id 不报 timeout。
- 各卡合并后跑 `python -m pytest tests/ -q` 全绿（本机需先修卡 F 的 HOME 隔离问题，或以 CI 结论为准）。
