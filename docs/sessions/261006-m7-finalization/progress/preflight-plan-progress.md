# M7 前置核实计划进度

## 2026-10-06 阶段一：只读核实与计划（dlg-20261006-024303-c1bd68）

- **当前阶段**：planning。M7 **未完成**，本卡只产出可派卡的计划。
- **本段结论**：
  - PR #82 的 `55 failed / 24 errors / 421 passed / 3 skipped` 是 **Linux 本机 uv 运行**的结果，
    不是 Windows 失败；Windows 原生证据归属源修 `9e0dd6db` 端点，PR 自己声明「不是本 head 新跑」。
  - 同一 head `fce9131a` 在 hosted CI py3.12 job `111751291971` 为 `500 passed, 3 skipped` 绿；
    master `e849c21` 的 py3.12 job（run `37403660636`）为 `512 passed, 3 skipped` 绿。采集总数
    503 对 503，是同一份用例集合的两种环境两个结果。
  - 失败分布已知：`test_http_cleanup` 15 passed / 4 failed（全在 `naked-shell`）、`test_http_store`
    16 passed、Windows 二进制用例 **passed**；其余以 `EOFError`（45）+ setup `EOFError`（24）
    为主，首个异常落在 stdlib `multiprocessing/connection.py:399` 的 `_recv`。
  - `git merge-tree --write-tree e849c21 fce9131a` → `634c7d7`，**0 冲突**；合并树非文档差异仅
    `core/server/http_store.py` +8 −2 与 `tests/test_http_file_tasks.py` +71，两处
    `getattr(os, "O_BINARY", 0)` 与新增 Windows 测试均保留。
  - macOS 隔离环境/样本在仓内**无任何收据**，记 unknown。
- **关键决策**：
  - 把 55/24 定性为「运行环境差异，待最小验证」，不发明根因；PR #82 的 `O_BINARY` 局部已审
    不等于全套件绿。
  - 替代 full 重跑的最小新因果输入：只定向跑 `tests/test_http_cleanup.py` 的 `naked-shell` 参数集，
    并同时记录本机负载水位——此前两次全量汇总都没有「这 4 个在安静环境下是否仍红」这一维。
  - 依赖顺序定为 `C1（解除阻塞并正式合并，产出共同 SHA）→ A（冻结共同 runtime）→ B/C/D（三平台
    隔离真实基线）`，`E（部署说明与入口核对）` 可并行。
  - 三平台必须测同一个 `MERGED_SHA`；旧 492 / Windows 21/25 / POSIX 21/25 / Linux 首测
    （服务 SHA `820c3a2`、工具 SHA `d4eab57`）一律不作为新源码资格。
- **已否决方案**：盲 full/grid 矩阵、延长 timeout/sleep、重试直到绿、旧平台参考数冒充新源码资格、
  fake 模型/stub 结果当 ASR 质量、跨仓改 gate 或平台工具、生产服务改动或凭据调查。
- **待用户裁决（唯一阻塞性的一点）**：M7 的「真实 ASR 质量」以记录制（只交三平台同源数字表，
  不设阈值）还是阈值制验收？原设计与 `docs/guides/http-baseline.md` 均未设阈值，本卡不自行放宽。
  次要待裁决（非阻塞）：CPU/RSS 是否收进基线工具，还是沿用工具外一次性监控。
- **下一步唯一动作**：把 `design.md` 交回 Pi 主脑，由主脑裁决质量门槛形式并决定是否派卡 C1
  （解除 PR #82 阻塞并正式合并）。