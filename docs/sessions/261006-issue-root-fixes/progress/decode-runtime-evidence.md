# #87 解码运行时证据（冻结对象 d196db1）

本文件只记录本卡实测到的命令与结果，不含实现推理，不引用此前任何审查结论。
所有运行都在**冻结提交** `d196db1277dd9d0339f09c32536b42633317ffce` 的工作树上进行，
生产代码在该提交上未被本卡改动（见「环境与对象」中的对象核对）。

## 环境与对象

- 冻结对象（app）：`e849c21748392ad848131e07ff17d32e4cc83a8b..d196db1277dd9d0339f09c32536b42633317ffce`
- 本卡期间工作树 HEAD 恒为 `d196db1277dd9d0339f09c32536b42633317ffce`，收尾复核一致。
- 解释器：CPython 3.11.15（CI `test` 矩阵的生产维度，py3.11 / websockets==15.0.1）
- websockets：15.0.1（CI 该维度钉死版本）
- 其余依赖：numpy、rich、colorama、pytest 9.1.1、soundfile、pytest-asyncio 1.4.0、
  aiohttp 3.14.3、httpx 0.28.1
- ffmpeg：`/usr/bin/ffmpeg`，6.1.1（真实 ffmpeg，未打桩）
- 依赖隔离：全部装在本卡专属临时目录下的独立 venv（`/tmp/capswriter-decode-runtime-<dispatch>/.venv`），
  **未写入、未重建主仓 `.venv`**；收尾对主仓 `.venv/bin/*` 逐个查 shebang 是否指向 `/tmp`，
  输出为空（干净）。
- scratch 唯一落点：`/tmp/capswriter-decode-runtime-<dispatch>/`，脚本先落盘再执行，事后保留。

## 证据一：三个相关测试文件整文件运行（真实消费树）

命令（在冻结工作树根执行）：

```
<python3.11> -m pytest tests/test_audio_decoder.py tests/test_ws_decode_failure.py \
    tests/test_protocol_v2.py -q -p no:cacheprovider
```

结果：`34 passed in 4.83s`，退出码 0，无 warning、无 error、无 skip 计数缺失。
该数字是终端汇总行的原文计数，未因 warning 抹改。

## 证据二：WS 故障文件连续 5 轮 + producer 实际帧样本

命令：

```
<python3.11> -m pytest tests/test_ws_decode_failure.py -q -p no:cacheprovider
```

连续 5 轮，每轮单独记录退出码与末行：

| 轮次 | 退出码 | 末行 |
|---|---|---|
| 1 | 0 | 5 passed in 0.94s |
| 2 | 0 | 5 passed in 0.96s |
| 3 | 0 | 5 passed in 0.96s |
| 4 | 0 | 5 passed in 0.88s |
| 5 | 0 | 5 passed in 0.77s |

（证据一那次整文件运行已含该文件第 0 轮，共 6 轮全绿。）

### producer 实际帧样本（只读取样）

取样方式：把冻结工作树 rsync 成 scratch 副本，在副本里加一个**只读** spy 插件包裹
`tests/harness/client.collect_terminal`，把客户端真实 `json.loads` 到的帧落盘；原树测试零改动。
副本内生产模块与原树逐字节相同（`core/server/connection/ws_recv.py`、`audio_decoder.py` 未改）。

白名单字段（task_id 已截断为前 8 位十六进制，其余字段原样）：

| 用例 | 客户端实收帧 | 关键字段 |
|---|---|---|
| 等下一帧时 SIGKILL | 2 帧 | ① `type=result, is_final=false`；② `type=error, code=decode_failed, retryable=false`，message 前缀 `ffmpeg 解码失败，退出码 -9` |
| feed 中途 SIGKILL | 1 帧 | `type=error, code=decode_failed, retryable=false`，message 含 `退出码 -9` |
| 末帧与死亡同到 | 1 帧 | `type=error, code=decode_failed, retryable=false`（无 `result`+`is_final` 帧） |
| 正常 flac 收尾（对照） | 1 帧 | `type=result, is_final=true`，无 `decode_failed` |

三例 task_id 与客户端自发的 uuid 一致（测试用同一 task_id 过滤终态），error 帧均非 `internal` /
`connection_lost` / `decode_stalled`。

### 连接关闭与回收事实

- 等下一帧用例：终态 error 帧之后立刻 `recv()`，得到 `websockets.ConnectionClosed`
  （测试内断连接码为 `ConnectionClosed`，否则断言失败）。
- 三例均无 `is_final=true` 的成功 result 帧（`not any(m.get("is_final"))` 断言通过）。
- ffmpeg 子 PID 回收：用 `/proc/<ppid>/stat` 找到服务端**唯一新子进程**后再 SIGKILL，
  事后轮询 `/proc/<pid>` 消失（8s 内）；持进程 `wait()` 返回非 0（实测 -9）。
