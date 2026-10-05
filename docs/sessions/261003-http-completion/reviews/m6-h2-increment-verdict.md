<!-- delegate-outcome: succeeded -->

# H1..H2 schema 边界消歧四问增量审

- 风险等级：internal。
- 冻结对象：`337689689c9b2a314548b70667e447841bf070ad..77940745146d377d780e1f840bfbfd633740c114`
- 审查结论：H2 将消费者承诺收窄为 schema 结构校验，且未改真实 producer；发现 1 项 P2 测试判据缺口，无 P1。
- 基线：派发记录为 timeout；本次未跑全量套件，不能分类全量继承红或新红。
- OCR：一次前置扫描返回 `status=skipped`、0 findings；覆盖未知，不作为干净结论。

failure-visibility: p2-only

## 1. 是否只消歧承诺且未弱化真实控制

- 主旨符合：`m6-repeat-matrix-design.md` 明示结构通过不认证执行次数；真实五轮仍由 producer 循环和 Hosted／裸环境证明，不接受假 JSON 代替真实运行。新增的全重标克隆用例只验证消费者接受结构自洽 JSON，测试名与说明都指出它不是执行证明。
- H0 的“未改 harness”被明确限定为 H0 当时事实；文档另记 H1 获准新增最小 WS listener，时间关系清楚，没有倒写历史。
- H0 的 `REPEAT_COUNT = 5`、五轮循环、同一持久目录、真实取消/mailbox、重启后完整结果相等、重启后实例上的旧 WS、源字节及 PCM oracle、ffmpeg 每轮证据均未改。M6 QA 仍要求 Hosted 与无会话裸 shell 实证、12 组验收与真实 skip 原因；本轮没有宣称新跑这些环境或 Goal 达成。
- 依据：`goals/http-integration/M6-qa.md:15-22`；`docs/sessions/261003-http-completion/m6-repeat-matrix-design.md:40,44-53`；`docs/sessions/261003-http-completion/progress/m6-repeat-matrix-progress.md:9-19,53-69`；原 QA 的跨进程 producer 字节与旧 WS 条款在 `docs/sessions/261001-http-files/qa.md:3,55-57`，公开 WS 契约见 `docs/reference/protocol.md:1-9`。

## 2. 是否新增机制或把 anti-forgery 问题换名

- 没有新增 nonce、签名、账本、状态、配置、fallback 或第二套消费者。新用例只复制 `_complete_round(1)` 的测试 fixture、重写 round/ID/offset，再调用现有文件消费者；通过只说明 schema 边界，不构成真实 producer 证据。
- 完整 JSON 可任意重写且不能自认证的未知被如实披露；按本卡边界不扩大为认证机制或 P1。

## 3. 状态、事实、fallback 与 AST

- 对冻结 Git blob 做前后 AST 比较：40 个原有函数在仅归一化消费者与被改测试的 docstring、两处指定 `AssertionError` 文案和 offset 测试的对应 `match` 文案后完全一致；模块 import/常量 AST 也完全一致。唯一新增函数是 `test_trace_consumer_accepts_fully_relabeled_clone_is_not_execution_proof`。
- `_phase*`、PCM/source helpers、WS helper、`_dump_trace`、`_tasks`、`_wait_until` 与五轮主入口的源码片段逐字节相同。字典键、数字、布尔值、调用、条件和既有返回值没有变化；无状态或 fallback 新增。
- 文案变化为：消费者说明、round ID 错误消息、offset 错误消息、offset 测试 matcher、旧重标测试说明；新增的唯一行为用例即上节所述。

## 4. 双消费者、断言和发现

- pytest 主入口与 CI importlib 仍加载同一 `consume_repeat_matrix_trace`，并从 `M6_REPEAT_MATRIX_ARTIFACT_DIR/trace.json` 读同一路径；入口先写实际文件再消费。CI 调用见 `.github/workflows/ci.yml:52-77`，函数与 producer 调用见 `tests/test_http_qa_repeat_matrix.py:65,1123`。
- 标准 uv 无项目 Python 3.12 的 focused consumer 运行：`10 passed, 2 deselected`。其中包括 missing-file 的真实 `read_bytes()` 负例、重用 offset 拒绝、mailbox 与 WS 约束、结果 payload 不等拒绝，以及新全重标克隆接受用例。
- **P2：简单 round 重标负例未单独锁住“ID 必须含本轮号”。** `test_trace_consumer_rejects_relabeled_round_without_unique_job` 把完全相同的 `_complete_round(1)` 复制五份，ID 因而重复；重复 ID 校验本身就能让用例红，无法证明 round 字段匹配检查有牙齿。已做已知坏控制：只删除 `round_job_id` 中 `f"r{round_id}"` 匹配条件，保留其余校验，再跑该单测，结果仍为 `1 passed`，不是导入或文件缺失失败。该用例应使用彼此唯一、但对目标轮仍缺少对应 `r{n}` 的 ID，使删除此条件时测试变红。依据：本卡要求仍拒绝“只重标 round、ID 不含本轮”；现有断言位置为 `tests/test_http_qa_repeat_matrix.py:360-371`，消费者条件为 `:133-140`。
- 这项 P2 指向 schema 回归测试的判别力；真实 producer 代码与五轮循环未变，不代表全重标 JSON 能认证执行次数，也不构成应用 P1。

## 验证与限制

- AST 对比结果：40 个既有函数归一化后相同；指定 producer/source/PCM/loop 源码完全相同；模块 import 与常量相同；新增函数仅 1 个。
- focused consumer 测试：10 passed、2 deselected；round ID 删除条件的坏控制：目标测试仍 1 passed，确认上述 P2。
- 未运行 500 条全量套件、真实五轮盲重复、Hosted/no-session 环境套件或真实 ASR；这些运行证据与 M6 Goal 状态仍未知。本次只判断 H1..H2 增量。
