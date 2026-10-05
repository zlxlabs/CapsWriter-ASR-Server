# M6 无会话裸壳收据（新运行时点，不追认旧声明）

## 0. 旧收据能不能用

H2 实现树 `77940745146d377d780e1f840bfbfd633740c114` 上**没有** owned `.tmp-h2*` 目录或文件，也没有 `env-i-named.sh`。
f382 交付文写了「脚本 `env-i-named.sh`（`env -i` + 具名模块）」和一张裸臂表，但指定输入里没有实际外发 argv、child 环境角色、returncode、时钟、源固定收据。
只见脚本名/JSON 标签/报告声称，不能 retro 认证；该时点 **unknown 原保**。
c6 双臂 `run_arm.sh` 在 flock 内直接 `uv run … python -m pytest tests/`，继承调用方环境，**不是** `env -i`，不能充 bare。
前 artifact 派发 `dlg-20261005-183710-6a1454`：通知 TIMEOUT exit 1，envelope `is_final=false`，报告 0 字节，unit `LoadState=not-found`，默认 Exec 0 **不成功**，不重签。
本卡只补一次具名无会话入口。不跑 full、不另开 fixture 凑 5、不跑模块其余 11 条、不跑 500、不改源。

## 1. 源绑定（运行时实际 c6）

工作树 HEAD 实测 `c6a17380c441263de05399977f8b1228ffd1682a`。
`git ls-tree -r -z` 过滤 `docs/`：nonDoc **340**，与 CodeH2、与 f382 摘要相同（同码不同 Doc）。
已知否定：合法不同 H1 树 `6b129a73a5520bd36021cb2f818d5e7e0a66fe0a` ≠ H2 树 `e260c171001c9f56ee94adc4cf572022ddae91fe`。
坏引用 `git cat-file` 退出 **128**（与「查不到」分态）。
`tests/test_http_qa_repeat_matrix.py` `_source_sha()` 读 `git rev-parse HEAD`。
本卡 trace `source_sha` = **c6 全文**，不是 779/f382 手写标签。child 观测 `git status --porcelain` 长度 0。

## 2. 实际 `env -i` 生产者边界

具名入口（唯一 pytest 节点）：

`python -m pytest tests/test_http_qa_repeat_matrix.py::test_five_round_same_service_concurrency_cancel_restart_ws -q -rs -p no:cacheprovider --junitxml=<owned>`

外层真实 argv 以 `/usr/bin/env` `-i` 开头，再跟白名单赋值，再跟 owned venv 解释器与 child observer。
白名单键：`HOME`、`PATH`、`TMPDIR`、`M6_REPEAT_MATRIX_ARTIFACT_DIR`、`LANG`、`LC_ALL`、`PYTHONNOUSERSITE`、`PYTHONDONTWRITEBYTECODE`。
`PATH` 只有 venv `bin` + `/usr/bin` + `/bin`（ffmpeg/git 在 `/usr/bin`）。
child observer 只记指定会话键的 present/length/role、包版本、源 SHA，然后
`os.execv(sys.executable, [sys.executable, '-m', 'pytest', …])`。
未调用 `pytest.main`，未改仓库插件。exec argv 收据含 `-m pytest` 与具名 node。
child 实测 environ 键恰好是上述白名单，没有 `DELEGATE_*`。
下列会话键全部 `absent`、length=0：`DELEGATE_DISPATCH_ID`、`DELEGATE_REPORT_PATH`、`DELEGATE_TASK_ID`、`DELEGATE_CARD_PATH`、`PI_LEAD_SESSION`、`PI_SESSION_ID`、`HERDR_PANE_ID`、`HERDR_TAB_ID`、`HERDR_AGENT_SESSION`、`CLAUDE_CODE_SESSION_ID`、`CODEX_THREAD_ID`、`KIMI_LEAD_SESSION`、`CURSOR_SESSION_ID`、`TERM_SESSION_ID`、`SSH_CONNECTION`、`SSH_CLIENT`。
明确停止：未读、未核、未哈希 `CLI_API_TOKEN`；未全量 dump 环境。
解释器：uv `--python 3.12` owned venv；venv `python` 是指向 CPython 的符号链接，**不得** `Path.resolve()` 丢掉 `pyvenv.cfg`。
child 实测包：websockets **15.0.1**、pytest **9.1.1**、pytest-asyncio **1.4.0**、aiohttp **3.14.3**、httpx **0.28.1**、numpy **2.5.3**、rich **15.0.0**、colorama **0.4.6**、soundfile **0.14.0**。
runtime `python-3.12`。parent returncode **0**，墙钟 37.313 s，未触 180 s 超时。
stdout 末行 `1 passed, 30 warnings in 36.19s`。
JUnit：1 testcase，failures=errors=skipped=0。不把这 1 条 XML 当成 5 次；五轮来自源码 `for round_id in range(1, REPEAT_COUNT + 1)`。

启动器在 pytest 之前的两次失败**不是**矩阵结果，原件保留、不冒充红/绿：

1. `uv run --with` 打印的 `sys.executable` 落在构建临时目录，父进程退出后路径消失，`env` 报 No such file（exit 127）。
2. 对 venv `python` 做 `Path.resolve()` 得到系统 `/usr/bin/python3.12`，conftest 缺 numpy，pytest usage error 4。

无自动 retry。真矩阵红会停并 failed。

## 3. 五轮相位（同一 persistent-httpdata）

每轮相位集合均为 `concurrency`、`cancel_io`、`restart`、`legacy_ws`。
`data_dir_role=persistent-httpdata`，`ffmpeg_argv_real=true`。
cancel-first：pending=1、mailbox=31、held=true；io-first：pending=0、mailbox=32、held=false。
`pcm_segment_oracle_ok=true`，`http_source_bytes_match=true`，`result_payload_equal=true`，`ws_on_restarted_instance=true`。

| 轮 | ffmpeg offset / start |
|---:|---|
| 1 | 0 / 3 |
| 2 | 6 / 3 |
| 3 | 12 / 4 |
| 4 | 19 / 3 |
| 5 | 25 / 4 |

offset 是日志事件下标，start 不必恒 4。消费者仍是 CodeH2 schema-only；全重标 clone 仍会被接受。本文件只证 producer 循环与 child 环境。

## 4. 与 Hosted / full 分层

Hosted 五轮：CI run `37339081182`、artifact `11356924649`、merge checkout `8f9a0ec4…`（树同 H2）。本卡不下载、不重跑、不抬旧 H1。
c6 双臂 full JUnit 各 514 cases / 511 passed / 3 skip，websockets 15.0.1 与 17.2，运行时继承环境。
裸与 Hosted 是不同实际 runtime。私有 argv / JUnit / trace 0600 留本机，不入库、不写宿主路径。
