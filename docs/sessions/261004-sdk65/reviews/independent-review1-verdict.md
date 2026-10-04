# SDK final 返回修复：独立审查 verdict

failure-visibility: p2-only

## 结论

冻结实现 `4dd33bebc1082a677a0664013aacf35193e8433d` 修复了「final 到达但调用等到总预算后报 timeout」的主路径。I1、I3、I5 的实现与核心行为得到支持；I4 的当前裁决逻辑在同轮探针中正确，但回归测试没有锁住该竞态；I2 仍有既存 `wait_for` 取消竞态，可导致取消延迟到剩余 timeout；I6 符合本次范围，但 Python 3.10 未在本审查运行。

未发现 P1。已证实的取消延迟是有限的调度/响应延迟：本次实测结束时 SDK 任务和连接均已收尾，没有错误结果被静默当成成功、数据损坏或崩溃，故按 `internal` 风险档记 P2，不阻塞主路径验收。OCR 返回 `reviewed_fallback` 且 `findings=[]`；OCR 主腿超时、备用腿成功，此状态不等于 skipped 或独立 clean 证明。

## P2 findings

| 工具标注 | 本仓判定 | 触发条件与可核实后果 |
|---|---|---|
| 无外部工具 finding；独立探针发现 | P2，I2：取消可能被继承的 `wait_for` 竞态延迟 | **P1 两问：**真实使用路径是否触发？是：Python 3.11.15 上从公共 `transcribe_file` 路径让真实 `deadline_changed` 等待者与调用方取消落在同一调度窗口，首个取消在 300ms 内未完成，任务快照含 `deadline_watch`（`cancelling=1`）和 `Event.wait`；二次取消后才结束。后果是否触及本仓 P1 红线？否：这是有界延迟而非错误结果、数据损坏或崩溃；取消最终完成并清理。`deadline_watch` 的 `wait_for` 最多等待剩余总预算（默认可能接近 120s）。另一个真实 SDK 调用路径的发送 Future 同拍探针在 3.11.15 上耗时 0.252s（设置 `idle_timeout=0.25`），并在取消后启动下一帧 send，随后关闭连接且无 SDK/server pending task；3.12.3 同一探针耗时 0.001s。定位：[client.py:360](/home/zlx/projects/oss/CapsWriter-Offline-with-AI-worktrees/sdk65-review1-261004/sdk/capswriter_asr/client.py:360)、[client.py:510](/home/zlx/projects/oss/CapsWriter-Offline-with-AI-worktrees/sdk65-review1-261004/sdk/capswriter_asr/client.py:510)、[client.py:534](/home/zlx/projects/oss/CapsWriter-Offline-with-AI-worktrees/sdk65-review1-261004/sdk/capswriter_asr/client.py:534)。原始输出：`/tmp/sdk65-review1-boundaries311.log`、`/tmp/sdk65-review1-boundaries312.log`、`/tmp/sdk65-review1-send-cancel.log`。这两处 `wait_for` 是本次改动未覆盖的继承路径；3.11.15/3.12.3 的实际 SDK 探针支持该 finding，不是仅凭代码形态推测。 |
| 无外部工具 finding；独立测试审查 | P2，I4：测试没有断言「发送失败与合法 final 同轮完成」 | [test_sdk_client.py:433](/home/zlx/projects/oss/CapsWriter-Offline-with-AI-worktrees/sdk65-review1-261004/tests/test_sdk_client.py:433) 明确不构造同拍；包装器在第一帧发送前直接抛 `OSError`，服务端没有收到帧，`frames == []`（483行）。故此测试证明普通发送失败映射为 `connection_lost`，不证明同一 `asyncio.wait` done 集合中的 final 不会覆盖发送异常。独立全 SDK 探针从实际序列化帧取 `task_id` 构造合法 final，并让 send 同时抛 `OSError`；upload 与 receive 在同轮完成时，SDK 按固定 upload→receive→idle 顺序上抛 `AsrError(connection_lost)`，关闭连接。当前实现通过探针，但缺少能锁住它的仓内回归测试。原始输出：`/tmp/sdk65-review1-boundaries311.log`。 |
| 无外部工具 finding；独立测试审查 | P2，I2：getter 任务不在测试的 pending-task 枚举范围内 | [test_sdk_client.py:158](/home/zlx/projects/oss/CapsWriter-Offline-with-AI-worktrees/sdk65-review1-261004/tests/test_sdk_client.py:158) 只筛选三个协程名前缀，没有筛 `idle_messages.get()` 创建的 Queue getter（168行）；故 `assert _pending_sdk_tasks() == []` 无法检测 getter 泄漏。独立跟踪真实 final 路径确实观察到一个 getter 创建，并在 `transcribe_file` 返回前完成；本次未观察到实际泄漏，因此这是断言覆盖盲点，不是已复现资源泄漏。输出见 `/tmp/sdk65-review1-boundaries311.log` 与 `/tmp/sdk65-review1-boundaries312.log`。 |
| 无外部工具 finding；独立测试审查 | P2，I3：上传期 idle 测试阈值低于配置的 idle timeout | [test_sdk_client.py:507](/home/zlx/projects/oss/CapsWriter-Offline-with-AI-worktrees/sdk65-review1-261004/tests/test_sdk_client.py:507) 为三帧各延迟 0.3s、`idle_timeout=1`，仅断言总耗时 `>=0.9`（556行）。错误地从上传开始计 idle 的实现仍可能在 1s 前成功，断言不能可靠锁定「上传期间不触发接收 idle」。实现本身在 [client.py:365](/home/zlx/projects/oss/CapsWriter-Offline-with-AI-worktrees/sdk65-review1-261004/sdk/capswriter_asr/client.py:365) 等待 `upload_done` 后才启动 idle；现有测试在 3.11.15/3.12.3 各重复五次均通过，但阈值没有充分区分正确与错误实现。 |

