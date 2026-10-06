<!-- delegate-outcome: succeeded -->
## 结论

**有限未复现，不是“不可能”。** 6 个 `flac` / `ogg_opus` non-final 样本均通过真实 WebSocket、生产 `ws_recv`、生产 `AudioDecoder` 和真实 ffmpeg 子进程推进了解码；各观察 17 秒时，ffmpeg `returncode=None`、`reader_error=None`、stdin 仍开、`input_finished=false`、PCM consumer 未结束、服务端任务仍为 `RECEIVING`。期间收到非终态 `result(is_final=false)`，未收到错误帧，未观察到自然关闭。

因此本轮**没有取得**“ffmpeg 自然退出 0 + `reader_error=None` + PCM consumer 正常结束”的目标前提，不能回答该前提下 WS 应发何种错误帧；#95 本轮未真实复现。观察结束后的客户端断开触发服务清理，ffmpeg 退出码 `-9` 是清理结果，不计自然 EOF。

## 基线、范围与可检验假设

- 正式基线：`cb74d8f2a333d231cbd7e36ccff8c305b4ab89b6`；分支 `card/caps-95-natural-eof-261006`；执行时源码与基线一致。唯一仓库改动为本证据文档。
- 已执行 Evidence-Commands：`git show cb74d8f2a333d231cbd7e36ccff8c305b4ab89b6:core/server/connection/audio_decoder.py`、对应 `ws_recv.py`、`gh issue view 95 --repo zlxlabs/CapsWriter-ASR-Server`。Issue 标题为“跟踪：未发末帧时正常 EOF 的 WS 关闭语义（存量路径，尚未自然复现）”，状态 OPEN。
- 源码可检验假设：压缩输入只在 `AudioDecoder.finish()` 投递 `_END` 后由 writer 关闭 stdin；non-final 帧不调用 `finish()`。即使 FLAC 声明总采样数、Ogg 带 EOS 页，ffmpeg 仍可能等管道物理 EOF。本轮实测未证伪此假设。
- 真实消费链路来自 `tests.conftest.fake_asr_server`：生产 `ws_recv`、`ws_send`、`AudioDecoder` 与真实 asyncio/ffmpeg 子进程；仅进程外 ASR worker 使用项目 fake worker。观测包装器只记录真实 `begin_task`、`transition_terminal`、consumer 返回值和 subprocess argv，直接调用原实现；没有模拟 decoder/ffmpeg、finish、关闭 stdin、替换 consumer 返回值或发送 final。
- 环境：探针实际 Python `3.11.15`、websockets `15.0.1`、NumPy `2.4.6`、pytest `9.1.1`；`/usr/bin/ffmpeg` 为 `6.1.1-3ubuntu5+esm13`，`libavformat 60.16.100`。复用前次私缓存 venv `$CAPS95_PYTHON`，没有安装/升级依赖；其本机绝对路径见执行器完整报告。调用 shell 默认 Python 为 3.12.3，不是本次探针解释器。

## 样本与 producer 实测

共 7 个样本，单样本上限 17 秒，6 个 non-final 每个均观察约 17.0 秒（合计约 102 秒）；另有正常 final 对照。`is_final` 来自已落盘的实际发出 JSON，不是推测值。各 SHA-256 均为完整值。

