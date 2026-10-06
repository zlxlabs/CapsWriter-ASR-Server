# M6 正式合并验收：状态回写与证据分层

M6（HTTP 边界 QA）判定为 **已完成**。本文件只做验收结论与证据分层，不重跑任何测试、不复制原始
工件、不新增防伪机制。schema 通过不等于认证任意 JSON；假引擎不等于 ASR 质量。

## 1. 三个身份不要互代

| 身份 | SHA | 含义 |
|---|---|---|
| CodeHead | `77940745146d377d780e1f840bfbfd633740c114` | 五轮矩阵实现树（`tests/`+harness+CI 契约） |
| PR #83 head | `75a1317905e607aebb279bffcb31a9e6839b00d0` | 待合并的文档与证据 tip |
| merge 主干 | `796104c371c672609cc38ef17d472ef383228cf7` | parents `6aa76f6c`+`75a1317`，19 文件 +2250/-4，非 squash |

从 CodeHead 到 merge，**运行时源码、tests、harness、CI 契约逐 blob 未变**；变的是 `docs/` 证据、
`goals/` 里程碑元与根 `GOALS.md`。因此旧文档里「nonDoc 340 与 CodeH2 全等」的口径在本卡之后
不再成立：其集合含 `goals/` 与 `GOALS.md`，本卡改 `goals/http-integration/M6-qa.md`，主脑再改
`GOALS.md`，两处都是元数据变更，不是代码漂移。

## 2. 十二组真实入口（各 once，不叠 12×5）

十二组语义在冻结源码的全量 JUnit 上逐条 traceable 到具名 node：SDK PATCH/落盘 SHA、跨连接领取
（4 样本）、丢 202 恰好一次恢复、未确认后缀、SIGTERM 重启、持久 fullResult、同 worker HTTP+WS、
取消/IO 交错、容量（缩小常量，非 16 GiB）、**组 10 PCM oracle（2 参数）**、**组 11 末段
finalfail（1）**、组 12 五轮 + 旧 WS。组间样本可重叠，不可相加当总量；真实 skip 三条为资源类
（ForceAligner 后端/模型两处、silero-VAD），与 HTTP 无关，非 HTTP 依赖缺失。
定位：`m6-artifact-closeout.md`、`m6-retained-suite-evidence.md`。

## 3. 两环境各自真跑满 5 轮×4 相位（分层，不互相代充）

- **Hosted**：CI run#37339081182（pull_request，head CodeHead），artifact `11356924649`，
  checkout `8f9a0ec4…`（树同 CodeHead）；CI 步骤为真实 pytest → 同源 `importlib` 消费者
  校验 → 上传，五轮来自 producer 循环而非 JSON 计数。
- **无会话裸 shell**：源 `c6a17380c441263de05399977f8b1228ffd1682a`，外层真实 argv 以
  `env -i` 开头、八键白名单，child 观测到的会话键全部 absent，解释器 `os.execv` 后跑具名
  matrix node，parent rc=0。同源 trace 的 `source_sha` 由 `git rev-parse HEAD` 运行时取得。
- **全量双臂**（pin websockets 15.0.1 与 unpin 17.2）：各 514 cases / 511 passed / 3 skip，rc=0。
  版本来自同次 `importlib.metadata` 实采，不是从卡面推断。
- 定位：`m6-bare-shell-retained-evidence.md`、`m6-h2-hosted-artifact-evidence.md`、
  `m6-h2-delivery-evidence.md`。

## 4. 审查与 CI（真绿，且知道为什么绿）

- 正式 Ready gate run#37364843281：primary / ocr-minimax / quality / resolve / gate / ledger 全
  SUCCESS，notify 非必需 skipped。旧 Draft gate run#37364159057 的 primary/OCR skip **不是**批准。
- Draft 期普通 CI run#37364158249 attempt 3：三个新 job（SDK 3.11 pin/unpin、全量 3.12）全
  SUCCESS；attempt 1/2 是 hosted runner 获取失败、未开始任何 step，不是测试红。官方 Actions
  事故恢复后才重跑一次，未改源码、未延长超时。
- 合并后主干 CI run#37399462648（push，head `796104c`，started 01:29:56Z）三个实际 job 全
  SUCCESS，无 failed step。仅 CI 工作流在 push 触发，不把「PR gate 未触发」当缺审查。
- 审查资格：H1 两份完整审查 verdict + H2 精确增量 verdict（`failure-visibility: p2-only`，
  无应用 P1）。本验收**不新增审查文档**来刷次数。

## 5. 已知 P2 与保留 unknown（不洗）

- **P2**：简单 duplicate round ID 的 relabel 单测会挡住「ID 必须含本轮号」这条 guard；删掉
  `rContains` 后仅 unique 的 fixture 仍绿。guard 当前完整，属 backlog。
- **可证性边界**：全重标 clone 仍被 schema-only 消费者接受。这是 B 范围的结构性局限，不是待做
  的反伪造功能；不升为 P1，不新增 nonce/ledger/Auth/pool/state/fallback。
- 原保：原 CodeHead 交付当时无全量 JUnit，不追认；旧 Draft 等待器 unparseable exit 2 属
  `toolUnknown`，其证据已挂在既有 holder 上，不他仓改码。
- unknown：真实三平台容器、物理 16 GiB 压力、生产 `CapsWriterServer`/`SocketManager` 全装配、
  真实 ASR 字节与质量、Windows 平台结论。**M7 及生产/平台/ASR 质量均未被本次验收代替，仍未完成。**

## 6. 供主脑接续的路线五问（全局 `GOALS.md` 属主脑层，本卡不改）

- **里程碑真完成了吗？** M6 真完成：十二组各 once 有具名入口，两环境各自真 5 轮，真实 producer
  边界、正式 gate、合并后主干 CI 均成立。
- **下一个目标还是对的吗？** M7 仍正确，但需先有 Windows 修复的正常正式合并与新共同运行时，
  再谈三平台基线。
- **有没有漏掉的里程碑？** 没有；路线仍是 M1–M7 全部 done 才算整条路线完成。
- **新证据是否改变了工作顺序？** 没有；依赖链不变，仍是 M4→M6→M7。
- **done 的定义还成立吗？** 成立；单里程碑完成不等于整条 HTTP 路线完成，也不授予生产部署授权。
- 审计历史按各条记录的时间点原保，不因本次收口回洗旧时点结论。

## 7. 本卡边界

本次仅两个文件：里程碑元回写与本验收文档。不改 app/tests/harness/sdk/CI/依赖、M7 文件、旧报告、
envelope 或凭据/账本路径；不跑本地 pytest、不重跑真实矩阵/模型/平台探针。合并后主干 CI 已实测
绿，足够支撑状态回写。`GOALS.md` 生成索引的刷新由主脑在自己的集成树接续后统一出 PR。
