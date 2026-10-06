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
- 本段结论：修正末帧并发分支，仅消费协程异常或返回 false 才取消 `finish()`；消费协程正常返回时继续确认 `finish()`，新增测试 8 项全绿。既有回归暴露的三个失败在修正后均通过。
- 关键决策与已否决方案：删除既有测试对已移除 `_CANCEL_TIMEOUT_SECONDS` 的注入，不恢复该中止超时；不以增加超时掩盖管道顺序问题。
- 下一步唯一动作：提交并发修正，随后完成 Python 3.11 窄套件与 Python 3.12 全套验证。

## 里程碑 5：双解释器验证与收尾

- 当前阶段：verification / closeout
- 本段结论：Python 3.11 窄套件为 61 passed；Python 3.12 全套为 520 passed、3 skipped；外部取消传播新增探针为 1 passed。FLAC 五轮错误帧延迟为 0.130047/0.229666/0.136789/0.132483/0.137360s，OGG Opus 为 0.083121/0.110871/0.072231/0.080376/0.094145s。
- 关键决策与已否决方案：验证只使用卡面命令与真实 ffmpeg；不增加协议字段、看门狗、重试或超时兜底。
- 下一步唯一动作：提交延迟证据与取消探针，核对工作树、ffmpeg 残留和最终报告。
