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

## 未决

原 55/24 的节点级根因仍 **unknown**。本卡不声称 PR82 就绪、不声称 M7 完成、不标 ready、不合并。
