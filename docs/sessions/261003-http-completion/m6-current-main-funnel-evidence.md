# M6 当前主干接续冻结 QA 的消费验证

<!-- 本文只记录本次候选树的脱敏实测事实。不写认证值、私有音频内容哈希、
     完整环境、profile、session 或凭据。解码/合成素材的私有摘要只留在 /tmp。 -->

## 范围与合入结果

- 验证基线（正式 master）：`4de4a7ffa44dfb50b48c252510927c4b2166cc77`
  （`origin/master` / `Merge pull request #62`）。
- 冻结 QA：`ad3c9cb56ba836c0f6ba3d2c0fa95b2001d50925`
  （`origin/card/http-m6-qa-261003`）。
- merge-base 实测为 `5134720e058e0e9ae3d3feddebf4942f8bf7ed7a`。
- 已用 `git merge --no-ff` 合入 ad3，无冲突。合并提交
  `14153dbbcf9f62e085b89cc3a70811468114f1e6` 的双亲恰好是 `4de4a7ff` 与 `ad3c9cb`。
  没有 squash / rebase / cherry-pick。
- `git diff --name-only 4de4a7ff..14153db` 只有 9 条路径，全部落在卡面允许集合：
  `docs/sessions/261001-http-files/qa.md`、
  `docs/sessions/261003-http-completion/m6-qa-evidence.md`、
  `progress/m6-qa-progress.md`、`progress/m6-review1-progress.md`、
  `progress/m6-review2-progress.md`、`reviews/m6-review1-verdict.md`、
  `reviews/m6-review2-verdict.md`、`tests/harness/worker.py`、
  `tests/test_http_qa_e2e.py`。
- 上述 9 个路径相对 ad3 的 git blob 全部 `equal=true`。本次没有手改测试、
  应用、SDK、CI 或旧文档。
- `core/`、`sdk/`、`start_*`、`config_*`、`.github/`、`pyproject.toml`、
  `.pre-commit-config.yaml`、`hot-server.txt` 共 226 个文件相对 4de4 全部
  `equal=true`。主干已合入的 SDK / C2 只作为 Base 真实源，不是本卡实现。
- 当前加载文件身份（HEAD blob）：
  - `design.md` `2c374ef61688e315327b98bb2592d1f50e78925c`（与 ad3 相同）
  - `qa.md` `7497fcf379391a8eb1430cf17c1c43ce190d8ba5`（ad3 文本，不是 master 夹具）
  - `m6-qa-evidence.md` `2ed3eee51b1e6281dd3aed21a69762e31eb88b02`
  - `m6-review1-verdict.md` `2bb1379dc8531b1c4fa5f0564ee69cdb30f02a8b`
  - `m6-review2-verdict.md` `f14eecf89527770f992a7772e3e0943788e32d68`
  - `tests/harness/worker.py` `ca59437e54426d744ae6448b3d03919fd49621ec`
  - `tests/test_http_qa_e2e.py` `c75376d31b7630da3d513d980634d0d6f9080aa0`
- 历史仍在合并图里：`30f7474`（5 函 6 案进度）→ `52a748c`（卫生）→
  `1cd07fe`（组 10 内容哈希纠正）→ `aa39e7f`（R1 收口）→ `560db3a`（R2 收口）→
  `ad3c9cb`（十二组索引转录）。ad3 的十二组索引不是新的第三轮冷审。
- 本文与 `progress/m6-current-main-funnel-progress.md` 是本次唯一新建文件。

## 全量测试（两套 CI 栈）

两次套件串行执行，共享
`flock --timeout 600 /home/zlx/.cache/caps-http-261005-fullsuite.lock`，
拿到锁后再 `timeout 900`。等锁失败会 fail-loud，没有重试、没有扩大 900 秒。
锁等待与执行分开记账。隔离由既有测试的 `tmp_path` + port 0 完成，
没有按名字杀进程，也没有动原系统 PATH。

固定 websockets：

- 命令：`uv run --no-project --python 3.12 --with numpy --with rich --with websockets==15.0.1 --with colorama --with pytest==9.1.1 --with soundfile --with pytest-asyncio==1.4.0 --with aiohttp==3.14.3 --with httpx==0.28.1 python -m pytest tests/ -q -rs -p no:cacheprovider`
- Python 3.12.3、websockets 15.0.1、pytest 9.1.1、pytest-asyncio 1.4.0、
  aiohttp 3.14.3、httpx 0.28.1。