| 样本（压缩 payload） | bytes / SHA-256 | 实际发出 JSON bytes / SHA-256 | 17 秒前状态 | 清理后 |
|---|---|---|---|---|
| `flac-pipe-complete-8s`（完整，STREAMINFO total_samples=0） | 183373 / `443842bc20d534a1a5c78bc3eba2becd2ef649eef688a9d1b2ddeee346ea0389` | 244693 / `7e94a54d15460b8abb171a9bd86b6d5d55360d419e6bd9a6efada135dd5d1b62` | pid 3620122；101376 samples；进程未退出；收到 partial result | 客户端关闭后 `-9` |
| `flac-file-complete-8s`（完整，STREAMINFO total_samples=128000） | 183373 / `da4bd36d8f0c37ede2ad88feb62dc973d6f5fb3d365458ebe5ee8fe25b599dc6` | 244694 / `840c7d0729faed74a21717751ada29e5a58c834c0ecc45c617747f6b8ac82ca7` | pid 3641561；101376 samples；进程未退出；收到 partial result | 客户端关闭后 `-9` |
| `flac-file-truncated-8s`（损坏：末尾去 32 bytes） | 183341 / `87879a4e121ef29fb0f9e68e1e6057c710df961cdeb74b112ac0a94e01fa9884` | 244650 / `4e2d9521aff6630ff73db45bc300dfc269ad8fd90ef22458b0f56ec99ae0587f` | pid 3662780；101376 samples；进程未退出；收到 partial result | 客户端关闭后 `-9` |
| `ogg-complete-eos-8s`（完整，最后页 EOS flag=4） | 41205 / `3c1a8b5618761ddc0d675a79512e5b5e52b28625a424f7526e0227416832d37c` | 55138 / `2a61c35d1a0ad569b0a04f6a2f156ba89181dd4159299dc4dc5a73de1e84764f` | pid 3688084；127984 samples；进程未退出；收到 partial result | 客户端关闭后 `-9` |
| `ogg-open-no-eos-8s`（未终结逻辑流：清除 EOS flag 并重算页 CRC） | 41205 / `114abbf1042e156773d0462b5d5020ec63f79a00fbbf8431f6027faae21ee8d4` | 55138 / `3f49340520a671f048181cd7973134831a0cefaea14f2c42702d14810b7d65c7` | pid 3708045；128200 samples；进程未退出；收到 partial result | 客户端关闭后 `-9` |
| `ogg-truncated-8s`（损坏：末尾去 32 bytes） | 41173 / `0f7ce875d03912f903d6f0d485c351856928ec36c7b98f6858eb229a18744c6e` | 55098 / `ef485e0694b4d09c907ea9849401f2874b9d84800d996108fc837ecc1576a03d` | pid 3730633；127880 samples；进程未退出；收到 partial result | 客户端关闭后 `-9` |
| `flac-normal-final-control-2s`（正常 final，对照） | 51305 / `2494d73bbfadda82991caef44528323766af3d6d2f9ad7bb2bfa96e0b7be7a19` | 68625 / `a236ccb058b1799953578aa99a916728737e9cba83c8bd2660559aed1e639915` | 0.073935 秒；32000 samples；ffmpeg 0；stdin closing、`input_finished=true`、consumer done/result=true；任务 `DONE`；实际收到 `result(is_final=true)` | 服务侧收到客户端正常清理关闭，码 1000 |

6 个 non-final 样本观察快照一致：`reader_error=null`、`stdin_is_closing=false`、`input_finished=false`、consumer `done=false/result=null`、任务 `RECEIVING/error_code=null`；WS 仅收到 `result(is_final=false)`，快照时 socket 未关闭。`-9` 和 close code 1000 均发生在快照后的本卡客户端关闭清理阶段。

### 编码与真实 subprocess 记录

- 8 秒 PCM producer fixture：`$CAPS95_CACHE/source-8s.f32le`；2 秒对照：`$CAPS95_CACHE/source-2s.f32le`。encoder 输入字节通过 `subprocess.run(input=...)`；真实 argv、继承环境白名单、编码输出 bytes/hash 全在 `$CAPS95_CACHE/probe-results.json.encoder_commands`。本机私缓存根的绝对路径见执行器完整报告。
- FLAC 实际 encoder argv：`ffmpeg -nostdin -hide_banner -loglevel error -y -f f32le -ar 16000 -ac 1 -i pipe:0 -c:a flac -f flac pipe:1`（pipe 版）；seekable 版末参数为 `.../flac-8s-file.flac`。同长输出分别声明 0 与 128000 samples。
- Ogg 实际 encoder argv：`ffmpeg -nostdin -hide_banner -loglevel error -y -f f32le -ar 16000 -ac 1 -i pipe:0 -c:a libopus -b:a 24k -application audio -f ogg .../ogg_opus-8s-file.ogg`。
- 被测 AudioDecoder 的实际 argv 从 `asyncio.create_subprocess_exec` producer 记录：FLAC 为 `ffmpeg -nostdin -hide_banner -loglevel error -f flac -i pipe:0 -ar 16000 -ac 1 -f f32le pipe:1`；Ogg 将 `-f flac` 替换为 `-f ogg`。每个真实 pid、argv、env 白名单、returncode、stdin 状态、reader error、样本数与 cleanup 时间线见对应样本 `decoder_spawn`、`observation`、`timeline`、`cleanup_after_observation`。
- 所有实际发出的 UTF-8 JSON frame 原字节保存在 `$CAPS95_CACHE/*.actual-sent-frame.json`；完整压缩 payload 在同目录 `*.payload.bin`。`$CAPS95_CACHE/probe.py` 是可重跑的单用途 producer/consumer 探针，`probe-results.json` 保留原始 producer 记录、实际 WS 收发和逐样本时间线。

