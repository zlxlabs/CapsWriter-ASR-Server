# PR82 有界验证进度

## 当前阶段

verifying（本卡只诊断，不改运行源码）。

## 本段结论

- 原始 55 failed / 24 errors 的**节点级收据不存在**：原文档只留计数与首异常类型，JUnit 路径写作省略号 `--junitxml=…`，仓库内无产物。故按三态记 `unknown`，不回填「原失败 case」。
- 原收据跑在 `946bc998`；本卡实测 `946bc998→fce9131a` 仅两个 docs 路径不同，非文档源零差异，两次运行同源成立。
- `e849` 不是 `fce` 的祖先（merge-base `6aa76f6c`），两端确为分叉对照。
- 卡面转述的 CI job `111751291971` 核实归属 `fce9131a` **本 head**，且「运行 pytest」步骤 conclusion=`success`，**不是** draft skip 造成的假绿；结果 `500 passed, 3 skipped in 256.89s`。
- 该 503 与本卡 collect-only 在 `fce` 上的 503 节点完全相等，交叉印证本卡 collection 环境可信。
- 绿/红之间唯一已知的依赖版本差是 **websockets 17.2（CI，未钉） vs 15.0.1（本地，钉死）**；原收据的「套件 2 未钉 websockets」因 fail-stop 从未在本机跑过。

## 关键决策与已否决方案

- **只登记 websockets 版本差为线索，不归因**。该项与 CPython 补丁版本（3.12.14 vs 3.12.3）、runner OS/ffmpeg、本地历史负载三重混淆，卡面已否决「当前负载推历史原因」，越权归因会造出假结论。
- **不因 CI 绿就宣布本地红已解决**，也不因两端定向绿就宣称历史原因消失。CI 绿只证明「该 head 在 CI 消费环境下通过」，不解释本机历史红。
- 定向节点一律标注「新候选，非历史原节点」，因原 nodeid 集合不可复原。
- 已否决（承卡面）：blind full/grid、延长 timeout/sleep、重试刷绿、以当前负载推历史原因、以计数相等推节点集合相同、伪造原失败 node、半段 env 或错 phase 关联当因果、绕闸、跨仓改工具、生产操作。

## 本段结论（续）

- 两端 collect-only 均 rc=0，但节点多重集**不相等**：`e849` 515 / `fce` 503，仅基线有 18 个、仅 head 有 6 个。`test_http_cleanup.py` 19 个节点两端逐条相同。比对判据经 canary 自检非恒真。
- 4 次定向运行（A：naked-shell cleanup 节点；B：跨进程 result producer 节点）全绿，且为真实 passed 非 skip。A、B 均为**新候选，非历史原节点**。
- child 首异常仍 **unknown**：节点绿故无 EOF 可追；且 `ProbeRun` 只暴露启动器 PID/returncode，原理上取不到识别子进程与 Manager 子进程的退出信息。已交出精确探针位置（`tests/test_http_cleanup.py:898` `ProbeRun.start()` 与 `wait_report` 978–986 行），本卡不改测试源码。
- 顺带发现实现与自述矛盾：`tests/test_http_cleanup.py:872` `_probe_env` docstring 称「不整体继承测试环境」，但 948 行实为 `dict(os.environ)` 全量继承。两端相同，非本卡差异变量，但使 naked-shell 不能充当 `env -i` 对照。

## 下一步唯一动作（已被下一节更正，保留原文）

在**同一冻结 venv、同一台机、同一入口**下，只变一个变量跑两次全量：websockets 钉 `15.0.1` 与不钉（实际 17.2），各留 nodeid 级 JUnit。这是当前唯一能把「本机 55/24」与「CI 绿」之间的混淆变量收敛掉的动作，且原收据明确缺这一维。归属下一张修复卡，本卡不实施。

若该单变量对照不能复现红，则 websockets 版本被排除，下一步才轮到 child 探针（位置已交）。两者不可并行猜。

## 纠正轮（Task16，dlg-20261006-033209-b7e45c）

只追加，不抹上文历史。

### 被推翻的上一轮结论

1. **「原始收据不可复原」错误。** 上一轮据仓内文档里的省略号 `--junitxml=…` 判定原件不存在，这是过度推断。本轮按 PR82 body → 两个 dispatch → delegate 状态目录 → 源根 `.tmp-combo/` 的精确指针链定位成功，`ws15.junit.xml` 与 `std-ws15.json` 均在位，**79 条具名失败/错误已复原**。教训：文档里没写路径 ≠ 没留存。
2. **「503 对 503 证 CI 节点集合/collection 环境一致」撤回。** 数字相等不构成节点集合相同的证据。
3. **「websockets 是唯一已知差异」撤回。** CPython 补丁版本（3.12.14 vs 3.12.3）同样不同，共两处。
4. **「推翻卡面 CI 红的假前提」撤回。** 卡面从未称 CI 为 55/24 红，历史 55/24 一直明写 Linux 本机红；去核该 job 是为取依赖版本，不是为反驳卡面。
5. **两端 collection 差异改用 base/merge-base 陈述**，不得表述为「PR82 删除了主干 18 节点」。`fce` 的 base 是 `6aa76f6c`，`e849` 在其之后。
6. **节点 A 更正为真实原失败节点**（原 4 条 naked-shell 之一），上一轮标「新候选」属过度保守。

### 本轮新增真实证据

- 原红构成：`EOFError` 45 + setup `EOFError` 24 + `AssertionError` 9 + `FileNotFoundError` 1，`tests=503 failures=55 errors=24 skipped=3`，与留存 summary 一致。
- 原红入口与依赖已实读：入口 `python -m pytest tests/ -q -rs -p no:cacheprovider`，CPython 3.12.3、websockets 15.0.1、pytest 9.1.1、pytest-asyncio 1.4.0、aiohttp 3.14.3、httpx 0.28.1、numpy 2.5.3、soundfile 0.14.0。
- **新授权的 `env -i` 真实父命令对照（fce 端、同一冻结 venv、单次）**：白名单 8 键，`env -i` 确已生效；节点 A `1 passed in 0.74s`，rc=0。**child 实际环境仍 unknown**（夹具不导出 environ 副本），只记录 parent producer argv/env，不伪造 child 实观。
- CI 侧依赖从日志 `Successfully installed` 行实读，可逐项比对；已知差异为 CPython 与 websockets 两处。

### 下一步唯一动作（更正）

**不采用**「跑两次全量做 websockets 单变量对照」——该动作不自授，且两次全量全绿也不能排除 websockets 对历史红的影响。

改为按**真实收据缺口**给候选：原 79 条中 69 条是 EOF 族，而 child 首异常在现有夹具下原理上取不到。下一卡应先落**child 可观测探针**（位置已交：`tests/test_http_cleanup.py:898` `ProbeRun.start()` 与 `wait_report` 978–986 行），拿到 launcher/recognizer/manager 三元组后，才能把 EOF 归到具体 child；websockets 与 CPython 两处差异作为并行候选保留，不宣称排除。

完整全量本地漏斗仍保留在正常交付卡，本卡不自授豁免。