- 锁等待 0.003 s，执行 231.231 s，pytest 墙钟 230.56 s，退出码 0。
- `482 passed, 3 skipped, 163 warnings`。

未钉 websockets（实际解析白名单）：

- 同一命令去掉 `==15.0.1`。
- Python 3.12.3、websockets **17.2**；其余依赖同上。
- 锁等待 0.003 s，执行 229.842 s，pytest 墙钟 229.38 s，退出码 0。
- `482 passed, 3 skipped, 163 warnings`。

3 个 skip 身份（`-rs`，两套相同，不是新 skip）：

- `tests/test_aligner_integration.py:53` ForceAligner 后端/模型未安装
- `tests/test_aligner_integration.py:62` ForceAligner 后端/模型未安装
- `tests/test_segmenter.py:208` 缺 silero-VAD 模型或 onnxruntime

相对 C2 主干收口当时的 `476 passed`，本次净增 6 条，等于 QA 冻结文件里的
5 个函数 + 重采样矩阵 2 参数。没有 HTTP / aiohttp / ffmpeg 缺失类 skip。
`tests/test_http_file_runner.py:55` 的 ffmpeg `pytestmark` 与
`tests/test_http_qa_e2e.py:61` 的 aiohttp `importorskip` 仍在，没有摘掉。

## 六条 e2e：裸 env -i 与自有 systemd

命令均为
`python -m pytest tests/test_http_qa_e2e.py -q -rs -p no:cacheprovider`，
同样先拿共享 flock。白名单只有 PATH / HOME / USER / LANG / LC_ALL / TMP* /
XDG_CACHE_HOME / UV_*，没有 token、webhook、profile 或 `CLI_API_TOKEN`。
源 WAV 由测试内 `make_pcm_container` 现造，不读私有媒体。

| 入口 | 计数 | 退出 | 锁等待 / 执行 |
|---|---|---|---|
| `/usr/bin/env -i` + 白名单 | `6 passed, 14 warnings`，0 skipped，7.87 s | 0 | 0.003 s / 8.280 s |
| 自有 user unit `m6-funnel-e2e-1791167787-1754287` | journal：`6 passed, 14 warnings`，7.61 s | unit `Result=success`、`ExecMainStatus=0`、`ActiveState=inactive`、`SubState=dead`、`NRestarts=0` | 0.003 s / 8.406 s（unit runtime 8.379 s） |

既有测试已经锁住 producer 边界，本卡没有再复制一份内存模拟：

- 组 1：真实 SDK PATCH 拼接字节 == 源文件；服务端 `sources/{id}.bin` 长度/SHA 与源一致。
- 组 3：丢掉唯一一次真实 202 后显式恢复；`/commit` 恰好 1 次，SQLite 1 条 job。
- 组 7：真 WS + 真 HTTP 共用一个 worker；`owner_kind` / `socket_id` / `task_id` 不串。
- 组 10：测试进程独立跑系统 ffmpeg 得到 16 kHz mono f32 参照；worker 子进程
  `queue_in.get()` 到的 `Task.data` 完整 SHA 与参照切片相等；argv 末段为
  `-ar 16000 -ac 1 -f f32le pipe:1`；参照片非全零。
- 组 11：末段推理失败 → 任务 `FAILED`，不发布缺段成功结果。
- 识别引擎是 fixture 声明的 stub，合法；没有 mock 网络 / Task / ffmpeg 冒充 Real SDK。

旧红验「同长度全零 PCM」与「自动重发 commit」只引用原提交
`1cd07fe` / `tests/test_http_qa_e2e.py` 既有断言，本卡不再做新 floor。

## 十二组消费索引（指向已执行测试，不产生新审查结论）

下列测试都出现在两次 482 passed 套件里。代码入口沿用 ad3 已入库的
`m6-review2-verdict.md` 转录表，这里只记「这次消费跑到了」。

