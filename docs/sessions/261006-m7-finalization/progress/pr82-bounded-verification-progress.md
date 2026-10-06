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

## 下一步唯一动作

在**同一冻结 venv、同一台机、同一入口**下，只变一个变量跑两次全量：websockets 钉 `15.0.1` 与不钉（实际 17.2），各留 nodeid 级 JUnit。这是当前唯一能把「本机 55/24」与「CI 绿」之间的混淆变量收敛掉的动作，且原收据明确缺这一维。归属下一张修复卡，本卡不实施。

若该单变量对照不能复现红，则 websockets 版本被排除，下一步才轮到 child 探针（位置已交）。两者不可并行猜。
