# SDK65 独立复核 verdict（第 2 轮）：final 收尾修复与测试约束力

- 审查范围：`820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..a9b7e3474b6ced87fbbbd994ae2c646ca1509e63`（冻结）
- 修复增量专项：`4dd33bebc1082a677a0664013aacf35193e8433d..a9b7e347`
- 审查者：独立 reviewer（dlg-20261004-083804-2bcb16），未读实现 report 与前轮 verdict
- 结论：**pass**
failure-visibility: clean

## H0..H1 增量四问

1. **只修登记在案的测试缺口吗？** 是。增量内 `sdk/capswriter_asr/client.py` 改动为 **0 行**
   （`git diff 4dd33be..a9b7e34 -- sdk/capswriter_asr/client.py` 为空）；全部改动落在
   `tests/test_sdk_client.py`（+322/-110 量级）与会话文档：偶然并发改屏障、getter 按真实
   Task 身份跟踪、错误覆盖 final 时显式断言、连接拒绝用例显式短预算。
2. **新增未经批准的抽象吗？** 无。新增物全部为测试内 fixture/包装器
   （`_legacy_wait_for`、`sdk_queue_getter_tasks`、`_pending_sdk_tasks`、测试内
   `tracked_wait`/`tracked_create_task`），生产代码零新增。
3. **状态/事实源/fallback 无依据增加吗？** 无（生产代码未动）。
4. **双路径？** 无生产双路径。`test_websocket_connection_failure_maps_to_connection_lost`
   改走显式 `deadline_total=2`，与默认路径存在行为差（见下「默认路径延迟复核」），
   但注释与 root-cause 第 6 节均如实披露，不属隐瞒。

## 逐不变式核验（代码/测试/行为映射 + 本轮新证据）

- **I1（合法 final 及时返回，不依赖服务端关连接）**：成立。
  `test_final_result_returns_without_server_close` 服务端回完 final 保持连接；
  本轮在 **base 820c3a2 临时树**（client.py sha256 `ff476ad7…`，与文档自证一致）拷入
  当前测试文件，真实 Python 3.11.15 上该用例以
  `AssertionError: final 已到达服务端但 transcribe_file 10 秒内没有返回` 转红
  （日志 `/tmp/sdk65_review2_base_red.log`）；修后同用例在 3.11.15 / 3.12.3 全绿。
- **I2（收尾与预算约束、取消延迟不被夸大）**：成立。`_pending_sdk_tasks()` 覆盖
  `_transcribe_connected.*` / `transcribe_file.*` / `_operation.*` 协程名前缀；
  getter 由 `sdk_queue_getter_tasks` 按 `asyncio.Queue.get.__code__` + 调用帧文件名
  == `sdk_client.__file__` 双重过滤保留真实 Task 身份，client.py 内 `ensure_future`
  仅 idle_watch 一处，不会误捕其他任务；三条路径（final/error/取消）均断言集合非空且
  全部 done。外部取消实测：默认路径 t+2s 取消，2.005s 收尾（有界、非即时承诺，
  文档亦未承诺即时）。`deadline_watch`/`upload` 仍用 `wait_for` 的存量取消语义未变、
  未被本 diff 扩大。
- **I3（上传/接收并行，idle 不提前触发，单 send 受各自预算）**：成立。
  慢上传屏障用例：5 帧 × 0.5s，idle=1s；屏障点断言总上传 > 1.5×idle 且 getter 未创建、
  调用仍存活；放行后断言总上传 > 1.8×idle、每次 send < idle、上传结束后才 idle 超时。
  把 `await upload_done.wait()` 单独删除的变异使该用例以
  `AssertionError: 慢上传屏障未到达` 转红（日志
  `/tmp/sdk65_review2_mut_skip_upload_done_gate.log`）。
- **I4（同轮异常不被 final 覆盖，裁决不依赖 set 顺序）**：成立。生产侧用
  `ordered = (upload, receive, idle)` 固定顺序先查异常再返回。
  把「receive 完成即返回」挪到异常裁决之前的变异，使
  `test_upload_failure_is_not_masked_by_final_when_both_tasks_done` 以
  `AssertionError: 同轮合法 final 覆盖了 upload 的 send 异常` 转红（日志
  `/tmp/sdk65_review2_mut_final_priority.log`）；且失败点是 `assert False` 而非
  `observed_same_done` 断言，证明同 done 集合构造真实生效。
