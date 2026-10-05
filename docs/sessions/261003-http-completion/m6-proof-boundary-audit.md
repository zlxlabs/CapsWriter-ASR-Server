succeeded

# M6 五轮工件的可证边界审计

## 结论

- H1 消费者能校验 JSON 结构、字段关系与局部约束，不能认证五轮事件真的发生。完整重标副本仍被接受，已用 H1 Hosted 原工件和 H1 消费者复现。
- 这不推翻真实 producer 的五轮目标：五轮事实来自实际循环、四相位操作与运行环境；消费者只负责检查发布文件的结构。不要把“消费者接受”单独写成“真实执行已证”。
- H1 Hosted run `37311065357` 的结论为 success，工件 `11346765500` 来自指定 H1 源 SHA；工件结构消费者读取同路径文件。裸环境的既有证据按派发输入称为存在，本审计未重跑或独立取回，故不以 Hosted 工件替它背书。
- 当前可核实的是 Hosted 五轮证据链与 false-positive。双环境五轮只有在独立裸环境 producer/运行证据成立时才满足该项；整体 M6 仍不能据此宣布完成：原 Goal 状态仍为“进行中”，12 组和正式 gate/主干验收是分开的条件。

## 字段来源与消费者读法

|字段|Producer 的事实来源|H1 消费者实际检查|可证明边界|
|---|---|---|---|
|轮次、相位、pass|`REPEAT_COUNT` 循环；每轮四相位断言通过后追加|数量、顺序、相位名、`pass is True`|结构完整；同一 JSON 可整体复制、重写|
|`round_job_id`|并发含真实 job id 前 8 位；取消与 WS 标签由 `round_id` 拼出；重启标签含 PID|字符串含 `r{n}`，且本文件内不重复|可拒“只改 round、不改 ID”的旧样本；不能认证 ID 来源|
|并发/取消/重启/WS 字段|真实 handler、worker、SQLite、磁盘、进程与 WS 操作先断言，再记匿名值|检查布尔、计数、PID 不等、offset 关系|生产代码运行时有证据；消费端只见可改写的值|
|`ffmpeg_log_offset` / `source_sha`|producer 读本轮调用日志下标；SHA 取 `git rev-parse HEAD`|只检查 offset 单调和 SHA 格式|不与外部日志或当前源码比对，副本可重写|
|runtime / producer roles|producer 写运行时名与角色列表|只检查非空/类型|标签不是进程或环境认证|

## 五问

1. **层级 0 是否必要？** 必要职责是工件结构与字段约束，不是认证执行来源。相同 JSON 字节可被重写成另一份结构有效的 JSON；不存在可由这个消费者单独读取的不可改写事实源。不要加 nonce、签名、第二账簿或配置框架来追求此边界之外的保证。
2. **五轮里程碑是否完成？** Hosted 侧的运行来源与真实工件已核实；派发给出的裸环境证据未在本审计独立复核。两者与消费者抗完全重标不是同一条件：前者证明 producer 执行，后者验证发布结构。即使两个五轮执行均成立，也不替代 `M6-qa.md` 的 12 组证据、真实 skip 原因和正式 gate/主干验收。
3. **根因与下一目标是否仍对？** 根因是把 schema 校验表述成事件真实性认证，不是某个比较对象少加一项。现有 `round_job_id`、PID 对、日志偏移、任务字段都在同一文件里；部分 ID 是按轮拼的标签，PID 可复用，偏移可重写。没有已存在的跨边界唯一事实可安全补比较；不新增机制或 P2。
4. **有无漏里程碑或需改顺序？** producer 在执行真实相位并断言后才追加 trace；CI 先跑一次 pytest，再由 importlib 消费同一路径文件并上传。真实来源要靠该 producer/运行环境证据确认，不能让文件自证。此发现不改变五轮次数、同一持久根或四相位目标，也不要求改 Goal/index。
5. **Done 定义还成立吗？** 选择 B：删除“任意自贴标签都必须被拒”的强承诺，说明消费者只作 schema/结构验证；保留对仅改轮次号且未改对应 ID 的拒绝。真实 5 次 producer 循环、Hosted 与裸环境各自的证据要求原样保留，因此没有降低用户目标。原 H1 设计只明确要求拒绝“不含该轮独特 job id”的简单重标样本，并未要求抵抗完整重写同一 JSON。

## 复现与依据

- 使用 Python 3.12.3，以 importlib 从工作树 H1 的 `tests/test_http_qa_repeat_matrix.py` 原位置加载消费者；输入是 Hosted run `37311065357` / artifact `11346765500` 的实际 `trace.json`。原件被接受。没有回显 trace、音频、摘要、IP、路径或环境值。
- 将原件首轮深拷贝五份，只改 `round`、四相位 `round_job_id`、递增 `ffmpeg_log_offset`，写入克隆 marker 与新字节；报告值仅为 `original_accept=true`、`rounds=5`、`bytes_changed=true`、`marker_written=true`、`full_relabel_accept=true`。初次临时导入缺少仓库根模块路径，补入真实 H1 根路径后复现成功；该次是探针启动错误，不是产品红。
- 原始要求：`goals/http-integration/M6-qa.md` 要 12 组并含至少五次并发回归，完成条件仍覆盖全部 12 组；`docs/sessions/261001-http-files/qa.md` 要跨边界断言 producer 实际发出的对象/字节；`docs/sessions/261001-http-files/design.md` 保留真实客户端、文件和进程边界。H1 循环/同服务/双消费者规则见 `docs/sessions/261003-http-completion/m6-repeat-matrix-design.md`。
- 源码证据：producer 循环与逐轮真实操作、日志切片、写 trace、最终消费在 `tests/test_http_qa_repeat_matrix.py:1063-1104`；消费者只读 trace 字节并验证字段在 `:65-151`；旧反例 `:358-369` 仅保留首轮 `round_job_id`，没有改成完整重标，故只能证明拒绝该简单样本。Hosted workflow 的 pytest、同路径 importlib 消费和 artifact 上传见 `.github/workflows/ci.yml:53-85`。
- 未改源码、Goal、index、App、配置或测试；未重跑完整矩阵、500 项套件、模型、Windows/Systemd、生产或 OCR。未收到/查阅正式 consult 意见。
- Pickup：工作树干净且是本 dispatch 自己的 worktree；无交接单。收件箱有 #81（分支工件未落主干，相关）与 #76（WS 长任务，本卡不处理）。巡检项未展开，需要时跑 `/worksite-audit`。memory 探针返回 `memory_dir_mismatch`；按 pickup 指引在 agent-config 仓运行 memory doctor 重建。公开审计页不保留本机路径。基线 `gh api request failed`，继承红状态未能判定；本次 clone 复现通过。