## I1–I6 验收映射

| 不变式 | 判定 | 证据 |
|---|---|---|
| I1 final 及时返回正确 Transcript，不依赖服务端关闭 | 支持 | 修前把新增核心用例拷入 base scratch：3.11.15 `test_final_result_returns_without_server_close_no_shim` 行为红（1 failed，返回 false）；3.12.3 shim/no-shim 核心选择行为红（1 failed、1 passed）。冻结实现修后对应选择分别绿：3.11.15 `1 passed, 27 deselected`；3.12.3 `2 passed, 26 deselected`。实际 wire 测试由服务端在收到 final 后保持连接。日志 `/tmp/sdk65-review1-red311.log`、`/tmp/sdk65-review1-red312.log`、`/tmp/sdk65-review1-green311.log`、`/tmp/sdk65-review1-green312.log`。 |
| I2 正常返回、错误、取消后任务和连接收尾；预算仍有效 | 部分支持 / 有上述 P2 | 主路径的回收断言及完整测试通过；实际 getter 追踪未见残留。但 `_pending_sdk_tasks` 漏掉 getter，且 `upload`、`deadline_watch` 的 `wait_for` 在 3.11.15 真实 SDK 调用的同拍取消探针中出现有界取消延迟。总预算/idle 超时测试存在；未声称所有 Python 3.10 调度语义均已验证。 |
| I3 上传接收并行；上传期间不受上传后 idle 提前终止；上传后无消息仍超时 | 实现支持，测试阈值偏弱 | receive 与 upload 并行启动见 [client.py:385](/home/zlx/projects/oss/CapsWriter-Offline-with-AI-worktrees/sdk65-review1-261004/sdk/capswriter_asr/client.py:385)；idle watcher 等 `upload_done` 后才计时（365–378行）。`test_idle_timeout_still_fires_after_upload` 通过；慢发送上传用例五轮/版本均通过，但 0.9s 与 1s 阈值差过小，见 P2。 |
| I4 error/cancel 不被 final/cleanup 覆盖；同轮裁决顺序固定 | 实现支持，关键竞态缺仓内回归断言 | [client.py:390](/home/zlx/projects/oss/CapsWriter-Offline-with-AI-worktrees/sdk65-review1-261004/sdk/capswriter_asr/client.py:390) 按固定顺序检查 done 集合；独立同轮 send 异常+final 探针得到 `connection_lost`，而非 Transcript。调用方取消传播普通路径通过；另见 I2 的取消调度边界。 |
| I5 真正序列化帧与同步子进程入口 | 支持 | 测试检查 SDK 实际发送帧，再从捕获的 `task_id` 生成回复；同步入口测试通过。目标整文件在两版本均通过（结果及原始日志见下）。 |
| I6 不加预算/重试/fallback/无第二消费者框架，继承缺陷显式披露 | 支持（带验证边界） | 实现改动为 `client.py` 32行新增/9行删除；无新增预算、重试或 fallback。文档列出 Python 3.10 继承兼容注意事项。此次独立执行器验证仅覆盖 Python 3.11.15、3.12.3，未运行 Python 3.10，不把结论外推到 3.10。 |

## 验证记录

- 冻结范围：`820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..4dd33bebc1082a677a0664013aacf35193e8433d`；审查分支起点为冻结 HEAD `4dd33bebc1082a677a0664013aacf35193e8433d`。全量 diff 五文件、911 insertions/9 deletions，`git diff --check` 干净。
- Python：`uv run --no-project --python 3.11 python --version` → 3.11.15；3.12 → 3.12.3。修前红验均来自 base scratch，修后测试来自冻结实现。
- 全文件窄测命令按任务卡依赖组合执行：`tests/test_sdk_client.py tests/test_sdk_deadline_stage.py`。3.11.15：34 passed，135.62s；期间 faulthandler 在 120s 打印 asyncio selector 堆栈，最终 pytest 退出码 0。不能把这条堆栈归因到单个测试；孤立 `test_close_without_error_frame_maps_to_connection_lost` 在 3.11.15 为 0.12s 通过。3.12.3：34 passed，15.48s，退出码 0。日志 `/tmp/sdk65-review1-full311.log`、`/tmp/sdk65-review1-full312.log`。
- 七个核心用例在 Python 3.11.15 与 3.12.3 各重复五次：十轮均 `7 passed`；日志 `/tmp/sdk65-review1-repeats.log` 及 `/tmp/sdk65-review1-repeat3.11-{1..5}.log`、`/tmp/sdk65-review1-repeat3.12-{1..5}.log`。
- OCR 前置摘要 934 bytes；原始 JSON `/tmp/sdk65-review1-ocr-20261004.json`，stderr `/tmp/sdk65-review1-ocr-20261004.stderr`。`status=reviewed_fallback`、`findings=[]`、`reason=primary=leg_timeout; backup:deepseek=success`；OCR 主腿耗时 900.113s 后超时，备用腿 104.575s 成功。按工具状态报告，不以它替代本审查结论。
- 所有探针日志在 `/tmp/sdk65-review1-*`。未接触生产，也没有在 CI / systemd 消费上下文运行；本结论限于上述本机解释器与本地 SDK 测试/探针。
