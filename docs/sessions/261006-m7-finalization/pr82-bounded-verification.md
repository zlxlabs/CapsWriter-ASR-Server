# PR82 原始失败收据与同环境有界验证

## 范围

只验证，不修复。生产/tests 源码 0 行改动。两端 Git 身份固定为 `e849c217`（远端 master）与 `fce9131a`（PR82 head）。

## 更正声明（对本文档上一版）

上一版存在四处越界推断，本版删除并更正：

1. 删去「推翻卡面 CI 红的前提」一类表述。**卡面从未称 CI 为 55/24 红**，历史 55/24 一直明写为 Linux 本机红。本卡去核实该 job 是为了取得依赖版本，不是因为它与卡面冲突。
2. 删去「`503` 对 `503` 证明本卡 collection 环境与 CI 节点集合一致」。两个数字相等不构成节点集合相同的证据。
3. 删去「websockets 是唯一已知差异」。CPython 补丁版本同样不同，为两处差异。
4. 两端 collection 差异改用 **base / merge-base** 陈述。`fce` 自旧 base `6aa76f6c` 分叉，**不是**「PR82 删除了主干的 18 个节点」。

## 原始收据：本轮已定位并复原（node 级）

上一版据「仓内文档省略号」判定原件不可复原，属过度推断。本轮按精确指针定位成功。

指针链：PR82 body → dispatch `dlg-20261005-114620-eb018f`（resume `dlg-20261005-093848-fe9697`）→ delegate 状态目录 `20261005-114637-resume-cursor-…-eb018f`（其 `envelope.json.repo_path` 给出源根）→ 源根 `.tmp-combo/`。

原件 `ws15.junit.xml` 与 `std-ws15.json` 均在位。安全解析结果（只取节点 ID / 异常类 / 计数，不回显 XML 与日志正文）：

| 项 | 值 |
| --- | --- |
| 套件 | `tests=503 failures=55 errors=24 skipped=3` |
| 具名 failure+error | **79** 条 |
| 异常构成 | `EOFError` 45 + setup `EOFError` 24 + `AssertionError` 9 + `FileNotFoundError` 1 |

按模块分布（failure/error）：`test_http_file_runner` 23F、`test_protocol_v2` 8E、`test_server_e2e_baseline` 6E、`test_http_qa_e2e` 6F、`test_error_contract` 6E+3F、`test_backpressure` 5F、`test_http_cleanup` 4F、`test_health` 3F、`test_file_result_contract_e2e` 3E、`test_port_restart` 2F、`test_owner_ipc` 2F。

原红确实只发生在 Linux 本机，入口 `python -m pytest tests/ -q -rs -p no:cacheprovider`，websockets 钉 `15.0.1`，rc=1。

## 两端 Git 身份与分叉关系

| 对象 | 值 | 取证 |
| --- | --- | --- |
| `origin/master` | `e849c21748392ad848131e07ff17d32e4cc83a8b` | `git ls-remote`，stdout 非空 |
| PR82 head | `fce9131a256a7a8e26a48a0c0882b81444f9ee59` | `gh pr view 82` |
| PR82 状态 | OPEN / **Draft** / MERGEABLE | 同上 |
| merge-base | `6aa76f6c6935e9cef00afc1bcbcf8327e7c95488` | `git merge-base` |

`fce` 的 base 是 `6aa76f6c`，`e849` 在该 base 之后。因此两端 collection 差异反映的是**两个不同基点各自的测试面**，其中 PR82 侧删除了 `test_http_qa_repeat_matrix.py` 与 `test_ws_progress_watchdog.py`，但不能表述为「PR82 删除了主干节点」。

## collection 对照（同一冻结解释器/依赖，独立 TMPDIR，rc 均 0）

| 端 | 收集节点数 | rc |
| --- | ---: | --- |
| `e849c217`（master） | 515 | 0 |
| `fce9131a`（PR82 head） | 503 | 0 |

节点多重集比对：**仅 `e849` 侧 18 个、仅 `fce` 侧 6 个、交集非全等**。`tests/test_http_cleanup.py` 的 19 个节点在两端**逐条相同**。判据经 canary 自检（注入已知不存在节点后正确报 `equal=False`），非恒真。

## 定向对照（更正：其中一条是真实原失败节点）

上一版把 A、B 一律标为「新候选非历史原节点」，属过度保守——本轮复原收据后可确认：

