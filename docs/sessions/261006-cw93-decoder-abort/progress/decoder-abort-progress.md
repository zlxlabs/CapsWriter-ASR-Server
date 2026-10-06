# #93 解码器中止死锁进度

## 里程碑 1：基线与红测

- 当前阶段：implementation / 先红后绿
- 本段结论：已确认基线 `e849c21` 的 WS、HTTP 中止路径均先等待进程退出再处理输出管道。已新增真实 ffmpeg 背压测试，尚未完成基线红测。
- 关键决策与已否决方案：按卡面锁定“kill → 撤写侧 → 排空 stdout/stderr 至 EOF → wait”；不通过新增超时、重试或兜底解决。
- 下一步唯一动作：在未修改实现上运行新增测试并保存断言失败原文。

## 里程碑 2：中止顺序修复

- 当前阶段：implementation / 中止单元与 HTTP close
- 本段结论：`AudioDecoder.cancel()` 与 `FileSourceDecoder.close()` 已改为杀进程、撤写侧、排空 stdout/stderr 至 EOF 后再 wait；重复 WS `process.kill()` 已删除。真实 FLAC/OGG 背压单元与 HTTP close 测试均通过。
- 关键决策与已否决方案：WS 与 HTTP 共享 `audio_decoder.py` 的 `_drain_subprocess_pipes()`，因为本卡两处消费者的管道收尾形态一致；删除中止超时常量及 HTTP 误导性超时日志。
- 下一步唯一动作：提交本里程碑，然后运行 WS 越线与末帧测试。

## 里程碑 3：WS 越线与末帧

- 当前阶段：implementation / WS 行为验收
- 本段结论：FLAC 与 OGG Opus 在真实 stdout 背压下均能在 5 秒内收到 `audio_too_long`；每种编码连续五轮通过，末帧变体也通过，服务端记录 `task_end ... code=audio_too_long` 并回收 ffmpeg。
- 关键决策与已否决方案：WS 测试与发送协程并发接收，避免客户端写缓冲压住关闭握手；在消费侧越过 5 秒前暂停取许可并确认 stdout 超过 `2×StreamReader.limit` 后才放行断言。
- 下一步唯一动作：提交 WS 里程碑并运行卡面要求的既有回归测试。

## 里程碑 4：并发正常路径回归

- 当前阶段：verification / 既有回归
- 本段结论：修正末帧并发分支，仅消费协程异常或返回 false 才取消 `finish()`；消费协程正常返回时继续确认 `finish()`，新增测试 9 项全绿。既有回归暴露的三个失败在修正后均通过。
- 关键决策与已否决方案：删除既有测试对已移除 `_CANCEL_TIMEOUT_SECONDS` 的注入，不恢复该中止超时；不以增加超时掩盖管道顺序问题。
- 下一步唯一动作：提交并发修正，随后完成 Python 3.11 窄套件与 Python 3.12 全套验证。

## 里程碑 5：双解释器验证与收尾

- 当前阶段：verification / closeout
- 本段结论：Python 3.11 窄套件为 61 passed；Python 3.12 全套为 520 passed、3 skipped；外部取消传播新增探针为 1 passed。FLAC 五轮错误帧延迟为 0.130047/0.229666/0.136789/0.132483/0.137360s，OGG Opus 为 0.083121/0.110871/0.072231/0.080376/0.094145s。
- 关键决策与已否决方案：验证只使用卡面命令与真实 ffmpeg；不增加协议字段、看门狗、重试或超时兜底。
- 下一步唯一动作：提交延迟证据与取消探针，核对工作树、ffmpeg 残留和最终报告。

## 里程碑 6：预算收尾

- 当前阶段：closeout / budget
- 本段结论：压缩新增测试样板后，新增测试 9 项通过，基线到 HEAD 的 `git diff --numstat` 总行数为 420，正好不超过卡面硬上限。
- 关键决策与已否决方案：只删除重复断言与格式样板，背压辅助仍强制断言 stdout 已暂停且缓存超过 `2×limit`；不删行为覆盖。
- 下一步唯一动作：提交预算收尾并刷新最终工作树与报告事实。

## 里程碑 7：最终现场

