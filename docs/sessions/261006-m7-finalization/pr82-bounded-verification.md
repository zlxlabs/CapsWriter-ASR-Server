# PR82 原始失败收据与同环境有界验证

## 范围

只验证，不修复。两端 Git 身份固定为 `e849c217`（远端 master）与 `fce9131a`（PR82 head）。原始 55 failed / 24 errors 的节点级收据未留存，本卡以三态记录其可得部分。

## 原始收据的三态判定

指针来源：固定对象 `fce9131a:docs/sessions/261003-http-completion/progress/windows-http-integrity-fix-progress.md`（59 行）。该文档是本卡唯一读到的原始记录。

| 项 | 状态 | 证据 |
| --- | --- | --- |
| 计数 | **known** | `55 failed, 421 passed, 3 skipped, 70 warnings, 24 errors in 262.02s`，rc=1 |
| 首异常 | **known** | `EOFError`，stdlib `multiprocessing/connection.py:399` `_recv` |
| 异常族计数 | **known** | `EOFError` 45 条 + setup `EOFError` 24 条 |
| 失败节点 ID 全集 | **unknown** | 原文只给文件级聚合，未留 nodeid 清单 |
| JUnit XML 原件 | **unknown** | 原文只写 `--junitxml=…`，路径为省略号，仓库内无该产物 |
| 原日志原件 | **unknown** | 称「原字节保留」，但保留位置未记，本卡不可得 |

因此**「原失败节点」不可复原**。本卡定向运行的节点一律标记为「新候选，非历史原节点」，不回填为原失败 case。

原收据运行于 `946bc998`；本卡实测 `git diff --name-only 946bc998 fce9131a` 仅返回两个 docs 路径，非文档源零差异，故该次红与 `fce9131a` 同源。

## 远端与 PR 身份（本卡实测，非文档自述）

| 对象 | 实测值 | 取证方式 |
| --- | --- | --- |
| `origin/master` | `e849c21748392ad848131e07ff17d32e4cc83a8b` | `git ls-remote`，stdout 非空 |
| PR82 head | `fce9131a256a7a8e26a48a0c0882b81444f9ee59` | `gh pr view 82` |
| PR82 状态 | OPEN / **Draft** / MERGEABLE | 同上 |
| 祖先关系 | `e849` **不是** `fce` 的祖先，merge-base `6aa76f6c` | `git merge-base --is-ancestor` rc=1 |

## 本卡新取得的因果输入：CI 在同一 head 上是绿的

卡面转述的 job `111751291971` 经只读 API 核实，**归属 `fce9131a` 本 head**，且各步骤均为 `success`，不是 draft skip：

| 字段 | 实测值 |
| --- | --- |
| run / job | `37306483615` / `111751291971`，`pull_request`，`run_attempt=1` |
| job 名 | 单元测试 (py3.12 / websockets) |
| 入口 | `python -m pytest tests/ -q`（与本地红同一入口） |
| **结果** | **`500 passed, 3 skipped, 163 warnings in 256.89s`** |
| 关键步骤 | 「运行 pytest」conclusion=`success`（非 skipped） |

`500 + 3 = 503`，与本卡在 `fce9131a` 上 collect-only 得到的 **503 节点完全相等**，交叉印证本卡 collection 环境与 CI 节点总体一致。

### 绿/红之间当前唯一已知的依赖版本差

| 维度 | CI（绿） | 本地原红 | 差 |
| --- | --- | --- | --- |
| CPython | 3.12.14 | 3.12.3 | 补丁版本不同 |
| **websockets** | **17.2**（矩阵未钉） | **15.0.1**（钉死） | **主版本不同** |
| 其余依赖 | aiohttp 3.14.3 / httpx 0.28.1 / pytest≥9.1.1 / pytest-asyncio 1.4.0 | 同 | 一致 |
| 入口 | `pytest tests/ -q` | `pytest tests/ -q -rs -p no:cacheprovider` | 仅附加输出参数 |

原收据明确记录「套件 2（`--with websockets` 不钉）因 fail-stop **未跑**」。即本机从未跑过 unpinned websockets 的全量，而 CI 跑的正是那一维。**这是本卡新增的最强线索，不是结论。**

该线索被三项混淆项污染，暂不可归因：CPython 补丁版本、runner OS/ffmpeg 差异、以及本地当时的机器负载。卡面已否决「当前负载推历史原因」，故此处只登记差异，不宣称因果。

## 本卡受控对照环境（已冻结）

私有 venv，不污染主仓 `.venv`／全局环境。`sys.executable` 为该私有 venv 的 `python`，版本 3.12.3。

| 包 | 版本 | 包 | 版本 |
| --- | --- | --- | --- |
| pytest | 9.1.1 | aiohttp | 3.14.3 |
| pytest-asyncio | 1.4.0 | httpx | 0.28.1 |
| websockets | 15.0.1 | numpy | 2.5.3 |
| rich | 15.0.0 | colorama | 0.4.6 |
| soundfile | 0.14.0 | ffmpeg | 6.1.1-3ubuntu5 |