- `/health` 的 `active_tasks` 回到 0（15s 内轮询到达）。
- 服务端主进程在整轮断言后仍存活。

## 证据三：base 红验（scratch-worktree，只拷测试文件）

工具：`scripts/git/scratch-worktree.sh <主仓> e849c21 -- <命令>`，临时树用后自动拆除
（收尾 stderr 报 `removing dirty worktree with 2 change(s)`，注册表已清）。

对象核对（红验必须落在 base 的生产代码上）：

- 临时树 HEAD = `e849c21748392ad848131e07ff17d32e4cc83a8b`
- `git status --porcelain` 只有两行：`M tests/test_audio_decoder.py`、`?? tests/test_ws_decode_failure.py`
- `git diff --name-only` 只有 `tests/test_audio_decoder.py`（生产模块零改动）
- 拷入文件的 blob：`test_audio_decoder.py` = `b8bf513b…`（base 树内为 `59600a75…`，即本卡新增测试内容），
  `test_ws_decode_failure.py` = `4c444005…`（base 不存在该文件，整文件为新增）
- in-process 导入来源打印：`audio_decoder.__file__` / `ws_recv.__file__` 均指向临时树 `core/` 下，
  **不是**本卡工作树；并断言 `audio_decoder.py` 源码中不含 `_reader_error is not None` 分支（base 无该分支）

红 1（迭代器不调 finish 的非零退出用例）：

```
FAILED tests/test_audio_decoder.py::test_pcm_chunks_raises_decode_failed_on_nonzero_ffmpeg_without_finish
E  Failed: DID NOT RAISE AudioDecodeError
pytest 退出码 1
```

红 2（WS 上传途中 SIGKILL、无末帧）：

```
FAILED tests/test_ws_decode_failure.py::test_ws_kill_while_waiting_next_frame_sends_decode_failed
E  AssertionError: 'internal' == 'decode_failed'   （实际帧 code=internal，
   message 前缀 RuntimeError: 压缩音频消费协程在末帧前结束）
pytest 退出码 1
```

两处红都是断言/DID NOT RAISE 形态，不是 import 失败、依赖缺失或工具异常；红 2 的帧是服务端真实
发出的 error 帧，不是桩。临时树整体退出码 0（脚本自身清理成功）。

## 证据四：同 tick 分支的独立局部撤回（scratch 副本）

撤回方式：scratch 副本里把 `core/server/connection/ws_recv.py` 换回 base 版本。
该文件在本 diff 中只有一处 hunk（11 行增删，`diff` 计数 11），即「末帧与消费协程同 tick 完成时
先取消费结果」这一新增分支——撤回粒度是这一处，未扩大。

注入生效确认：撤回后 408–422 行实际内容已打印核对，`if consumer in done and not receive.done():`
与 `raise RuntimeError('压缩音频消费协程在末帧前结束')` 均在位（新增分支已消失）。

对照探针（同一探针脚本，只换被测模块文件）：

| 树 | helper 看到的 done | 真实 helper 结局 |
|---|---|---|
| 冻结提交（未变异） | `n_done=2, both_done=true` | 抛 `AudioDecodeError(code=decode_failed)` |
| 撤回新增分支后 | `n_done=2, both_done=true` | 返回末帧 `'{"is_final": true}'`（失败被吞） |

- 探针证实两分支确实同 tick 完成（`n_done=2`、`both_done=true`），撤回生效由结局翻转佐证。
- 变异后跑该用例：`FAILED …::test_receive_compressed_frame_same_tick_prefers_decode_failed`，
  断言文本为「同 tick 已知 decode_failed 必须压过 receive 结果，实际得到 '{"is_final": true}'」。
- 变异后跑 WS 整文件：`1 failed, 4 passed`——只有这条翻转，其余 4 条不受该 hunk 影响
  （说明这条测试的约束力指向本 hunk，不是整文件级联假红）。
- 未继续叠加更多变异。

## 不变式 → 代码位置 → 锁定测试

