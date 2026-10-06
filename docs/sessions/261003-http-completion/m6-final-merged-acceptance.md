# M6 正式合并验收：状态回写与证据分层

M6（HTTP 边界 QA）判定为 **已完成**。本文件只做验收结论与证据分层，不重跑任何测试、不复制原始
工件、不新增防伪机制。schema 通过不等于认证任意 JSON；假引擎不等于 ASR 质量。

## 1. 三个身份不要互代

| 身份 | SHA | 含义 |
|---|---|---|
| CodeHead | `77940745146d377d780e1f840bfbfd633740c114` | 五轮矩阵实现树（`tests/`+harness+CI 契约） |
| PR #83 head | `75a1317905e607aebb279bffcb31a9e6839b00d0` | **合并前**最终文档与证据 tip（该 PR 已正式合并，不是仍待合并） |
| merge 主干 | `796104c371c672609cc38ef17d472ef383228cf7` | parents `6aa76f6c`+`75a1317`，19 文件 +2250/-4，非 squash |

从 CodeHead 到 merge，**运行源码、tests、harness、CI 契约逐 blob 未变**，该阶段实际变更**只有
`docs/`**（14 个文档文件），`goals/` 与 `GOALS.md` 未被改；故「以 `docs/` 为唯一过滤的 340 个非
文档 blob 与 CodeH2 全等」在 merge `796104c` 处**仍成立**。本卡的 Goal 元回写是另一件事：`750848b`
改了 `goals/http-integration/M6-qa.md`，主脑随后还会改 `GOALS.md`，两者都在该 340 集合内，故该集合
**在本次元数据增量后不再全等**。两个口径分开读：「不再全等」只说元数据变了，不能推导成运行源码
漂移；「运行源码等价」也不能反向担保元数据未变。

## 2. 十二组真实入口（各 once，不叠 12×5）

十二组语义在冻结源码的全量 JUnit 上逐条 traceable 到具名 node：SDK PATCH/落盘 SHA、跨连接领取（4 样本）、
丢 202 恰好一次恢复、未确认后缀、SIGTERM 重启、持久 fullResult、同 worker HTTP+WS、取消/IO 交错、容量
（缩常量非 16 GiB）、**组 10 PCM oracle（2 参数）**、**组 11 末段 finalfail（1）**、组 12 五轮+旧 WS；
组间样本可重叠不可相加，真实 skip 三条为资源类（ForceAligner 两处、silero-VAD）与 HTTP 无关。定位：
`m6-artifact-closeout.md`、`m6-retained-suite-evidence.md`。

## 3. 两环境各自真跑满 5 轮×4 相位（分层，不互相代充）

- **Hosted**：CI run#37339081182（pull_request，head CodeHead），artifact `11356924649`，checkout
  `8f9a0ec4…`（树同 CodeHead）；CI 步骤为真实 pytest → 同源 `importlib` 消费者校验 → 上传，五轮
  来自 producer 循环而非 JSON 计数。
- **无会话裸 shell**：源 `c6a17380c441263de05399977f8b1228ffd1682a`，外层真实 argv 以 `env -i` 开头、
  八键白名单，child 观测到的会话键全 absent，`os.execv` 后跑具名 matrix node，parent rc=0；trace 的
  `source_sha` 运行时取 `git rev-parse HEAD`，不是手写标签。
- **全量双臂**（websockets pin 15.0.1 与 unpin 17.2）：各 514 cases / 511 passed / 3 skip，rc=0；
  版本来自同次 `importlib.metadata` 实采，不是从卡面推断。
- 定位：`m6-bare-shell-retained-evidence.md`、`m6-h2-hosted-artifact-evidence.md`、`m6-h2-delivery-evidence.md`。

## 4. 审查与 CI（真绿，且知道为什么绿）

- 正式 Ready gate run#37364843281：primary / ocr-minimax / quality / resolve / gate / ledger 全 SUCCESS，
  notify 非必需 skipped。旧 Draft gate run#37364159057 的 primary/OCR skip **不是**批准。
- 普通 CI run#37364158249 **创建于 Draft 阶段**，第三次实际运行在 Ready 之后：attempt 3 于
  2026-10-06T01:20:27Z 创建/01:20:26Z 开始，晚于正式 Ready gate run#37364843281（19:39:45Z），
  三个新 job（SDK 3.11 pin/unpin、全量 3.12）全 SUCCESS。前两次未构成测试红：attempt 1 三个 job 中
  两个 `cancelled`/0 step、3.11 unpin job 实跑 11 步 success；attempt 2 三 job 全 `cancelled`/0 step；
  成因属平台/工具侧，本卡不重新诊断。官方 Actions 事故恢复后才重跑这一次，未改源码、未延长超时。
