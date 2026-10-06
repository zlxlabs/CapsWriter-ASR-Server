# 最新主干最小 O_BINARY 修复（H2）

- 基线：`dccca739131ac95e54f75bf5611508aa7ff3c20a`；代码提交：`084704c6d201ede2599d1753affc0db74d01ea48`。
- 改动：源文件创建与追加的两个 `os.open` 标志加入 `O_BINARY`；新增一条真实 SDK→HTTP/TCP→Store 回归，覆盖确认前缀、未确认尾、服务重启恢复及 commit 重放。
- 回归断言真实 handler 收到的 PATCH 分块、磁盘字节/SHA、SQLite 状态/offset 和唯一 job；不替换为库 helper 测试。
- H2 单节点 Linux：pinned、unpinned 均 1 passed；两次均绑定代码提交 `084704c`。
- H2 全量 Linux：pinned 与 unpinned 各 554 passed、3 skipped、0 failures、0 errors；skip 是既有模型/依赖缺失用例。JUnit 与运行日志留在 `~/.cache/caps-pr82-combined-261006-285aff49/h2-verification/`。
- Windows 本轮未取得 base 字节红或 H2 字节绿，不能视作原生准入。目标环境定位记录指向与最初试探的 SSH 别名不同；唯一 SFTP 批次在 `mkdir` 路径解析处失败，四个包文件未上传，未重试。
- 旧 H1 Windows 绿仅作背景，不计入 H2 证据；任务派发时主干基线查询失败，继承红未能判定。
- 收尾核查时 `origin/master` 已到 `03ec517`：相对 `dccca739` 增加 8 份 #76/#85/#87 证据文档，并只改 `tests/test_ws_decode_failure.py` 的终态日志断言；H2 触碰文件无差异，未自动 rebase。
- 当前仅保留本地代码与本进度记录，不推送、不创建 Draft PR；待 Windows 目标连接与单次传输窗口可用后再完成原生红绿验证。
