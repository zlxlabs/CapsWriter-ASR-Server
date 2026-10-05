# C2 合并主干正式窄验收

<!-- 仅记录当前正式主干的脱敏事实；不写认证值、原始音频/文本、IP、根目录、
     环境 profile、secret 或其摘要。本文不替主脑判断 M4 总体完成。 -->

## 结论与边界

- 验收对象是已合入 `master` 的 `4de4a7ffa44dfb50b48c252510927c4b2166cc77`，不是
  新冷审轮。当前树只落本卡两份文档，不改应用、SDK、tests、workflow、config、旧证据、
  GOALS 或账本。
- 本地正式验证的两套 Python 3.12 全量 suite 均退出 0：各 `476 passed, 3 skipped,
  149 warnings`；3 个 skip 都是资源缺失，不是收集失败。主干 CI 同 SHA 的 3 个 job
  也均为 `completed/success`。overall M4Done 仍由主脑验收后更新。

## 1. 合并身份、候选树与加载来源

- `git log`：HEAD 是 merge `4de4a7f`，父提交为 `3d7436c` 与 `7a3a964`；提交时间
  `2026-10-05T01:50:12Z`。独立 `git ls-remote origin refs/heads/master` 返回非空且
  为同一 SHA。`git rev-parse HEAD^{tree}` 与 candidate `7a3a964` 的 tree 均为
  `91812b...`，明确为同树不同历史；PR62 的 `headRefOid=7a3a964`、merge SHA 为
  `4de4a7f`、状态 `MERGED`。
- PR62 检查真实结论：3 个测试、`gate / classify_pr_paths`、quality、primary、
  resolve_advisory、gate、OCR、ledger 均 `SUCCESS`；notify 是 `SKIPPED`，不是 primary
  skip。合入时间与上项一致。
- 用当前 HEAD 工作树启动全量 pytest，并用独立 source probe 校验 6 个文件：
  `core/server/app.py`、`core/server/http_store.py`、`core/server/http_server.py`、
  `tests/fixtures/__init__.py`、`tests/fixtures/http_fatal_exit_probe.py`、
  `tests/test_http_cleanup.py`。六个模块/文件的加载路径均指向当前树，字节均与
  `git show HEAD:<path>` 相同；结果为 `source_probe=pass files=6 head=4de4...`，不是
  旧 import cache。`tests/test_http_config.py` 另以真实裸子进程核对仓库与依赖来源。

## 2. 本卡预算内的实际 suite

每套独立使用既定共享 flock 路径 `caps-http-261005-fullsuite.lock`；排队最多 600 秒，
取得锁后 `timeout 900s`，一套结束立即释放锁。排队和执行分别计时，没有把排队算入
900 秒，也没有对已执行的 pytest 自动重试。

```text
uv run --no-project --python 3.12 --with numpy --with rich --with websockets==15.0.1 --with colorama --with pytest==9.1.1 --with soundfile --with pytest-asyncio==1.4.0 --with aiohttp==3.14.3 --with httpx==0.28.1 python -m pytest tests/ -q -rs -p no:cacheprovider
uv run --no-project --python 3.12 --with numpy --with rich --with websockets --with colorama --with pytest==9.1.1 --with soundfile --with pytest-asyncio==1.4.0 --with aiohttp==3.14.3 --with httpx==0.28.1 python -m pytest tests/ -q -rs -p no:cacheprovider
```

| suite | 锁排队 | 锁内执行 | 结果 |
|---|---:|---:|---|
| Python 3.12 + websockets 15.0.1 | 183.967s | 225.732s | 476 passed, 3 skipped, 149 warnings |
| Python 3.12 + 最新 websockets（17.2） | 212.409s | 224.204s | 476 passed, 3 skipped, 149 warnings |

`-rs` 的三个 skip 为 `test_aligner_integration.py:53/62`（ForceAligner 后端/模型缺失）
和 `test_segmenter.py:208`（Silero-VAD 模型或 onnxruntime 缺失）。没有非零 suite 或
锁超时；本机共享锁确实与同时 M7 suite 排队，未改预算、端口、SQLite、unit 或生产服务。

## 3. 同 SHA 主干 CI 与继承红

