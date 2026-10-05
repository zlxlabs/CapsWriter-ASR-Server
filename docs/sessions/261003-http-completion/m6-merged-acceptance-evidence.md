# M6 合并主干验收证据

## 范围与身份

本文件只记录主干 `3d26d90b707003cbbc0b31d8d0e2e1f823f4d2a3` 的验收，不改变实现、测试、CI、Goal 或旧证据。运行前工作树干净；`HEAD`、`origin/master` 与该 SHA 相同。候选 `5db84d3f32a3e0530493410a9a8b80e7c6aff925` 是基线祖先，候选树和合并树均为 `dc467353149784c39f7858780b5ad0afc34c50d0`。

卡面指定的源契约已核对：`goals/http-integration/M6-qa.md` 仍是「未开始」，`GOALS.md` 仍显示 M4「进行中」、M6「未开始」；producer 域为 `docs/sessions/261001-http-files/design.md` 与 `qa.md`。仓内没有名为 `sharedreview-discipline` 的文件；本轮按绝对路径加载的 review 纪律为 `.agents/skills/review-discipline/SKILL.md`。

## 完整套件

两套命令都从该 SHA、Python 3.12、独立 `TMPDIR` 执行，并分别拿 `$HOME/.cache/caps-http-261005-fullsuite.lock` 后在 900 秒内运行：

```text
uv run --no-project --python 3.12 --with numpy --with rich --with websockets==15.0.1 --with colorama --with pytest==9.1.1 --with soundfile --with pytest-asyncio==1.4.0 --with aiohttp==3.14.3 --with httpx==0.28.1 python -m pytest tests/ -q -rs -p no:cacheprovider
uv run --no-project --python 3.12 --with numpy --with rich --with websockets --with colorama --with pytest==9.1.1 --with soundfile --with pytest-asyncio==1.4.0 --with aiohttp==3.14.3 --with httpx==0.28.1 python -m pytest tests/ -q -rs -p no:cacheprovider
```

| 套件 | 实际依赖 | 结果 | 说明 |
|---|---|---|---|
| WebSockets 15.0.1 | pytest 9.1.1 / pytest-asyncio 1.4.0 / aiohttp 3.14.3 / httpx 0.28.1 / websockets 15.0.1 | 481 passed, 3 skipped, 1 failed，235.31 秒 | 唯一红为既有 `tests/test_http_cleanup.py::test_fatal_cleanup_exits_process_and_reaps_children[systemd-unit]` 在 unit 已非零退出后未读到 `post_fatal` 报告；不是本卡改动，基线不可用，继承关系不能判定。 |
| WebSockets 未 pin | pytest 9.1.1 / pytest-asyncio 1.4.0 / aiohttp 3.14.3 / httpx 0.28.1 / websockets 17.2 | 482 passed, 3 skipped，234.00 秒 | 全绿。 |

三项真实 skip 原因保留：`tests/test_aligner_integration.py:53`、`:62` 是 ForceAligner 后端/模型未安装；`tests/test_segmenter.py:208` 是缺 Silero-VAD 模型或 onnxruntime。没有 HTTP 或 ffmpeg skip 冒充通过。

另有一次无效启动记录：首轮指定的隔离 `TMPDIR` 子目录未创建，部署脚本 6 例均在 `mktemp` 前失败；该次 `476 passed, 3 skipped, 6 failed` 不作为产品结果，已与上述有效运行分开。

## 五轮窄矩阵与真实消费环境

五轮均使用完整模块集合，无 `-k`：

```text
tests/test_http_qa_e2e.py tests/test_http_supervision.py tests/test_http_file_tasks.py
```

每轮在自有临时根的 `narrow-matrix/run-N`、独立 `TMPDIR` 下执行；实际命令为固定 WebSockets 15.0.1 套件命令加上述三个模块。每轮单独 `flock --timeout 600`，拿锁后 `timeout 900s`，退出即释放。五轮均在同一 source SHA `3d26d90b707003cbbc0b31d8d0e2e1f823f4d2a3` 执行：

| run | 结果 | 用时 |
|---:|---|---:|
| 1 | 49 passed，exit 0 | 54.41 秒 |
| 2 | 49 passed，exit 0 | 52.96 秒 |
| 3 | 49 passed，exit 0 | 53.98 秒 |
| 4 | 49 passed，exit 0 | 55.27 秒 |
| 5 | 49 passed，exit 0 | 54.70 秒 |

`test_http_supervision.py:298-317` 的 `_run_bare_probe` 每轮只白名单传递 `PATH`、`HOME`、`PYTHONPATH`、语言和端口/数据目录等非秘密变量；因此裸 shell 消费环境随五轮实际执行各覆盖一次。另按既有 fixture 运行自有 user-systemd 短消费 `tests/test_http_cleanup.py::test_normal_sigterm_still_exits_zero[systemd-unit]` 五次，结果依次均为 `1 passed`（0.57、0.54、0.62、0.69、0.59 秒）；fixture 使用 port 0、独立 SQLite、瞬态 unit、独立 PID/cgroup、合法 stub 模型，TCP、ffmpeg、Queue、worker 均为真实边界。

跨边界证据不是同进程手造字典：`tests/test_http_file_runner.py:112-145` 的真实 ffmpeg wrapper 记录实际 argv/env，`:213-230` 建立 multiprocessing Queue 和识别子进程，`tests/harness/worker.py:92` 消费真实 Queue；`tests/test_http_qa_e2e.py:378-450` 的 `RecordingProxy` 逐字节记录真实 SDK TCP body，`:495-560` 记录丢响应后的真实请求序列，`:612-718` 对独立 ffmpeg 参考 PCM 与 worker 实收 `Task.data` 做完整 SHA-256 对齐。监督重启 producer 载荷落在 `tests/test_http_supervision.py:577-620` 的真实文件，不把响应正文、令牌、环境秘密或 provider URL 写入本报告。

