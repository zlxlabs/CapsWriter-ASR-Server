# 最新主干最小 O_BINARY 修复（H2）

- 基线：`dccca739131ac95e54f75bf5611508aa7ff3c20a`；代码提交：`084704c6d201ede2599d1753affc0db74d01ea48`。
- 改动：源文件创建与追加的两个 `os.open` 标志加入 `O_BINARY`；新增一条真实 SDK→HTTP/TCP→Store 回归，覆盖确认前缀、未确认尾、服务重启恢复及 commit 重放。
- 回归断言真实 handler 收到的 PATCH 分块、磁盘字节/SHA、SQLite 状态/offset 和唯一 job；不替换为库 helper 测试。
- H2 单节点 Linux：pinned、unpinned 均 1 passed；两次均绑定代码提交 `084704c`。
- H2 全量 Linux：pinned 与 unpinned 各 554 passed、3 skipped、0 failures、0 errors；skip 是既有模型/依赖缺失用例。JUnit 与运行日志留在 `~/.cache/caps-pr82-combined-261006-285aff49/h2-verification/`。
- Windows 原生单节点：base `dccca739` 分类为 `base_byte_red`，确认 offset 7 时物理前缀被 LF→CRLF 扩展，物理 9 bytes、prefix/SHA 不同；H2 `084704c` 分类为 `h2_byte_green`，1 passed，41 bytes/SHA 与 producer 一致，confirmed offset 41、COMMITTED、仅 1 job。
- Windows 环境为 Python 3.11.7、NumPy 2.4.6、websockets 17.2；manifest SHA-256 `65c94e49d044753edeef9e8a24219569a9ccf196c58811ad22fb15ed339408cc`。两包 SHA-256：base `2c3f43b61d725c15ac1973430b8e0451bf28c2665cca7acd850c0743ae166e2e`，H2 `a66586985fe594a92b84b482e4325cbf9b6bf19276a9d802157bbee72e4571e0`。
- Windows 直接证据保存在用户 Temp `caps-pr82-win-h2-340b4ce4-73e8-4b9b-89c1-ee54cfe65b3b/incoming/results/{base,h2}/`：各含 `result.json`、JUnit、pytest stdout/stderr；源码/运行清单与 SHA 的校验结果在 `results/verify.json`。
- 旧 H1 Windows 绿仅作背景，不计入 H2 证据；任务派发时主干基线查询失败，继承红未能判定。
- 收尾核查时 `origin/master` 已到 `03ec517`：相对 `dccca739` 增加 8 份 #76/#85/#87 证据文档，并只改 `tests/test_ws_decode_failure.py` 的终态日志断言；H2 触碰文件无差异，未自动 rebase。
- Draft PR：[#99](https://github.com/zlxlabs/CapsWriter-ASR-Server/pull/99)，仍保持 Draft；代码 H2 为 `084704c6d201ede2599d1753affc0db74d01ea48`，本次仅更新本进度文档记录 Windows 结果。