主干 CI run [37252990501](https://github.com/zlxlabs/CapsWriter-ASR-Server/actions/runs/37252990501)
的 `headSha` 是 `4de4a7f`，workflow 为 `CI`，run 与三个 job 均完成成功：

| job | 实际 pytest |
|---|---|
| Python 3.11 / websockets | `tests/test_sdk_*.py`，61 passed |
| Python 3.11 / websockets==15.0.1 | `tests/test_sdk_*.py`，61 passed |
| Python 3.12 / websockets | `tests/`，476 passed, 3 skipped, 149 warnings |

CI 实际解析到 pytest 9.1.1、pytest-asyncio 1.4.0、aiohttp 3.14.3、httpx 0.28.1；
3.11 的 SDK 矩阵差异由主干 workflow 的实际 `tests/test_sdk_*.py` 范围体现，不能用
本地 3.12 全量数字替代。派发时基线 API 为 `gh api request failed`，因此与同作业名、
首个失败步骤名的继承红无法比较，记录为“未能判定”；本次三套主干 job 与两套本地
suite 均无新红。

## 4. 不变式定位与已执行锁定

| 不变式 | 生产代码 | 已执行测试/真实证据 |
|---|---|---|
| `terminal_at` 起算 7 天；只清 DONE/FAILED、保留元数据与结果 | `HttpStore.cleanup_terminal_sources`、`HttpServer._source_cleanup_loop` | `test_store_cleanup_uses_terminal_boundary_and_keeps_every_other_source`；旧 `created_at`、非终态、NULL terminal、未登记源均保留 |
| runner 引用、非终态 Job、partial/EXPIRED partial 源保留 | `cleanup_terminal_sources` 的 active id 与 source-presence 路径 | `test_periodic_cleanup_waits_for_real_runner_reference_then_keeps_result`；真实 close 屏障释放前后分别断言 |
| EXPIRED 跨 SQLite 重开持久化并返回 410 | `HttpStore._row_for_token`、`UPLOAD_EXPIRED` | `test_expired_upload_is_410_and_metadata_kept` 与周期 HTTP 测试；旧 A1 正常路径及 PermissionError 反证文档已存在，source 字节不变 |
| DONE/result 重开可领；FAILED 保留 error_code；replay 不新建 Job/不重识别 | `HttpStore.job_record/get_result/commit_upload` | `test_persisted_done_result_is_served_after_reopen`、周期测试与 `test_repeated_commit_returns_same_job_without_resubmitting` |
| 真实 producer 跨 TCP/进程发出源文件、ffmpeg argv/env、16 kHz mono f32 PCM；不宣称模型质量 | `HttpFileRunner`、`sdk/capswriter_asr/http_client.py` | `test_real_container_upload_then_other_connection_takes_done_result`；真实 SDK/aiohttp TCP、ffmpeg 记录夹具、worker Task/Result、PCM 段边界和落盘结果均断言，识别引擎明确是 stub |
| fatal 非零退出且 worker/Manager/cgroup 资源 gone | `CapsWriterServer.start/_drain_after_fatal`、`HttpServer.report_fatal` | `test_fatal_cleanup_exits_process_and_reaps_children`；真实 `http_fatal_exit_probe` 注入 unlink PermissionError，源/Job/result 保留、监听关闭、子进程回收 |
| 正常 TERM 零退出；HTTP disabled 保持旧 WS 生命周期 | `CapsWriterServer.stop`、`resolve_http_settings` | `test_normal_sigterm_still_exits_zero`、`test_http_disabled_keeps_default_websocket_lifecycle`，裸 launcher 与 systemd launcher 矩阵均执行 |
| SDK watchdog 不是 SLA；3.11 不调用会吞取消的 `wait_for` | `sdk/capswriter_asr/http_client.py` | `test_auto_budget_formula_is_four_times_duration_plus_120`、`test_auto_budget_lets_93s_identification_finish`、`test_sdk_package_never_calls_wait_for` 及 planted-call 反证 |

A1 的旧正常/PermissionError 证据不重新读取受限私有 JSON，也不重复认证 token
哈希；本次只采信版本化文档、当前源码和全量测试。Restart-on-failure 部署重启、
真实模型质量和生产认证未测，不能外推为已覆盖；已有 8 组进程生命周期矩阵已执行，
不另编一套 probe。

## 5. 收口动作与未知

文档提交后只执行一次：

```text
python3 <runtime-release>/scripts/delegate/accept_precheck.py --dispatch-id dlg-20261005-015734-7ed447 --repo-path <本工作树> --commit-range 4de4a7ffa44dfb50b48c252510927c4b2166cc77..HEAD --timeout-sec 900 --verify-timeout-sec 1200
```

其 `scope` 只验证本卡两条文档，不替代 suite；`accept_precheck.json` 的
`status/main_sha_at_check/head_sha/commit_set` 与同 SHA CI 身份另存于派发报告。无需
重开旧资格、旧 09 或旧 unknown；不部署、不新 PR、不改默认分支。报告同时记录
首次独立 source probe 因 `/tmp` 脚本未注入 repo path 的启动失败，以及修正后唯一有效
probe 的通过结果。