## 十二组不变式对照

| 组 | 当前实现位置 | 本次/既有实际测试与 producer 证据 |
|---:|---|---|
| 1 二进制 producer | `sdk/capswriter_asr/http_client.py:438-549`；`core/server/http_store.py:628-677` | `test_http_qa_e2e.py:378`：真实 SDK、代理线缆、落盘文件长度/字节/SHA 与源一致；创建 JSON 与 PATCH 原字节分离。 |
| 2 脱离连接 | `core/server/http_file_runner.py:204-265`、`core/server/http_store.py:699-750` | `test_http_file_runner.py:341-442`、`test_http_file_tasks.py:416-465`：提交连接关闭后新连接取完整结果，HTTP owner 与 WS 不混。 |
| 3 幂等创建/提交 | `sdk/capswriter_asr/http_client.py:572-627`；`core/server/http_server.py:546-584` | `test_http_qa_e2e.py:495-560`：commit 响应真实发出后被丢弃，只显式 GET 恢复；POST/commit、Job、ffmpeg、Queue 段数均证明只识别一次。 |
| 4 offset 恢复 | `core/server/http_store.py:628-677`；`sdk/capswriter_asr/http_client.py:529-556` | `test_http_file_tasks.py:272-315` 统计真实未确认重发字节；`test_http_supervision.py:503-574` 覆盖 offset 前与 ACK 前 SIGKILL，文件尾不冒充确认。 |
| 5 部分上传重启 | `core/server/http_store.py:341-350`、`:628-677` | `test_http_supervision.py:503-574` 和 `test_http_file_runner.py:747-808`：确认前缀、文件身份、partial 保留；旧 QUEUED/RUNNING 变 `FAILED[server_restarted]`，不自动重跑。 |
| 6 结果跨重启 | `core/server/http_file_runner.py:204-265`；`core/server/http_store.py:874-907` | `test_http_supervision.py:577-620` 使用真实 producer 文件载荷跨进程核对；`test_http_cleanup.py:280-350` 验证源清理后结果仍可领取。 |
| 7 双 owner 并发 | `core/server/state.py:69-98、318-326`；`core/server/worker/process_manager.py:68-94` | `test_http_qa_e2e.py:114-278`：真实 WS/HTTP 同时经过同一 Queue/worker，三元 key、socket、Result sink 不串；空/断 WS 均有真实 TCP 行为。 |
| 8 取消与 I/O 交错 | `core/server/http_server.py:528-543`；`core/server/http_store.py:628-677` | `test_http_file_tasks.py:619-740`：cancel-first 与 io-first 各 5 次，真实 TCP handler、worker Future、文件字节和 SQLite offset 对齐。 |
| 9 final/额度边界 | `core/server/state.py:30-98`；`core/server/http_server.py:546-584`；`core/server/http_store.py:699-750` | `test_http_file_tasks.py:1158-1565`：WS 预留、DB+内存不重复计数、并发准入锁、重复 commit 与新 Job 的 429；真实 payload/SQLite 状态可读。1 GiB/16 GiB/2 GiB 未做真实体量压测。 |
| 10 PCM producer | `core/server/http_file_runner.py:87-166、469-543`；`core/server/segmenter.py:245-259` | `test_http_qa_e2e.py:612-718`：44.1 kHz stereo 与 8 kHz mono 两参数，真 ffmpeg、16 kHz mono f32、有界段、offset/overlap/tail 和每段完整 SHA；参考段非全零。 |
| 11 整任务失败 | `core/server/http_file_runner.py:381-400、469-505`；`core/server/worker/pipeline.py:162-208` | `test_http_qa_e2e.py:723-783`：最后 `is_final` 段失败时无缺段 DONE；既有 runner 测试覆盖中段、ffmpeg、结果超限、worker 崩溃、未知异常和 SIGTERM。 |
| 12 清理/旧 WS | `core/server/http_store.py:779-803`；清理监督在 `core/server/http_server.py:280-300` | `test_http_cleanup.py:146-820`、`test_http_capacity.py:311-912` 覆盖 TTL、活跃引用、重启和同 worker 清理；旧 WS 由 `test_server_e2e_baseline.py`、`test_backpressure.py`、`test_health.py`、`test_error_codes_contract.py`、`test_protocol_v2.py`、`test_segmentation_contract.py` 回归。 |

## CI 身份与边界

真正的 merged-main 同 SHA 是 [master push CI 37260999978](https://github.com/zlxlabs/CapsWriter-ASR-Server/actions/runs/37260999978)：head 为 `3d26d90`，3 个 job 全部 SUCCESS。PR73 的正式 fullready gate 是 [37258495073](https://github.com/zlxlabs/CapsWriter-ASR-Server/actions/runs/37258495073)，head 为候选 `5db84d3`，8 个 job 全部 SUCCESS；候选的 [CI 37258462419](https://github.com/zlxlabs/CapsWriter-ASR-Server/actions/runs/37258462419) 为 3 个 job 全部 SUCCESS。draft [37258462809](https://github.com/zlxlabs/CapsWriter-ASR-Server/actions/runs/37258462809) 的 primary/部分 gate 是 skipped/cancelled，不计正式绿。

上述 Hosted CI 各自只证明该 run 的一次 workflow 消费，没有真实五轮窄矩阵证据；本地五轮不能移植成 Hosted CI 五轮。因而本文件不宣称 M6 Goal 已 Done，也不宣称真实 ASR 质量、生产鉴权、硬 2 GiB 峰值保障或真实 16 GiB 体量压测。