| # | 节点 | 是否原失败节点 | `e849` | `fce` |
| --- | --- | --- | --- | --- |
| A | `test_http_cleanup.py::test_fatal_cleanup_exits_process_and_reaps_children[naked-shell]` | **是**（原 4 条 naked-shell 之一） | passed 0.94s | passed 0.67s |
| B | `test_http_supervision.py::test_result_producer_payload_and_done_survive_new_process` | 否（`test_http_supervision` 不在失败清单） | passed 0.82s | passed 0.77s |

原收据中 A 的失败消息为 `探针在产出 pre_fatal 报告前就退出了，exitcode=1：再见！`。本次 A 在两端均通过。

**这不能证明历史原因已消除**：原始 79 条中的另外 3 条 naked-shell 节点与 70 余条 EOF/Assertion 条目未被本卡复跑；且原收据自己记过有节点在全量中失败、隔离复跑却通过（隔离 ≠ 全量）。

## 真实 `env -i` 父命令对照（新授权，单次）

按卡面要求，在 `fce` 端、同一冻结 venv、**真实 `env -i` 父命令**下运行既有候选节点 A 一次（180s 外层，不双端、不重试、独立 TMPDIR）。

- 白名单：`PATH` / `HOME` / `TMPDIR` / `PWD` / `LANG=C.UTF-8` / `LC_ALL=C.UTF-8` + 两个驱动键。
- **producer 实观环境键数 = 8**，即 `env -i` 确已生效、未继承父环境（非恒真判据：继承态远不止 8 键）。
- 结果：`1 passed in 0.74s`，pytest rc=0，外层 rc=0。
- **child（探针）实际环境：unknown**。现有夹具无法实观——`ProbeRun` 只取启动器 `returncode`/`.pid`；`tests/fixtures/http_fatal_exit_probe.py` 只 `os.environ.get` 若干 `CW_*` 键，不导出 `environ` 副本。故只记录 parent producer 的 argv/env 证据，不伪造 child 实观。

注：源码 `dict(os.environ)` 并不妨碍从 `env -i` 父命令启动——本轮已实测该路径，producer 侧环境确为 8 键白名单。

## 版本与环境对照（CI 绿 vs 本地原红）

从 CI job 日志的 `Successfully installed` 行与原 `std-ws15.json` 的 `versions` 字段实读：

| 维度 | CI | 本地原红 | 是否相同 |
| --- | --- | --- | --- |
| CPython | 3.12.14 | 3.12.3 | **不同** |
| websockets | 17.2 | 15.0.1 | **不同** |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 | 9.1.1 / 1.4.0 | 相同 |
| aiohttp / httpx | 3.14.3 / 0.28.1 | 3.14.3 / 0.28.1 | 相同 |
| numpy / soundfile | 2.5.3 / 0.14.0 | 2.5.3 / 0.14.0 | 相同 |
| rich / colorama | 15.0.0 / 0.4.6 | 未记录 | CI 侧已知，本地侧 unknown |

入口同为 `python -m pytest tests/`，CI 结果 `500 passed, 3 skipped`，本地结果 `55 failed / 24 errors`。

**已知差异为两处（CPython 补丁版本 + websockets 主版本），不是一处。** 本卡未对任一维度做过单变量对照，故不宣称任一维度是原因；两端定向全绿也不能排除 websockets 对历史红的影响。

## child 首异常：仍 unknown，且现有夹具原理上取不到

原收据 79 条中 69 条是 `EOFError`（45 失败 + 24 setup），症状是父进程读队列时 `multiprocessing/connection.py:399 _recv` 抛错。首次异常的 child 身份未在任何留存产物中记录。

夹具缺口（结构性）：`ProbeRun`（`tests/test_http_cleanup.py:898`）只暴露**启动器自身** `returncode`/`.pid`（982/994/999 行），不暴露识别子进程与 `multiprocessing.Manager` 子进程的 PID、退出码或独立 stderr。原收据「exitcode=1：再见！」正是启动器层症状。

**建议给下一卡的探针位置（本卡不改源码）**：在 `ProbeRun.start()` 成功之后、`run_managed_fake_server()` 真实 `ProcessManager.start()` 返回处，写出 launcher / recognizer / manager 三方 PID、父子关系与各自退出码，并令 `wait_report` 失败分支（978–986 行）把该三元组并入异常消息，使启动器 rc=1 时能定位首个死掉的 child。

## 未决

原 79 条失败中 EOF 族的 child 首异常根因仍 **unknown**。本卡不声称 PR82 就绪、不声称 M7 完成、不标 ready、不合并。正式 Ready、完整门禁与全量本地漏斗仍留下一张交付卡。
