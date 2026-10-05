# C2 当前主干收口证据

<!-- 本文只记录本次候选树的脱敏实测事实；不记录认证值、内容哈希、私有音频、
     根目录地址、完整环境、profile 或 session 标识。 -->

## 范围与合入结果

- 验证基线：`c2818c5cba71ac86ddc0da1bee54538d34cdfe6b`。
- 已用 `git merge --no-ff` 合入正式主干 `3d7436c499829eb8bb92fc3757b6e4968c88e548`，
  再用正常 merge 合入既有风险证据 `b4d667cf389a27c43034b418358f89223841cebe`。
  两次均无冲突，合并提交保留了两条历史；提交身份为当前执行器身份，不是 lead 代签。
- `git diff c2818c5..HEAD --name-only` 的文件全部落在卡面 scope：
  `.github/workflows/ci.yml`、`sdk/**`、主干已审 SDK 测试、`docs/**`。
  本文是本次唯一新建文件；没有改写旧 C2 证据、旧 fixture 或历史报告。
- 以下六个 C2 源/夹具文件相对基线逐一做字节比较，结果均为 `equal=true`：
  `core/server/app.py`、`core/server/http_server.py`、`core/server/http_store.py`、
  `tests/fixtures/__init__.py`、`tests/fixtures/http_fatal_exit_probe.py`、
  `tests/test_http_cleanup.py`。候选中的 SDK/CI 变化只来自已审正式主干。
- 候选仍未部署生产；本次没有修改应用或 SDK 行为，也没有修复 P2、添加重试、
  fallback、释放账本或新测试。

## 全量测试

两次套件串行执行，均从候选新 HEAD 加载，使用 `-p no:cacheprovider`：

```text
uv run --no-project --python 3.12 --with numpy --with rich --with websockets==15.0.1 --with colorama --with pytest==9.1.1 --with soundfile --with pytest-asyncio==1.4.0 --with aiohttp==3.14.3 --with httpx==0.28.1 python -m pytest tests/ -q -rs -p no:cacheprovider
```

固定 websockets：

- Python 3.12.3、websockets 15.0.1、pytest 9.1.1、pytest-asyncio 1.4.0、
  aiohttp 3.14.3、httpx 0.28.1。
- `476 passed, 3 skipped, 149 warnings`，约 223.57 秒，退出码 0。

最新 websockets：

- Python 3.12.3、websockets 17.2；其余依赖版本同上。
- `476 passed, 3 skipped, 149 warnings`，约 226.02 秒，退出码 0。

三项 skip 均是当前测试环境明确报告的资源缺失，不是收集错误或新红：

- `tests/test_aligner_integration.py` 的 ForceAligner 后端/模型未安装，两项；
- `tests/test_segmenter.py` 缺 Silero-VAD 模型或 onnxruntime，一项。

第一次固定套件启动时，外层日志包装器未向子进程传递私有目录，三个重定向得到
`Permission denied`，没有进入 pytest；该次退出码 1 记为取证脚本启动失败，不计入
测试套件结果。修正后通过终端原生长任务执行了唯一一次实际固定套件，没有重试已执行
的测试。

## 真实 SDK→TCP HTTP→ffmpeg/FileRunner 入口

复用了现有
`tests/test_http_file_runner.py::test_real_container_upload_then_other_connection_takes_done_result[mp3]`
producer，不在本卡复制同进程对象。该用例使用已合入的 SDK，真实 TCP HTTP 上传和
提交，真实 `HttpFileRunner`、真实 multiprocessing worker 以及真实 ffmpeg；识别引擎
是该 fixture 明确声明的 stub，只验证协议和跨进程边界，不宣称模型质量。

裸 shell 与 systemd unit 各运行一次同一用例；两次均为 `1 passed, 3 deselected`，
退出码 0。systemd unit 收尾时的结构化状态为 `Result=success`、`ExecMainStatus=0`、
`ActiveState=inactive`，并已按 `--collect` 回收。

两入口逐字段脱敏事实完全一致：

| 边界 | 实测事实 |
|---|---|
| SDK/HTTP producer | 恢复文件存在；真实上传完成并由另一连接读取终态 |
| 上传/任务 | `upload_state=COMMITTED`、`job_state=DONE`、`error_code` 为空 |
| 结果持久化 | SQLite `results` 1 行；`type=file`、`is_final=true`；字段名集合包含 `task_id`、`text`、`text_accu`、`tokens`、`timestamps`、时序字段和 owner 字段 |
| 源字节 | 60,489 字节；上传记录与磁盘源字节相等（只记布尔结论，不写内容哈希） |
| ffmpeg producer | start/end 各 1；真实子进程退出 0；argv 含 `-nostdin`、错误级别、具体源输入、16000 Hz 单声道、`f32le pipe:1`；测试 env marker 和 PATH shim 均命中 |
| 解码产物 | 1,280,000 字节 PCM；同一源重复解码的 full-hash 稳定（不输出哈希值） |
| 资源收尾 | runner teardown 断言识别子进程 join 后不存活、队列 feeder 线程退出并关闭 Manager；没有临时 PCM 文件，active job/task 已清空 |
| 脱敏 | 认证值、哈希值和音频均未写入本证据文档或脱敏摘要；fixture token 仅在进程内使用 |

该 producer 测试在退出 worker 后重新打开 SQLite，仍断言存在 1 条结果和 1 条
`DONE` 任务。源、结果和资源释放的不变式由测试中的真实文件、SQLite 独立连接、
producer 记录和进程 join 断言共同锁定。

## HTTP 终态、重开和生命周期不变式

当前全量套件中已执行并通过以下既有不变式：

- `tests/test_http_cleanup.py::test_periodic_cleanup_waits_for_real_runner_reference_then_keeps_result`
  通过真实 TCP HTTP 创建/提交，验证 runner 持有引用时源不删除，释放后才清理；
  `DONE` 与结果 payload 保留，重复提交复用原 Job，不重新处理；非终态、未登记源和
  过期 partial 字节保留，过期上传返回 410。
- `tests/test_http_file_tasks.py::test_persisted_done_result_is_served_after_reopen`
  通过新 listener/新连接验证同一 Job 的持久结果可重新读取；结果字段仍由 SDK
  解码交付，未从内存对象猜测。
- `tests/test_http_cleanup.py` 中的真实进程边界矩阵覆盖 naked-shell 与 systemd-unit：
  `fatal_cleanup_exits_process_and_reaps_children`、`normal_sigterm_still_exits_zero`、
  `http_startup_failure_exits_nonzero_without_hanging_worker`、
  `http_disabled_keeps_default_websocket_lifecycle`。每个入口均断言真实 worker/
  Manager PID 消失或 cgroup 清空；fatal 入口还断言源字节、`DONE/COMMITTED` 和结果
  payload 不变，正常 TERM 与 HTTP disabled 语义不变。
- SDK71 watchdog 合同由主干带入的 `tests/test_sdk_deadline_stage.py`、
  `tests/test_sdk_no_wait_for.py` 等当前测试锁定；本卡只验证，没有重写。

## 校验与未覆盖范围

- `git diff --check c2818c5cba71ac86ddc0da1bee54538d34cdfe6b..HEAD`：通过。
- 全量测试的继承红基线在派发时不可用，因此继承红与新红无法做历史作业对照；
  本次实际套件没有新失败。
- 未做生产部署、真实模型质量验证、真实生产认证验证、Restart-on-failure 部署
  重启验证，也未把同 owner fixture 的结果外推为全面 no-leak 安全保证。
- 未追查卡面明确保留的历史未知；本文件只记录本次当前主干可直接复核的事实。
