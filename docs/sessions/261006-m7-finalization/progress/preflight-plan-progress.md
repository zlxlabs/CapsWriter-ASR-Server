# M7 前置核实计划进度

## 2026-10-06 阶段一：只读核实与计划（dlg-20261006-024303-c1bd68）

- **当前阶段**：planning。M7 **未完成**，本卡只产出可派卡的计划。
- **本段结论**：
  - PR #82 的 `55 failed / 24 errors / 421 passed / 3 skipped` 是 **Linux 本机 uv 运行**的结果，
    不是 Windows 失败；Windows 原生证据归属源修 `9e0dd6db` 端点，PR 自己声明「不是本 head 新跑」。
  - 同一 head `fce9131a` 在 hosted CI py3.12 job `111751291971` 为 `500 passed, 3 skipped` 绿；
    master `e849c21` 的 py3.12 job（run `37403660636`）为 `512 passed, 3 skipped` 绿。采集**计数**
    503 对 503；这只证明计数相等，用例集合是否相同见阶段二纠正 1。
  - 失败分布已知：`test_http_cleanup` 15 passed / 4 failed（全在 `naked-shell`）、`test_http_store`
    16 passed、Windows 二进制用例 **passed**（仅证明该用例通过）；其余以 `EOFError`（45）+ setup
    `EOFError`（24）为主，首个异常落在 stdlib `multiprocessing/connection.py:399` 的 `_recv`。
  - `git merge-tree --write-tree e849c21 fce9131a` → `634c7d7`，**0 冲突**；合并树非文档差异仅
    `core/server/http_store.py` +8 −2 与 `tests/test_http_file_tasks.py` +71，两处
    `getattr(os, "O_BINARY", 0)` 与新增 Windows 测试均保留。
  - macOS 隔离环境/样本：本卡**读取范围未定位到**，记 unknown（不等于不存在）。
- **关键决策**：
  - 55/24 的根因 **unknown**，不发明根因；PR #82 的 `O_BINARY` 局部已审不等于全套件绿。
  - 最小新因果输入：定向验证（覆盖面见阶段二纠正 4）+ 环境/版本/源码对照。
  - 依赖顺序定为 `C1 → A → {B, C, D}`（三平台可并行）；`E` 静态准备可并行、运行验收依赖被测
    runtime SHA。
  - 三平台必须测同一个 `MERGED_SHA`；旧 492 / Windows 21/25 / POSIX 21/25 / Linux 首测
    （服务 SHA `820c3a2`、工具 SHA `d4eab57`）一律不作为新源码资格。
- **已否决方案**：盲 full/grid 矩阵、延长 timeout/sleep、重试直到绿、旧平台参考数冒充新源码资格、
  fake 模型/stub 结果当 ASR 质量、跨仓改 gate 或平台工具、生产服务改动或凭据调查。
- **质量门槛**：M7 的「真实 ASR 质量」验收形式**pending，由主脑向用户提问**（本卡不代问、不代决，
  候选见 design.md §6）。CPU/RSS 不在待裁决项：原 M7 已要求资源证据，沿用工具外监控。
## 2026-10-06 阶段二：纠正推理错误（dlg-20261006-025815-70f6c7）

只改原两个文件，未跑测试/服务，未改运行代码，未扩调查。

- **纠正 1（503 对503）**：计数相等**只**证明计数相等。无同次JUnit / node multiset 对照，
  用例集合是否相同改记 **unknown**，删「同一份用例集合」与「排除用例差异」。
- **纠正 2（O_BINARY）**：具名用例 passed 只证明该用例通过，**不**证明改动未在别处导致 55/24
  失败；删「不是O_BINARY 修复引入」与「红只测环境不是改动有问题」。Linux 平台保留文档来源，
  根因仍 **unknown**。
- **纠正 3（ps/负载）**：ps/负载/systemd 是**本卡执行当时观测**，两次红在 2026-10-05，相隔约
  一天，不作因果输入；一次安静转绿**不能**证明负载相关；改为要求环境/版本/源码对照待验证。
- **纠正 4（最小验证覆盖面）**：原方案只跑 cleanup 4 条，会漏掉 45+24 的EOF 簇。改为至少覆盖
  cleanup 与真实 EOF 失败族**各一个原具名 case**（EOF case 从原 JUnit 取，不猜），同入口、
  base/head 环境与 child 退出签名。**全量本地漏斗仍是正常交付要求**，不豁免、不自授豁免、
  不把未知红当噪音。
- **纠正 5（macOS 与共享脚本）**：仓内查不到 ≠ 不存在，改记「本次读取范围未定位到」；六个共享
  未跟踪脚本归属本卡未核实，删「属主脑所有」。
- **纠正 6（CPU/RSS 与格式覆盖）**：CPU/RSS 原 M7 已要求资源证据，**默认沿用工具外监控**，
  删该用户裁决点、不扩工具。WAV/MP4 四次只是已知部分，补列 MP3/AAC/M4A/Opus 覆盖，缺样本
  记缺口、不缩完成条件。
- **纠正 7（AST 框架与 E 的依赖）**：AST 哈希框架**不需要**，改用 git 精确 blob（`git rev-parse
  <SHA>:<path>`）。卡 E 改为「静态准备可并行，**运行验收必须依赖它实际测试的 runtime SHA**」。
- **纠正 8（自相矛盾）**：API 预算「6 次」与实际列项矛盾，统一为 11 次；依赖图 `C1→A→B→D` 与
  B/C/D 三平台小节矛盾，统一为 `C1 → A → {B, C, D}`；质量门槛改为 **pending，由主脑问用户**。
- **下一步唯一动作**：把纠正后的两个文件交回主脑消费；质量门槛由主脑向用户提问。