| 组 | 被测代码 | 本次已执行的 consumer | 形状事实 |
|---|---|---|---|
| 1 二进制上传 | SDK `_finish_upload`；HTTP PATCH；`HttpStore` 写入 | `test_http_qa_e2e.py::test_real_sdk_upload_bytes_match_server_disk_sha`；`test_http_client.py` CLI 子进程；`test_http_file_tasks.py` 落盘 | 真实 TCP PATCH；磁盘源字节与声明一致（只记布尔） |
| 2 受理后断连领取 | `HttpFileRunner` sink；`HttpStore` 读结果；SDK `get_file_result_http` | `test_http_file_runner.py::test_real_container_upload_then_other_connection_takes_done_result`；`test_http_file_tasks.py::test_persisted_done_result_is_served_after_reopen` | 新连接领取；payload 来自 worker 真 Result |
| 3 幂等与显式恢复 | SDK `_request` / `_commit_upload` / `resume_file_http` | `test_http_qa_e2e.py::test_lost_commit_response_recovers_with_exactly_one_recognition` 及既有 client/runner 用例 | 识别恰好一次 |
| 4 可信续传 offset | SDK seek；`HttpStore.append_bytes` | `test_http_client.py` / `test_http_file_tasks.py` 续传用例 | 只发未确认后缀 |
| 5 部分上传跨重启 | store 恢复；监督 | `test_http_supervision.py::test_http_offset_crash_windows_recover_in_new_processes` | 新进程核对磁盘/offset |
| 6 结果跨重启 | store 结果事务 | `test_http_supervision.py::test_result_producer_payload_and_done_survive_new_process`；cleanup 周期用例 | 重开后结果仍可读 |
| 7 双 owner 并发 | `derive_owner_id` / `make_task_key`；WS + HTTP runner | `test_http_qa_e2e.py::test_real_ws_and_http_share_one_worker_without_key_pollution` | 真 Queue，key 不污染 |
| 8 取消与 I/O 交错 | handler / IoWorker / append | `test_http_file_tasks.py::test_handler_cancellation_and_io_completion_orders_preserve_confirmed_bytes` | 可信 offset 保留 |
| 9 资源边界 | store guard；准入 | `test_http_file_tasks.py` 负例矩阵；`test_http_capacity.py` | 错误显式返回，旧字节不被覆盖 |
| 10 解码与 PCM | `FileSourceDecoder`；共享 segmenter；`harness/worker.py` | `test_http_qa_e2e.py::test_resampled_sources_produce_bounded_16k_mono_f32_segments`（stereo44 / mono8k） | 16 k mono f32；offset/overlap/tail 由独立 ffmpeg 对齐 |
| 11 整任务失败 | `handle_audio_task`；`fail_job` | `test_http_qa_e2e.py::test_final_segment_failure_fails_job_without_publishing_partial` | FAILED，无缺段成功 |
| 12 源清理与旧 WS | cleanup；旧 WS 回归 | `test_http_cleanup.py` 终态/引用/周期清理；全量旧 WS 套件 | 终态源可清，结果保留；旧 WS 未因 HTTP 改语义 |

TTL 只引用已有测试/源码，不猜：`UPLOAD_TTL_SECONDS == 7 * 24 * 3600`
（`tests/test_http_store.py:384`，定义在 `core/server/http_store.py:49`）；
`SOURCE_RETENTION_SECONDS` 同样是 `7 * 24 * 3600`（`:50`）。
design / 测试里没有 48 小时常量，本文不补造。

未知资源状态不默认 gone：ffmpeg / ForceAligner / Silero 缺失分别表现为
assert 失败或上述 3 个具名 skip；systemd 侧用 `Result` / `ExecMainStatus`
两态，查不到与值不同分开记。

## 校验与未覆盖

- `git diff --check 4de4a7ffa44dfb50b48c252510927c4b2166cc77..HEAD`：通过。
- 派发时刻主干基线 `gh api request failed`，继承红 **未能判定**。
  本次两套全量与两次 e2e 没有新失败。
- 旧「commit 读超时 / 并发预算」一次红的根因仍以原进度档为准；今天的绿
  不追认历史因果（见 `progress/m6-qa-progress.md` 既有记录，本文不覆写）。
- 未做真实 ASR 质量、真实录音、三平台生产部署、1 GiB / 16 GiB / 2 GiB
  体量压测。假引擎 stub 只证明协议与跨进程边界。
- 叶执行器不开 PR / ready / rerun / 签名 / merge / 部署。
  候选供主脑更新 PR 73 正文后走完整 Gate。
