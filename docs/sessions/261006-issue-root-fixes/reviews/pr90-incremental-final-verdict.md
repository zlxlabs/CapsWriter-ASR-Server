# PR90 一次新增量独立审查结论

- 结论：通过；本轮新增量没有可阻产品的问题。
- 风险档：internal。
failure-visibility: clean
- 冻结审查范围：137032657a2ca9f5a3bf66194a5ddf24334e1956..cdee617f66069a859fd7d60bce520fc594ab4a4d（四问）；完整增量 5c05a0c4023140b2d3bdb20413936f6105415108..cdee617f66069a859fd7d60bce520fc594ab4a4d（三文件）。
- 文件范围：sdk/capswriter_asr/client.py、tests/test_sdk_client.py、tests/test_sdk_progress_watchdog.py。

## 四问

1. 仅处理登记项：是。改动限于完成置位顺序、真实 pending-send/error 断言、真实 gather 取消场景和两个 receiver 存活/收尾 oracle。
2. 未授权抽象：否。没有新增生产抽象、状态或配置；测试观测字段服务于多个新增场景，receiver 检查 helper 在两个测试模块各有真实消费者。
3. 无依据状态、事实源或 fallback：否。复用既有 completed 标志与任务集合；没有新增 fallback、重试、超时机制或 AsrError 字段。
4. 双路径：否。最终结果仍从单一路径返回；先保存结果，清理 gather 成功后置 completed，失败/取消仍走外层 abort。

## 不变量证据

- I1：新增背压测试使用真实 WebSocket send；服务端读闸关闭后观察 send 未完成，并在跨过 idle 窗口后确认匹配结果仍持续增加、调用未被误杀。解除背压后拿到匹配 task_id 的 final。未知/异 task 负控制在本轮五文件窄测中实跑通过；这些用例本身未由本增量改写。
- I2：新增 error 用例由假服务端使用生产 ErrorMessage 序列化，再经真实 socket 发出；task_id 来自收到的真实上传帧。错误发生时上传未完且最后一帧非 final；客户端保留三种 code 对应的 code/message，服务端会话结束，内部任务收尾为空。
- I3：client.py 先保存 receive 结果并 break；取消其余任务并等待真实 asyncio.gather 成功后才置 completed=True。新增用例在包含真实 upload task 的 gather 上对原 operation 单次 call_soon 取消；确认 final 已到、send pending、close 时 socket paused、transport 被 abort、调用有界结束且无泄漏。该受控实验验证取消路径，不推断自然发生频率或永久性。
- 两个 receiver oracle：正常 final 返回测试与背压取消测试均在收尾前断言精确 _receive qualname 为已知 live 的非空对照，收尾后断言泄漏列表为空；五文件实跑覆盖二者。
- 调用方核对：_operation、绝对 deadline、超时裁决与 close/finally 消费路径保持原值；duration*4+120、绝对 deadline、ordered 异常优先级及 return_exceptions 未改。

## 验证与 OCR

- Python 3.11.15 / websockets 15.0.1；源码 __file__ 指向本 worktree。新增真实 gather 取消用例单独实跑：1 passed。
- 同一运行时五文件窄测（test_sdk_client、test_sdk_progress_watchdog、test_sdk_deadline_stage、test_sdk_no_wait_for、test_e2e_sdk_server）：62 passed。
- Python 3.12.3 / websockets 16.0；源码 __file__ 指向本 worktree。关键用例（I1、三种真实 error、两个 receiver oracle、I3 取消）：7 passed。
- 固定三文件范围 git diff --check：通过。
- OCR 主审三态：status=reviewed（非 reviewed_fallback、非 skipped），coverage=complete，findings=[]，cli_status=complete，profile=minimax；耗时 98.9 秒。独立 verifier 的 verify_status=skipped、verifier=none，不能表述成 verifier 已审。

## 产品问题与流程事项

- 可阻产品问题：无。维护 backlog：无。
- 差分预算记录：145 行新增、20 行删除，增删合计 165；高于目标 70 与硬值 100。按锁定决策只作预算/卡片合规记账，不成为新的产品门槛。
- 主干基线：卡面记录 gh api request failed；继承红未能判定。本地指定窄测均通过，不代表 CI 结论。
- 流程记录：worktree 初始干净且无交接单；orphan 巡检为 0。memory 巡检探针返回 memory_dir_mismatch。探索终端调用按调用口径 12 次；部分复合调用内含多条只读子命令，若按子命令逐条计数会超过 12，作为流程偏差如实披露，不影响产品判定。