## 判据、对照与结论边界

- “自然EOF真实复现”要求同一观察快照同时满足：所有实际发送帧 `is_final=false`、ffmpeg returncode=0、`reader_error=None`、stdin 未关闭且 `input_finished=false`、PCM consumer done 且结果为 True，并且快照在 cleanup 之前。本次 6 个 non-final 样本全部为“观察窗内未自然EOF但已推进”；无自然 EOF、无非零解码故障、无无推进样本、无探针失败样本。
- 正常 final 对照是已知否输入：实际发送 `is_final=true`，真实 WS 收到 final result、consumer 正常返回、任务 DONE。私判据将其分类为“normal-final 对照（必须拒绝为 #95 复现）”，`rejected_as_natural_eof=true`，负控制通过。
- 非 final 自然退出候选不存在，因此本轮没有记录自然 EOF 时的 WS error frame/close code，不能把 cleanup 的 `-9`、1000 close 或 final 对照结果外推成目标答案。

## 执行命令与验证

- 源码/issue：任务卡三条 Evidence-Commands（见上）。
- 环境核查：`command -v ffmpeg; ffmpeg -version; command -v python; python --version`；实际探针依赖核查：`$CAPS95_PYTHON --version` 与该解释器导入 `websockets,numpy,pytest` 并打印版本。`CAPS95_PYTHON` 的本机绝对路径见执行器完整报告。
- 完整探针命令：`PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}" "$CAPS95_PYTHON" -m pytest -q -s "$CAPS95_CACHE/probe.py"`，stdout/stderr 分别重定向到 `$CAPS95_CACHE/probe-run-2.stdout` / `$CAPS95_CACHE/probe-run-2.stderr`；退出码 0，`1 passed, 12 warnings in 102.70s`。警告为 websockets 15 对 `ConnectionClosed.code/reason` 属性的弃用提示，不影响探针结论。
- 第一次探针尝试在构造损坏 Ogg fixture 阶段失败（退出码 1），尚未启动 WS 样本；原因是把预期截断页交给“完整页序列”解析器。修正为对截断样本只作损坏标注后只重跑一次；第一次失败保存在 `$CAPS95_CACHE/probe-run.stdout`，修正版成功结果/producer 产物保留在私缓存。没有为得到复现扩大等待或重复刷探针。
- `git diff --check`：通过（退出码 0）。仅本卡证据文档在 Git 范围内；生产代码、测试、配置与依赖未改。

## Git 快照（证据文档落盘前实际输出）

`git log --oneline -1`：

```text
cb74d8f Merge pull request #99 from zlxlabs/card/caps-pr82-latest-minimal-261006-285aff49
```

`git show --stat --format= HEAD`：

```text
 core/server/http_store.py                          |   8 +-
 .../latest-minimal-progress.md                     |  13 +++
 tests/test_http_file_tasks.py                      | 102 ++++++++++++++++++++-
 3 files changed, 117 insertions(+), 6 deletions(-)
```

`git status --short --untracked-files=all`（证据文档落盘前，实际输出为空）：

```text
```

## 锁定决策与已否决方案

- 锁定：本轮只做真实复现取证；有限未复现不等于不可能。应用不改。协议语义需人工裁决，不由本探针变更。
- 已否决且未执行：改正常 EOF 语义、所有合法 EOF 一律转 `decode_failed`、SIGKILL/主动关闭 stdin 伪造自然 EOF、替换 consumer 结果、加 watchdog/retry/fallback、假模型证明识别质量、处理 #96、部署或访问生产端点。

## 踩到的坑

- 第一次探针在采样前把刻意损坏的末尾 Ogg 页当成完整页检查，错误发生在 fixture parser，不是解码行为。只修正损坏样本结构标记，第二次且唯一一次完整探针通过。

## 闸与绕过

- 无绕过。只使用本派发自己的独立 worktree 与私缓存；外部 fake worker 是卡面允许的唯一替身。未做提交范围外变更。

## 与卡面的偏差

- 无。没有复现目标链路，所以只报告有限阴性，不推断不存在，也不报告自然 EOF 对应的 WS 错误帧。

## 最贵的一步

- 7 样本实际 WS/ffmpeg 观察共 102.70 秒；最贵的是为避免复用旧 4.9 秒阴性窗口，对 6 个 non-final 样本各观察 17 秒。