numpy/rich/colorama/soundfile 在原收据中未钉版本，其历史实际值不可得；上表为本卡新建受控对照值，**不冒充历史重现**。

## 两端 collection 对照（各跑一次，rc 均为 0）

两端用同一冻结解释器、同一依赖闭包、独立 TMPDIR，入口 `python -m pytest tests/ --collect-only -q`。

| 端 | SHA | 收集节点数 | rc |
| --- | --- | ---: | --- |
| 基线 master | `e849c217` | 515 | 0 |
| PR82 head | `fce9131a` | 503 | 0 |

**计数与集合差异必须分开看**，本卡按节点多重集比对：**仅基线有 18 个、仅 head 有 6 个、交集非全等**。

- 仅 `e849`：`test_http_qa_repeat_matrix.py` 12 个、`test_ws_progress_watchdog.py` 5 个、`test_protocol_v2.py::test_compressed_backpressure_does_not_extend_any_deadline` 1 个。
- 仅 `fce`：`test_backpressure.py` 3 个、`test_error_contract.py::test_segment_watchdog_errors_and_exits_main_nonzero`、`test_http_file_tasks.py::test_http_binary_payload_survives_append_recovery_and_commit_replay`、`test_protocol_v2.py::test_compressed_consumer_backpressure_pauses_upload_idle`。
- `tests/test_http_cleanup.py` 的 19 个节点在两端**逐条相同**，4 个 `naked-shell` 参数化节点两端均在。

该比对判据已用 canary 自检：向基线多重集注入一个已知不存在的节点后，判据正确报 `equal=False`，非恒真。

`fce` 的 503 与 CI 的 `500 passed + 3 skipped` 相等；`e849` 的 515 说明主干含 PR82 已删除的两个文件，**两端不是单变量的 O_BINARY 父子关系**，不可把差异整体归给 PR82。

## ≤4 次定向节点对照

入口 `python -m pytest <node> -q -rs -p no:cacheprovider`，单次外层 180s，独立 TMPDIR，各自进程组。

| # | 节点 | `e849` | `fce` |
| --- | --- | --- | --- |
| A | `test_http_cleanup.py::test_fatal_cleanup_exits_process_and_reaps_children[naked-shell]` | 1 passed (0.94s) | 1 passed (0.67s) |
| B | `test_http_supervision.py::test_result_producer_payload_and_done_survive_new_process` | 1 passed (0.82s) | 1 passed (0.77s) |

四次全绿且**均为真实 passed 而非 skip**（输出为 `1 passed`，非 `s`）。

三点必须随绿一起记录，否则会读成假结论：

1. **A、B 都是「新候选，非历史原节点」**。原 nodeid 集合不可复原，无法证明它们属于原 55 failed。
2. **隔离绿 ≠ 全量绿**。原收据自己就记过 `test_options_missing_and_none_default_but_falsy_wrong_types_are_rejected` 在全量中 409≠400、隔离复跑却 passed。EOFError 族本就只在全量出现。
3. **naked-shell 不是 `env -i`**。读消费方代码确认：`tests/test_http_cleanup.py:948` 为 `env = dict(os.environ)` 再 `env.update(self.env)`，即整体继承父环境；而同文件 `_probe_env`（872 行）的 docstring 自称「只白名单传…不整体继承测试环境」，**docstring 与实现相反**。真正接近干净消费环境的是 `systemd-unit` 分支（逐键 `--setenv`）。该继承行为两端逐字节相同，故不构成本卡两端的差异变量，但本卡覆盖的是 naked 分支，**不构成 env 对照**。

## child 因果信号：不可得

节点 A、B 本次为绿，无 EOF 可追，故 child 首次异常仍 **unknown**。检查夹具能力后确认结构性缺口：

`ProbeRun`（`tests/test_http_cleanup.py:898`）只暴露**启动器自身**的 `self._process.returncode` 与 `.pid`（982、994、999 行），**不暴露识别子进程 / `multiprocessing.Manager` 子进程的 PID、退出码或独立 stderr**。原收据中「探针以『再见！』rc=1 退出」正是启动器层症状；其后的 child 首异常在现有夹具下原理上取不到。

按卡面要求，本卡不越界改测试源码，改为交出精确探针位置：需在 `ProbeRun.start()` 成功之后、`run_managed_fake_server()` 真实 `ProcessManager.start()` 返回处，写出 launcher/recognizer/manager 三方 PID、父子关系与各自退出码，并令 `wait_report` 失败分支（978–986 行）把该三元组并入异常消息，使启动器 rc=1 时能定位到首个死掉的 child。

## 未决

原 55/24 的节点级根因仍 **unknown**。本卡不声称 PR82 就绪、不声称 M7 完成、不标 ready、不合并。
