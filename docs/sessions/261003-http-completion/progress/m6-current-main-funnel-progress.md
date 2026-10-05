# M6 当前主干漏斗进度

阶段：implementing → 叶集成验证完成，等待主脑更新 PR 73 / ready / 完整 Gate。
结论：正式 master `4de4a7ff` 上 `git merge --no-ff ad3c9cb` 无冲突；九路径 delta
与 ad3 blob 一致；应用/SDK/CI 相对 Base 226 个文件字节未变。两套完整 suite
各 `482 passed, 3 skipped`；六条 e2e 在裸 env -i 与自有 systemd 各 `6 passed`。
本次只验证消费方兼容，不新开 review 计数，不改 App/SDK/旧文档。

## 现场

- 工作树 `card/http-m6-current-main-funnel-261005`，起点即 Base。
- 无交接单。仓 memory 命中 `sdk-test-fixture-constant-return`（恒返回夹具会消灭时长类缺陷）；
  本卡继续用既有真实 ffmpeg / 非全零参照片，没有新造恒返回夹具。
- 存活探针不可用（`archive_orphan_debts.py` 非零；`memory_report.py` 报
  `memory_dir_mismatch`）。需要时跑 `/worksite-audit`。
- 本仓仍开着 #72/#69/#68/#67/#65/#61/#57/#56/#52/#43 等既有单，不在本卡范围。

## 合入

- `14153db` merge: 从已合主干接续冻结 QA ad3
- 双亲：`4de4a7ff` + `ad3c9cb`；TDD / 两轮独立 review 提交仍是祖先
  （`30f7474`、`52a748c`、`1cd07fe`、`aa39e7f`、`560db3a`）。
- 新文件仅本文与 `m6-current-main-funnel-evidence.md`。

## 全量验证（当前 HEAD，两套 websockets 各一次）

共享锁 `~/.cache/caps-http-261005-fullsuite.lock`，
`flock --timeout 600` 后 `timeout 900`，无自动重试。

- `websockets==15.0.1`：`482 passed, 3 skipped, 163 warnings in 230.56s`；
  锁等待 0.003 s，执行 231.231 s，退出 0。
- `websockets` 解析到 17.2：`482 passed, 3 skipped, 163 warnings in 229.38s`；
  锁等待 0.003 s，执行 229.842 s，退出 0。
- skip 身份两套相同：`test_aligner_integration.py:53`、`:62`（ForceAligner）、
  `test_segmenter.py:208`（silero-VAD）。没有新 skip。
- C2 收口当时是 476 passed；+6 来自冻结 QA 的既有六条，不是本卡新写测试。

## 六条 e2e

- 裸 `env -i`：`6 passed, 14 warnings in 7.87s`，退出 0。
- systemd unit `m6-funnel-e2e-1791167787-1754287`：journal `6 passed` 7.61 s；
  `Result=success` / `ExecMainStatus=0` / `ActiveState=inactive` / `NRestarts=0`。
- producer 边界由既有用例锁定（真实 SDK/TCP/ffmpeg/worker `Task.data` SHA），
  私有目录 `/tmp/m6-funnel-261005/`，公开文档只记布尔/计数/形状。

## 未做 / 留给主脑

- 未开 PR、未 ready、未 rerun、未签、未合默认分支、未部署。
- 正式 QA 草稿仍是 PR 73 / `card/http-m6-qa-261003` / head ad3。
  主脑验后 ff/push 那个 branch、更新正文为本次 Candidate/消费证据、再 ready 完整 Gate。
- draft 绿 / primary SKIPPED 仍不是批准。
- 真实 ASR 质量与生产未测。
- 继承红：派发基线不可用，未能判定。