- 合并后主干 CI run#37399462648（push，head `796104c`，started 01:29:56Z）三个实际 job 全 SUCCESS，
  无 failed step。仅 CI 工作流在 push 触发，不把「PR gate 未触发」当缺审查。
- 审查资格：H1 两份完整审查 verdict + H2 精确增量 verdict（`failure-visibility: p2-only`，无应用
  P1）。本验收**不新增审查文档**来刷次数。

## 5. 已知 P2 与保留 unknown（不洗）

- **P2（准确表述）**：旧的那个简单 relabel 单测**保留了重复 round ID**；即使删掉 `r{round_id}` 包含
  guard，同一 fixture 仍先被 duplicate-ID 检查拒绝，所以**原单测仍绿**，掩盖了 guard 缺失。guard
  当前**未被删除**，属 backlog。能辨别该 guard 的是独立现场负控（ID 唯一但轮号错误），该负控**没有**
  被修进原 CI 单测。
- **可证性边界**：全重标 clone 仍被 schema-only 消费者接受，是 B 范围的结构性局限，不是待做的
  反伪造功能；不升为 P1，不新增 nonce/ledger/Auth/pool/state/fallback。
- 原保：原 CodeHead 交付当时无全量 JUnit，不追认；该阶段 CI 等待器 32/33/34 属 `toolUnknown`
  （不据此猜绿也不猜红），证据已挂在既有 holder，不他仓改码。
- unknown：真实三平台容器、物理 16 GiB 压力、生产 `CapsWriterServer`/`SocketManager` 全装配、真实
  ASR 字节与质量、Windows 平台结论。**M7 及生产/平台/ASR 质量未被本次验收代替，仍未完成。**

## 6. 冻结边界：结论只覆盖 merge `796104c`，不覆盖之后的主干

本次 M6 完成结论**冻结于 merge `796104c371c672609cc38ef17d472ef383228cf7` 及其真实运行与审查**
（§2–§5 每条证据都产生于该时点）。此后主干已前移：`git ls-remote origin master` 实测
`d251618e16766061074fe5767d6aecd39b9f9236`，相对 `796104c` 为 11 文件 +667/-246 且**改了运行源码**
（`core/protocol.py`、`core/server/{connection/ws_recv,state,worker/process_manager}.py`、
`sdk/capswriter_asr/client.py`、`tests/harness/server.py` 与三个测试文件）。该提交 subject 写
「修 #76（#76）」，但 API 中 `#76` 是 OPEN issue 而非 PR，故只按 SHA 引用。
`796104c` 处的非文档 340 集合等价、514 cases/511 passed/3 skip 双臂、裸壳与 Hosted 真五轮、正式
审查，**都不覆盖 `d251618e` 的运行源码变化**。本文件不把历史证据当成对最新主干的重新资格，也不
断言该 peer 改动对错（本卡不审、不改、不重新测试它）。Goal 只记「M6 在 `796104c` 历史时点真实
完成」，不是「在最新主干上再次全量验证 M6」。

## 7. 供主脑接续的路线五问（全局 `GOALS.md` 属主脑层，本卡不改）

- **里程碑真完成了吗？** M6 真完成：十二组各 once 有具名入口，两环境各自真 5 轮，真实 producer 边界、正式 gate、合并后主干 CI 均成立（覆盖范围见 §6）。
- **下一个目标还是对的吗？** M7 仍正确，但需先有 Windows 修复的正常正式合并与新共同运行时。
- **有没有漏掉的里程碑？** 没有；路线仍是 M1–M7 全部 done 才算整条路线完成。
- **新证据是否改变了工作顺序？** 没有；依赖链不变，仍是 M4→M6→M7。
- **done 的定义还成立吗？** 成立；单里程碑完成不等于整条 HTTP 路线完成，也不授予生产部署授权。
  审计历史按各条记录的时间点原保，不因本次收口回洗旧时点结论。

## 8. 本卡边界

本次仅两个文件：里程碑元回写与本验收文档。不改 app/tests/harness/sdk/CI/依赖、M7 文件、旧报告、
envelope 或凭据/账本路径；不跑本地 pytest、不重跑真实矩阵/模型/平台探针。合并后主干 CI 已实测绿，
足够支撑状态回写。本分支保持母 base `796104c`，**不合并** §6 的 peer 主干；该 metadata-only 增量
由主脑接到新主干评估实际组合 diff，`GOALS.md` 生成索引同由主脑在自己的集成树接续后统一出 PR。
