# #81 历史清账修后独立审查 2 Verdict

- 风险等级：internal
- 冻结审查范围：`e849c21748392ad848131e07ff17d32e4cc83a8b..9b498640712ec0fc3671a579955ba4a2204a0438`
- 输入：冻结 Git 对象、任务卡 spec 和范围内文档；未读实现报告或实现推理。
- 全量 diff：6 个文档，639 行新增、1 行删除。卡面明确 600 行预算只限本 verdict，不用于追责被审实现。
- OCR 命令（公开记录中将本机路径变量化）：`ocr-review --repo "$(git rev-parse --show-toplevel)" --from e849c21748392ad848131e07ff17d32e4cc83a8b --to 9b498640712ec0fc3671a579955ba4a2204a0438 --audience agent --concurrency 4 --background-file "$OCR_SPEC_SUMMARY"`；实际调用使用本卡工作树与本派发唯一 scratch 中的 `spec-summary.md`。
- OCR stdout envelope：`{"status":"skipped","reason":"no_reviewable_items","findings":[]}`，包装器退出码 0；此状态不计为已审。

failure-visibility: p2-only

## 结论

`changes-required`：未发现 P1，确认 2 项 P2，均落在文档内自包含复算器的验收边界。冻结 TSV 的当前数据、分类统计、时序证据和五段历史摘录本身通过独立核对；这不抵消复算器在指定坏态下仍通过的问题。

## Findings

### P2-1：归档对象不可用时最终仍报告 PASS

**违反 spec**：新 clone 缺归档对象必须显示为对象不可用，且不能默认 PASS。

**位置**：`docs/development/known-issues/artifact-disposition-261006.md:144` 将 `OBJECT_UNAVAILABLE` 只计数、打印后 `continue`；`:211` 和 `:214` 仅根据 `fail` 决定 `RESULT` 与退出码，没有把不可用计入失败或未完成状态。

**独立探针**：将 TSV 第二个来源记录的 SHA 改成一个不存在的 SHA（保留源路径、状态及其余真实 Git 对象），其他本地文档和链接均齐全。脚本打印 `UNAVAILABLE .cursor/rules/00-delegate-executor.mdc ... observed=OBJECT_UNAVAILABLE`，汇总为“448 条来源记录、1 条对象不可用”，随后仍输出 `RESULT: PASS` 并以退出码 0 结束。注入已确认只命中 1 条来源记录。

**后果与风险**：部分归档对象缺失的 clone 可被机器调用方按成功处理，未验证的来源随之混入清账通过结论。影响内部证据复核，不影响运行时；判 P2。

### P2-2：摘录校验允许行重排，不能证明原文连续

**违反 spec**：摘录须按连续原文字节核对并保留判定上下文，不能只验证任意逐行集合。

**位置**：`docs/development/known-issues/artifact-disposition-261006.md:186` 把源内容转成行集合；`:187-188` 丢弃空行后逐行查集合成员，未比较原文连续字节或顺序。

**独立探针**：当前附录 EV-A1 的原文在真实 source 对象中确为连续字节；我在隔离副本中只把摘录的 `failure-visibility: p2-only` 与 `## 结论` 两行换序，变异脚本断言替换成功。随仓复算器仍报 5 段摘录、`RESULT: PASS`、退出码 0。独立字节比较确认当前真实附录 5/5 段都连续匹配 source 对象。

**后果与风险**：摘录的顺序或上下文被改写时，复算器仍会确认其来源；历史结论审查无法依赖该复算结果发现错序。影响内部历史证据，不影响运行时；判 P2。

## 独立核查事实

- 完整解析 TSV：147 个唯一路径、449 条源记录、五栏非空且无重复路径；基线为 34 条存在、113 条缺失。逐条 Git 对象复算为 `BLOB_SAME_AS_BASE=22`、`BLOB_DIFF_FROM_BASE=28`、`BLOB_BASE_MISSING=360`、`NO_PATH=39`，不可用/查询错均为 0，状态不符 0。
- 实际 disposition 共 10 类，数量为 17/17/77/2/1/18/6/1/4/4，合计 147。17 条 `superseded-in-baseline` 均有不同 blob 来源，且每条至少有一个不同 blob 来源提交早于基线路径最后修改提交；同 blob 来源未被计作取代。六项不恢复资产都在源对象中找到 blob，且本轮明确保留不恢复及重开条件。
- 当前工作树运行公开复算入口：449 条来源状态不符 0、摘录 5 段、文档链接断链 0、`RESULT: PASS`。对同 blob 来源行把 disposition 变异为 `superseded-in-baseline` 后，负控报告该路径违例并返回失败，证明这项负控对该类数据变异有效。
- `artifact-review1-verdict.md` 与其原始提交 `6633b74e4127f157108529321491ff07b9a213f4` 的 blob 均为 `e5a2a407fc16dc758dc55729ab052d8b28a7f2de`，原文未改。
- `docs/README.md:27` 和 `docs/development/designs/documentation-layout.md:40` 均指向当前 `docs/development/testing.md`；实际 `.github/workflows/ci.yml` 有 pytest 与五轮矩阵工件校验、没有 lint 步骤，`gate.yml` 调用外部 Required Gate v2。修订后的 testing 文档与这些消费者一致。#82 及其他在途类别保留为在途，没有判作已解决。65/38 与宽归档口径分列，337 refs 明确为当次运行记录。

## 未证实与限制

- `docs/testing.md` 到 `docs/development/testing.md` 的**路径映射**由 README 和布局文档证实；旧文档中 `uv sync`、Dev Container 等内容并未在新 testing 文档逐项重述。相关六项资产有各自的不恢复理由与重开条件，但当前是否仍有人消费旧开发环境说明没有独立需求证据。本 verdict 只确认路径映射，不推断所有旧段落已被语义覆盖。
- OCR 为 `skipped`，不是审查结论。未运行本机全量 suite 或 CI；本轮是文档审查并按卡面运行 `git diff --check`。
- 派发卡记录主干基线 API 获取失败；继承红无法判定。本轮未运行 CI，因此没有新的 CI 红可归因。
