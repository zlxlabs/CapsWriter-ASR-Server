# #87 剩日志真实验证

## 结论

真实 WebSocket、真实 ffmpeg 子进程、正常 `INFO` 日志配置下，ffmpeg 被
`SIGKILL` 后客户端在 0.125 秒内收到 `decode_failed`，消息为
`ffmpeg 解码失败，退出码 -9`，ffmpeg 已回收，服务进程仍存活并可继续处理
正常任务。服务端 logger 的实际文件增量含同一失败任务的结构化
`task_end ... status=failed code=decode_failed`；stdout/stderr 没有该文本。
因此 #87 的「日志未知」已由独立真实证据闭合，本卡不改生产实现。

## Probe 与白名单证据

- 脚本（保留、不提交）：`/tmp/caps87_real_log_probe_20261006_1834.py`
- 结果 JSON：`/tmp/caps87_real_log_probe_20261006_1834_v3.json`
- Python：`/usr/bin/python3` 3.12.3；CapsWriter 版本 `2.6`
- 实际源码：`core/server/connection/{audio_decoder,ws_recv,ws_send}.py`
  均来自当前 worktree；ffmpeg 为 `/usr/bin/ffmpeg`
- 配置：`CW_LOG_LEVEL=INFO`；使用 `ManagedFakeServerHarness` 的真实跨进程
  WebSocket、真实 worker 和真实 ffmpeg，不使用 mock logger、mock 错误帧
- 失败任务：`70276ae4-a420-4bc0-9193-b1ab57791fef`；输入 FLAC 585844
  字节，SHA-256 `bc137f13820225a76d5dc87fdedffbb34a734454f6307a6666a50dfc8860bed0`
- 失败路径：先收到非 final 结果，再收到 `type=error`、
  `code=decode_failed`、`retryable=false`；连接随后由服务端关闭
- ffmpeg PID `4006817`，已从 `/proc` 消失；服务 PID `4006718` 在失败后仍存活
- 正常对照任务：`9a90ba35-4fe4-4de6-97f9-337ea6d98306`，收到 `is_final=true`
  结果；筛选该任务消息得到 `decode_failed_codes=[]`
- 服务 stdout：`/tmp/caps87_real_log_probe_20261006_1834_v3.stdout.log`，
  537 字节，SHA-256 `0263c23e6388acb8acd8300c2f1d04f78250243ef0532e1185b6ab6fa79f5c67`
- 服务 stderr：`/tmp/caps87_real_log_probe_20261006_1834_v3.stderr.log`，
  0 字节，SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- logger 文件：`logs/server_latest.log`；probe 后 2522 字节，SHA-256
  `5ad5e64e43d971771544aeb80f5dae8dc0305589d935800610c34cc9b7f0e7aa`；
  相对 probe 前增量 2230 字节，增量 SHA-256
  `b6a0cfb3d376e57e06f57cf30d86ddf293ab72957c3966c7a91dcd938b6f5fe4`
- logger 白名单命中：
  `2026-10-06 18:39:55.158 INFO [state.py:391] task_end owner_kind=ws
  owner=3ae45609-0515-467d-aefa-c7db52aa39d1 task=70276ae4-a420-4bc0-9193-b1ab57791fef
  status=failed code=decode_failed duration_s=10.296 elapsed_s=0.081 segments=2 encoding=flac`
- `ManagedFakeServerHarness.stop()` 正常完成，随后核查服务 PID 与 worker PID
  均已消失；该 harness 未把 `multiprocessing.Process.exitcode` 写入结果，
  所以不宣称未知的数值退出码。

## 代码来源与现有测试

- `core/server/connection/ws_recv.py:512-518` 捕获 `AudioDecodeError`，调用
  `queue_error_and_close`；`ws_send.py:66-80` 排队错误帧并关闭连接。
- `ws_send.py:48-51` 的 `schedule_error_close` 调用
  `transition_terminal`；`core/server/state.py:366-398` 的集中终态迁移通过
  `core.server` 的 `server` logger 写出 `task_end`，所以该日志不是协议帧回显。
- `core/server/__init__.py:23-25` 初始化 `server` logger；
  `core/logger.py:60-88` 将文件写入 `logs/server_latest.log`，控制台处理器
  固定为 `WARNING+`，实际 stdout/stderr 是另一路 producer。
- `tests/test_ws_decode_failure.py:110-149` 已锁真实 SIGKILL、错误码、回收和
  进程存活，但没有锁服务端 logger 文件。
- `tests/test_protocol_v2.py:242-256` 已用 `caplog` 锁一般成功/失败
  `task_end` 结构化日志，但失败样例是 `unsupported_encoding`，不是本次真实
  ffmpeg 非零退出；因此「真实 SIGKILL 对应 logger」目前仍无长期断言。

## 边界记录

- 首次探针未进入服务：`/tmp/concurrent.py` 遮蔽标准库并缺少
  `psycopg2`；第二次 HTTP harness 因环境缺 `aiohttp==3.14.3` 超时。
  两次均未作为行为证据；第三次改用现有真实 WS harness 成功。
- 主干 CI 基线在派发时 `gh api` 不可用，继承红无法判定；本次仅执行
  `git diff --check`，没有新增代码红。