| 不变式 | 实现位置 | 锁定它的测试 |
|---|---|---|
| ffmpeg 已知非零退出必须在 `pcm_chunks` 迭代时抛 `decode_failed`，不等 `finish` | `core/server/connection/audio_decoder.py` `pcm_chunks` 中 `item is _END` 分支 | `tests/test_audio_decoder.py::test_pcm_chunks_raises_decode_failed_on_nonzero_ffmpeg_without_finish` |
| 解码推进后真 ffmpeg 被 SIGKILL，迭代即抛 `decode_failed`（不得用垃圾输入冒充启动失败） | 同上 | `tests/test_audio_decoder.py::test_pcm_chunks_raises_when_ffmpeg_killed_after_progress` |
| stderr 有告警但退出码 0 仍算成功 | 同上（按 returncode 判，不按 stderr 判） | `tests/test_audio_decoder.py::test_stderr_warning_with_zero_returncode_still_succeeds` |
| ffmpeg 失败信息只保留 stderr 末 500 字节 | `audio_decoder.py` 错误消息构造 | `tests/test_audio_decoder.py::test_ffmpeg_failure_message_keeps_only_last_500_stderr_bytes` |
| WS 等下一帧时 ffmpeg 死亡：客户端收到 `decode_failed`、`retryable=false`、连接关闭、无成功 final | `core/server/connection/ws_recv.py` 解码失败错误分支 + `_receive_compressed_frame` | `tests/test_ws_decode_failure.py::test_ws_kill_while_waiting_next_frame_sends_decode_failed` |
| 正在 feed 下一帧时死亡走同一错误分支 | `ws_recv.py` `_feed_compressed` 路径 | `tests/test_ws_decode_failure.py::test_ws_kill_while_feeding_sends_decode_failed` |
| 末帧与死亡同到时失败优先，不发成功 final | `ws_recv.py` `_receive_compressed_frame` 同 tick 分支 | `tests/test_ws_decode_failure.py::test_ws_final_arriving_with_death_prefers_decode_failed`、`::test_receive_compressed_frame_same_tick_prefers_decode_failed` |
| 子进程与任务槽位在错误路径上被回收 | `audio_decoder.py` 进程回收 + `/health` active_tasks | `test_ws_kill_while_waiting_next_frame_sends_decode_failed`（`/proc` 回收 + active_tasks 回 0 断言） |
| 正常 flac 上传仍产出 final，未被错误分支误伤 | 未改动的成功路径 | `tests/test_ws_decode_failure.py::test_ws_normal_flac_still_gets_final` |
| 协议层帧形态（v2 `_frame` / `_encode_flac`） | `tests/test_protocol_v2.py` 覆盖 | `tests/test_protocol_v2.py`（整文件，证据一已跑） |

## 风险与边界

- 本卡只验 decoder 失败公共接口与 WS 错误传播这条链。**不解释、不归因生产环境 ffmpeg 历史死亡原因**，
  也不判断 ffmpeg 6.1.1 以外版本的差异。
- 未触碰：duration ×4+120、总 deadline、HTTP 链路、协议字段集合、重试语义、ping 周期。
  本卡的 WS 用例显式 `ping_interval=None`，因此不构成对 ping 路径的证据。
- 未跑全量 `tests/`（CI 3.12 维才是全量），未部署、未改任何配置。
- 平台：SIGKILL 与 `/proc` 相关断言在非 Linux 会被 skip；本卡运行环境为 Linux，
  `/proc` 用例实际执行（证据二第 1 例含子 PID 定位与回收断言，为 passed 而非 skipped）。

## 已知限制

1. WS 故障文件单轮耗时 <1s，样本量小（5 条用例）。稳定性的证据来自「6 轮全绿 + 每轮退出码 0」，
   不来自单轮时长；对更长时间窗的抖动本卡没有覆盖。
2. 副本 spy 运行时，`__pycache__` 沿 rsync 一并带过去，导致失败回溯里的文件名显示为原树路径；
   已用 blob 比对确认副本测试文件与冻结工作树逐字节相同（两侧 `4c444005…`），非内容差异。
3. red 2 用的是 base 上真实 ffmpeg 被 SIGKILL 的路径，但 base 侧错误码为 `internal`，
   因此它证明的是「这条测试锁的是错误码语义」，不是「base 完全无错误处理」。
4. 主干基线在派发时刻不可用（`gh api request failed`），本卡没有可比基线，
   因此「继承红 / 新红」无法判定；本卡跑的三文件在冻结提交上全绿，未观察到任何红。

## 复现命令（相对冻结工作树根）

```
# 证据一
python3.11 -m pytest tests/test_audio_decoder.py tests/test_ws_decode_failure.py \
    tests/test_protocol_v2.py -q -p no:cacheprovider
# 证据二（重复 5 次）
python3.11 -m pytest tests/test_ws_decode_failure.py -q -p no:cacheprovider
# 证据三
scripts/git/scratch-worktree.sh <主仓> e849c21748392ad848131e07ff17d32e4cc83a8b -- bash red_base.sh
# 证据四（在 scratch 副本内）
cp <base 版本 ws_recv.py> core/server/connection/ws_recv.py
python3.11 -m pytest tests/test_ws_decode_failure.py -q -p no:cacheprovider
```