- **I5（跨边界断言真实序列化帧/UUID；子进程同步返回；变异必红）**：成立。
  fake server 只按实际收到的帧回 final，断言 `task_id` 一致、单任务 UUID 唯一、
  `samples_total == 16000`、`transcript.task_id` == 帧内 task_id；
  `test_sync_entrypoint_returns_transcript_in_subprocess` 在独立子进程内以
  真实 websockets 收发 + legacy wait_for 语义断言同步入口返回正确 Transcript。
  本轮三条变异（final 优先 / 删 upload_done 门 / 删 getter.cancel()）全部以行为
  `AssertionError` 转红；第 3 条失败信息直接显示捕获到 pending 的真实
  `Queue.get()` Task（`/tmp/sdk65_review2_mut_skip_getter_cancel.log`）。
- **I6（无预算/重试/fallback 新增；披露准确）**：成立。生产 diff 仅 idle_watch 改写 +
  同轮裁决定序，无新配置/状态/抽象；root-cause 第 5 节如实披露 3.10 存量
  `TimeoutError` 别名差异且本卡不修，第 6 节如实披露 3.11 其他取消等待边界为有限延迟
  P2 接受不修，第 10 节明确「生产尚未升级」。未宣称生产已恢复。

## 默认路径连接拒绝延迟复核（步骤 4 专项）

独立探针（`/tmp/sdk65_review2_probe_connrefused.py`，真实 fake server + monkeypatch
connect 拒绝，外层 `asyncio.wait_for` 170s 硬截止 + shell `timeout 200`）：

| 路径 | 结果 |
| --- | --- |
| 显式 `deadline_total=2` | 0.097s 返回 `AsrError(connection_lost)` |
| 默认预算 | **120.145s** 后才交付同一个 `AsrError(connection_lost)`（≈ 默认预算 120s） |

async task 栈取证（`/tmp/sdk65_review2_stackprobe.py`，t+2s 时 `task.get_stack()`，
非 selectors 线程栈）：`transcribe_file` 停在 client.py:538 的
`await asyncio.gather(operation_task, timer_task, …)`，`deadline_watch` 停在
client.py:516 `await asyncio.wait_for(deadline_changed.wait(), …)` → `tasks.py:476
await waiter`，且 `cancelling=1`——取消确被 3.11 `wait_for` 吞掉，`gather` 等到预算
结束才放行已算好的错误。文档此前的「路径归因推断」本轮升级为栈级实证；结论不变：
**有界**（≤ 默认预算）、错误码正确、外部取消 2s 内可中断、`deadline_watch` 为存量代码
（本 diff 未触碰），维持 P2 接受不修 + 披露，不为它新增机制。测试改显式 2s 未掩盖该
披露——root-cause 第 6 节明写 120s 现象与边界。

## 实测矩阵（本轮新跑，非引用）

- 解释器来源：3.11.15 = `uv` 管理的 `~/.local/share/uv/python/cpython-3.11…`；
  3.12.3 = `/usr/bin/python3.12`（系统）。依赖：`uv run --no-project` +
  numpy/rich/colorama/websockets(解析为 17.2)/soundfile/pytest==9.1.1/
  pytest-asyncio==1.4.0/httpx==0.28.1。
- 两文件整测 `tests/test_sdk_client.py tests/test_sdk_deadline_stage.py`：
  3.11.15 `34 passed in 19.64s`（`/tmp/sdk65-review2-full-311.log`），
  3.12.3 `34 passed in 17.96s`（`/tmp/sdk65-review2-full-312.log`）。
- 竞态核心 7 用例 × 5 轮 × 两解释器：10/10 全绿，每轮 ≤6.1s（上限 60s）。
- base 红验 1 条：见 I1（AssertionError，15.13s）。
- 变异红验 3 条（要求 2 条）：全部 AssertionError，见 I3/I4/I5。
- 连接拒绝探针：默认路径 120.145s + 栈取证，显式路径 0.097s。

## 观察项（不阻塞，backlog 级）

- 慢上传用例的 `send_durations` 含屏障等待时间，极端调度下末帧测量可能逼近 1s 断言
  边界；本轮 10 轮全绿，属轻微信号风险。
- 测试解析到 websockets 17.2，SDK 声明下限 15.0.1 的实测未在本轮覆盖（与存量一致）。
- 存量 P2（非本 diff 引入）：3.11 默认预算下「快速失败延迟交付至预算结束」；
  3.10 `except TimeoutError` 抓不到 `asyncio.TimeoutError`。两者文档均已披露。

## 未跑项

- 生产端到端验收（不在授权范围，文档亦未宣称）。
- OCR：首轮已执行 reviewed_fallback，本轮未重复调用，也不声称本轮跑过。
- 3.10 整测（存量缺陷已披露，不在本卡修复范围）。
