# PR #94 独立审查 Verdict
verdict: pass
failure-visibility: p2-only
new: verdict: in docs/sessions/261006-cw93-decoder-abort/reviews/decoder-abort-review1-verdict.md; locked-by docs/sessions/261006-cw93-decoder-abort/reviews/decoder-abort-review1-verdict.md

审查固定范围：`e849c21..95b86f46e12ca9f01acd740694b66da50c7c3e59`，PR #94，risk-tier `internal`。判定：没有 P1；一条 P2 测试挂起风险和一条 P3 私有 helper 命名建议。修复已解除 WS 越线取消、WS 末帧与 HTTP 关闭中的 wait/读管道依赖闭环。

## P1

无。

## P2

### P2-1：死锁回归时，取消与末帧测试可能卡在异步清理而非有界失败

位置：`tests/test_decoder_abort.py:116-120`、`tests/test_decoder_abort.py:210-233`；服务端收尾在 `tests/conftest.py:173-177`。

触发：将取消顺序回退为 #93 原有的「kill 后立即 wait」，让消费侧在背压下停止读；`test_external_finish_cancellation_propagates` 的 `await finish_task` 会等待 `finish()` 的取消收尾，而后者可卡在 `cancel()` 的 wait。末帧测试的 `collect_terminal(..., timeout=5)` 虽有接收期限，但超时后退出 websocket 上下文并进入 fixture teardown；服务端 handler 在 `finally` 再次等待相同解码器清理，`wait_for(server.wait_closed(), timeout=5)` 取消等待时也要等 handler 清理结束。

后果：目标回归可能使 pytest/CI 长时间挂住，无法按失败结果结束；这与“改坏时有界变红”的测试契约不符。卡面预取的基线与末帧回退实测也观察到该挂起形态。

建议：给这些特定回归用例提供不依赖同一事件循环清理的硬边界，并在边界触发后从测试进程外回收子进程/服务端；让测试报告明确断言失败，而不是依赖被测 cleanup 返回。

## P3

### P3-1：HTTP 模块跨模块导入私有 helper

位置：`core/server/http_file_runner.py:53` 导入 `core/server/connection/audio_decoder.py:9` 的 `_drain_subprocess_pipes`。

触发：若未来将 `audio_decoder` 内部函数重命名或移走而未同步 HTTP runner，服务模块导入会失败。当前没有运行时错误；该 helper 有 WS 与 HTTP 两个真实消费者，共享实现有依据。建议将共享函数命名为包内可见接口，或放在更中性的子进程工具模块。

## 必审清单

1. **`AudioDecoder.cancel()`**：先同步 `kill()`，再关 stdin、取消并等待 writer/reader/stderr 任务，随后并行读 stdout/stderr 到 EOF，最后 `wait()`；被杀的 ffmpeg 不再写入，读侧继续前进后 EOF 可达，消除了“wait 等 EOF、EOF 又等读侧”的环。StreamReader 会在高水位暂停 transport，kill 后残留只包含有界 asyncio 缓冲与有界 OS pipe 缓冲，`read()` 不会收集整条音频输出。`feed()` 的 CancelledError 路径会等 `feed` task 收尾后异常返回，`ws_recv` 再调用 `_cancel_audio_cache()`，两次是顺序调用；returncode 已设、stdin 已关、task 已结束、管道已 EOF，第二次安全。取消 `finish()` 时其异常分支会调用 `cancel()`；`cancel()` 在首个 await 前已发出 kill，即使再次外部取消打断后续排空，也不会留下仍在执行的 ffmpeg 进程，但 transport 完整收尾依赖这次 await 能继续。
2. **WS 末帧分支**：consumer 正常返回时，无论它还是 `finish` 先完成，都会等待双方再提交最终段；仅 `finish` 先完成时会先检查其结果/异常。consumer 返回 `False` 时取消未完成的 `finish`，返回 `False` 让外层终态清理接管；这是任务已终态或连接已关闭的信号。consumer 抛错时 `.result()` 原样重抛，先取消/回收 `finish` 再交给外层；外部取消走 `BaseException` 清理分支后继续传播。consumer 的 `AudioDecodeError.code` 由外层原样传给 `queue_error_and_close`。等价简写是直接 `await finish`，done/未 done 的 Task 均保留相同返回或异常语义；这是纯简化，不构成 finding。
3. **HTTP `close()`**：runner 的 `finally` 在同一 Job 协程内执行；取消会先退出 `async for` 的当前 `pcm_chunks()` 读取，再进入 `close()`，因此生产调用点没有与挂起 stdout 读并发。`close()` 发 kill、撤 stderr reader、排空 stdout/stderr 再 wait，覆盖 runner stop 的 Job 取消。直接由另一个并发协程在生成器仍执行 `read()` 时调用 `close()` 可能造成双 reader，但仓内真实调用路径不会并发这样做。移除 `DECODER_CLOSE_TIMEOUT` 不留下常规 ffmpeg 等待闭环。
4. **测试约束力**：背压取消用例在 `cancel()` 两秒边界或 returncode/EOF 断言处暴露回归；HTTP close 用两秒边界及进程/EOF 断言；WS 越线用真实 FLAC/Opus 背压、错误码和五轮延迟断言锁路径。外部 finish 取消与末帧测试的清理无独立硬边界，构成 P2-1。`test_decoder_abort_has_no_stale_cancel_timeout_constant` 只锁定无用常量不存在，不锁运行行为；可防止该符号复现，但价值有限。改动后的 `test_audio_decoder.py::test_cancel_kills_and_waits_for_unresponsive_ffmpeg` 也直接 `await decoder.cancel()`，没有自身时限，不过它的 sleep wrapper 不形成 stdout 背压，不能单独锁 #93 死锁。
5. **私有 helper**：跨模块用下划线名称不理想，但同一实现有两个调用方，抽取本身并非无消费者的抽象；仅记 P3-1 命名/归属建议。

## 验证

- 卡面指定的 Python 3.11 窄套件：24 passed（完整命令与耗时记录在执行报告）。卡面预取摘要称 62 passed；本 worktree 按同一命令实际收集为 24 项，差异记入报告。
- `git diff --check e849c21...95b86f46e12ca9f01acd740694b66da50c7c3e59`：退出码 0，无输出。
- OCR 初筛：`status=reviewed`、`coverage=complete`、`findings=[]`；工具 verifier 为 skipped/none，不将其当作额外验证。
- 本轮未注入变异；不声称新增反向验证结果。卡面已提供主脑此前的基线与末帧回退结果，本 verdict 对挂起风险另按测试/fixture 清理控制流判定。