- 当前阶段：closeout / delivered
- 本段结论：预算收尾提交已推送，远端 draft PR 指向最终 HEAD；最终 numstat 为 418 行，ffmpeg 残留为空。
- 关键决策与已否决方案：无新增决策；保留里程碑 6 的历史记录，不回写历史段落。
- 下一步唯一动作：无。

## 里程碑 8：续修有界回归

- 当前阶段：implementation / resume P2-1
- 本段结论：排空函数改为公开名 `drain_subprocess_pipes`；末帧在消费失败检查后直接 `await finish`；取消/末帧/WS 越线用例改到 spawn 进程组，超时由父进程 `killpg`，不依赖被测 cleanup 返回。
- 关键决策与已否决方案：子进程用 `run_until_complete` 后立刻 `os._exit`，避免 `asyncio.run` 关机等待挂住的 handler；否决在同一事件循环里用 `wait_for`/`shield` 包 `cancel()`，因为它取消不了已登记的 `process.wait()`。
- 下一步唯一动作：红验 a/b/c 后跑 Narrow-Verify 与 Verify-Command。

## 里程碑 9：续修验证收尾

- 当前阶段：verification / resume closeout
- 本段结论：红验 a 在 68s 内 7 项 AssertionError、HTTP 仍绿、无残留 ffmpeg；红验 b 末帧两编码 11s 内 AssertionError；还原后 8 passed。Narrow-Verify 61 passed；Verify-Command 520 passed、3 skipped。
- 关键决策与已否决方案：无新增决策。
- 下一步唯一动作：推送 draft PR #94。

## 里程碑 10：隔离通过路径的孤儿进程

- 当前阶段：implementation / orphan fix
- 本段结论：CI py3.12 全量 job 打完 `520 passed, 3 skipped` 后不退出，根因是 `_scenario_ws` 的 `multiprocessing.Manager()` 与 worker 没有显式关闭，子进程又以 `os._exit` 跳过 finalizer；这些孤儿继承 pytest 的 stdout/stderr 管道写端，管道读端拿不到 EOF。修法两条同时上：子进程 `finally` 里 `worker.join()` + `manager.shutdown()`，父进程 `_run_isolated` 在通过、场景报错、超时三条路径上都 `killpg` 回收整组。
- 关键决策与已否决方案：`_kill_group` 杀掉后只等内核摘掉被 SIGKILL 的成员（不计僵尸），不靠等待进程自然退出；否决旧 `_reap_group` 里「扫全机 ffmpeg 逐个 kill」的兜底，它会误伤同机其他会话的 ffmpeg，且组内回收已覆盖；`_live_group_pids` 用 `/proc/<pid>/stat` 的 pgrp 判定，僵尸不计（僵尸不占文件描述符，挂不住管道）。
- 下一步唯一动作：验证 `_run_isolated` 末尾的不变式断言非恒真，再推送。

## 里程碑 11：孤儿修复验证

- 当前阶段：verification / orphan closeout
- 本段结论：b009903 上窄套件 `8 passed` 后 5 s 仍残留 5 个进程（4 个 `spawn_main` + 1 个 `resource_tracker`，pgid/sid 全指向已死的隔离子进程）；修后同一窄套件与三次全量管道模拟（`520 passed, 3 skipped`，退出码 0）残留探测均为 0，汇总行到管道结束 0.056 s。红验 a（`cancel()` 回退基线顺序）68.22 s 内 7 项 AssertionError、HTTP 仍绿、无残留。不变式断言有效性：把 `_kill_group` 改成只检测不杀并去掉子进程侧关闭后，4 个 WS 用例以 `AssertionError: ... leftover_group_pids=[<pid>]` 转红，pid 与 5 s 探测到的残留一致。
- 关键决策与已否决方案：残留探测用 `CW93_PROBE` 标记读 `/proc/<pid>/environ` 归因，只认本轮运行衍生的进程，避免把同机其他项目同时起的 multiprocessing 进程算到自己头上；否决用 `ps` 差集直接归因，实测把别的项目的 `resource_tracker` 误计成残留。
- 下一步唯一动作：推送 `card/caps-93-decoder-abort-261006`，由主脑验收与 PR 门禁主审复核。
