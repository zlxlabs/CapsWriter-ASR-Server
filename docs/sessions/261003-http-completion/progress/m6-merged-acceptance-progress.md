# M6 合并主干验收进度

## 状态

- 阶段：`verifying`
- source：`3d26d90b707003cbbc0b31d8d0e2e1f823f4d2a3`
- 当前结论：已完成本卡要求的主干取证与两份正式 Doc；M6 Goal 仍保持「未开始」，不提前改成 Done。
- 允许改动：本文件与 `m6-merged-acceptance-evidence.md`；没有修改 App、SDK、collector、测试、CI、旧 Doc、Goal 或账本。

## 已完成

1. 独立确认 `HEAD`、`origin/master`、合并树、候选祖先关系；读取 M6 Goal、HTTP 文件设计/QA 契约和 review 纪律。
2. 固定 WebSockets 15.0.1 完整套件有效运行：`481 passed, 3 skipped, 1 failed`。唯一红是既有 systemd fatal cleanup 测试在 unit 退出后没有及时读到 `post_fatal` 报告；没有可用基线，继承红关系未能判定。
3. WebSockets 未 pin 完整套件实际解析为 17.2，结果 `482 passed, 3 skipped`；三个 skip 的具名资源原因已原样保留。
4. 同一主干源码的三个窄模块连续 5 轮，每轮 `49 passed`、exit 0；每轮都使用独立临时目录、port 0、SQLite、真实 TCP/ffmpeg/Queue/worker。监督模块内的裸环境白名单探针随 5 轮实际执行。
5. 既有 systemd fixture 的正常消费节点独立执行 5 轮，每轮 `1 passed`；证据包含独立 unit、PID/cgroup、SQLite、端口和真实边界。
6. 记录了 master 同 SHA 的 push CI `37260999978`、PR73 候选正式 gate `37258495073`、候选 CI `37258462419`，并明确 draft `37258462809` 不计正式绿。

## 未满足的整体完成边界

- Hosted CI 只有各 run 的单次 workflow 消费，没有五轮窄矩阵证据；本地五轮不能代替 Hosted CI 五轮，因此不宣称 M6 Goal Done。
- 固定 pin 完整套件的 systemd fatal cleanup 时序红仍在；本卡是 DocOnly，不修实现、不重跑到绿。
- 本次证据不覆盖真实 ASR 质量、生产鉴权、硬 2 GiB 峰值保障或真实 16 GiB 体量压测。

完整逐组位置、producer payload/argv/env/源字节/PCM/Queue 对齐和命令结果见：
`docs/sessions/261003-http-completion/m6-merged-acceptance-evidence.md`。
