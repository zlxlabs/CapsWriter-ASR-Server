# #81 历史清账修后证据复核（R3）

failure-visibility: p2-only

## 结论

发现一项 P2：公开复核器没有锁定 TSV 的冻结规模与分类集合。当前数据实际完整且复算一致；但删除一整条路径记录或把分类改为未知值，复核器仍返回 `RESULT: PASS`，无法约束任务要求的 147 路径 / 449 来源 / 10 类完整性。

本轮独立性流程发生输入隔离偏差，执行器任务结果为 failed。此 verdict 保留本轮实测 finding 与证据，不能单独作为 #81 的独立 review 放行结论；需由新的隔离审查者复核。

## 冻结范围与 OCR

- Base：`e849c21748392ad848131e07ff17d32e4cc83a8b`
- Head：`88aaa697ea6893b7315932be22813b159f601f30`
- 先审增量：`9b498640712ec0fc3671a579955ba4a2204a0438..88aaa697ea6893b7315932be22813b159f601f30`；再审全量：`e849c21748392ad848131e07ff17d32e4cc83a8b..88aaa697ea6893b7315932be22813b159f601f30`。
- 全量为 7 files、735 insertions、1 deletion；实现新增量 350 不套用为被审实现预算。
- 摘要文件 `/tmp/capswriter-artifacts-review2-dlg-20261006-055220-0a0b2d/spec-summary.md` 为 3,394 bytes（上限 8,000）。
- OCR 命令（repo 根以 Git 查询展开，命令行不固化本机工作区身份）：`ocr-review --repo "$(git rev-parse --show-toplevel)" --from e849c21748392ad848131e07ff17d32e4cc83a8b --to 88aaa697ea6893b7315932be22813b159f601f30 --audience agent --concurrency 4 --background-file /tmp/capswriter-artifacts-review2-dlg-20261006-055220-0a0b2d/spec-summary.md`
- stdout envelope：`{"status":"skipped","profile":"minimax","model":"MiniMax-M3.1-Flash-Preview","reason":"no_reviewable_items","findings":[],"cli_status":"skipped","coverage":"none","verify":{"verify_status":"skipped","verifier":"none","concurrency":4,"counts":{"total":0,"verified":0,"confirmed":0,"refuted":0,"unverifiable":0,"unverified":0},"reason":"","budget_s":900.0,"finding_timeout_s":120.0},"attendance_ledger_write":"ok"}`。按 `skipped` 处理，未算作已审。

## Finding

### P2 — 复核器对 TSV 路径规模和分类变更不敏感

- 违反条款：spec 要求完整解析冻结的 147 路径 / 449 来源、独立校算 10 类与 147 条类别计数，并要求对被审数据变异有效的负控。
- 位置：[docs/development/known-issues/artifact-disposition-261006.md:138] 读取 TSV 当前内容并拆行；`:139` 只校表头；`:143-145` 只检查当前行的字段非空；`:147-159` 逐条核当前仍存在的来源；`:229-232` 在 `fail` 为空时返回 PASS。`_bstate` 未校验，且没有路径数、来源数、类别允许集或类别计数断言。
- 复现：执行公开代码块的抽取版本，完整数据为 `RESULT: PASS`。把最后一条 TSV 路径记录从消费者实际读取的 TSV payload 移除后，输出变为「已核 446 条来源记录、状态不符 0 条」，最终仍为 `RESULT: PASS`、退出码 0。将同一条记录的 disposition 改成 `invented-category`，仍为 `RESULT: PASS`、退出码 0。
- 真实后果：将来若冻结表漏行或某行误分类，复核器会把不完整/未登记分类的数据报成通过；据此复核 #81 清账结论会漏掉未盘点路径或分类漂移。当前被冻结数据实值经独立解析为 147 / 449 / 10，未发现现存漏行或错误分类。按文档证据完整性影响判 P2；没有生产运行时失效证据，未判 P1。

## 本轮事实核验

- TSV 全量解析：147 行、无重复 path、449 条 source；`baseline_state` 为 34 `EXISTS_AT_BASE` / 113 `MISSING_AT_BASE`，与 147 个 Git 路径对象逐项相符。
- `source_state`：22 `BLOB_SAME_AS_BASE`、28 `BLOB_DIFF_FROM_BASE`、360 `BLOB_BASE_MISSING`、39 `NO_PATH`。公开复核器逐源查询实际 Git 对象，正常 payload 输出已核 449、状态不符 0、不可用 0。
- 10 类计数逐行解析与文档表格一致：`content-in-baseline-no-action` 17、`baseline-has-later-divergent-content` 17、`archive-pointer-old-process` 77、`archive-pointer-current-dependency` 2、`archive-pointer-association-unverified` 1、`excluded-content-not-copied` 18、`not-restored-scope-decided` 6、`superseded-path-registered` 1、`in-flight-issue-82` 4、`in-flight-other-card` 4，合计 147。17 条 `baseline-has-later-divergent-content` 逐项核实 source/base blob 不同、base 路径最后修改时间晚于 source commit；分类只证明内容与时间事实，没有推断语义覆盖。
- 负控：source SHA 换为不存在对象时输出 `UNAVAILABLE ... observed=OBJECT_UNAVAILABLE`、`RESULT: FAIL`、退出 1；EV-A1 中两条原文换序时输出「不是连续原文」、`RESULT: FAIL`、退出 1。两处坏态分别单独执行；之后以原 payload 再跑，恢复 `RESULT: PASS`。
- 附录 5 段通过连续完整行校验。公开复核器文档链接检查输出断链 0；`docs/development/testing.md` 的 CI 说明与冻结 CI 的 pytest 步骤一致，未找到 lint 步骤。
- 历史对象只核 blob 身份：`6633b74e`、`391d1d15`、`8669585b` 对 `artifact-review1-verdict.md` 的树项均为 blob `e5a2a407fc16dc758dc55729ab052d8b28a7f2de`；当前对应树项仍同 blob。未打印该文件正文。
- 六项旧资产仍标为本轮不恢复；日志/memory 内容未复制；65/38 与 449/147 两套口径未混用；337 refs 未当重建分母；`#82` 仍标在途。

## 未验证限制

- OCR 为 `skipped / no_reviewable_items`，未提供审查覆盖。
- 未跑全量测试套件；仅执行卡面要求的公开复核代码、正负控与 `git diff --check`。
- 本轮只确认 17 条 divergence 的 Git 内容/时间，不对旧内容与新内容做语义等价判断。对 TSV 中明示未证实的消费者关系仍保留未证实，不推成「无人引用」。
- 输入隔离偏差：一次批量读取把进度存档中的历史 review 摘要带入本轮上下文；公开复核器还按其 `DOCS` 清单打开两份历史 verdict 来检查相对链接。未在本 verdict 复述那些历史判断，但已无法撤回这两处输入暴露，本 verdict 的独立审查资格因此不成立，需另起隔离审查。
