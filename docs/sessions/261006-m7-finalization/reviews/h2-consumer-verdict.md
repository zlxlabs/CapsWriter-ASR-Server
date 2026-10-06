# H2 消费者视角独立终审

- 固定范围：`dccca739131ac95e54f75bf5611508aa7ff3c20a..084704c6d201ede2599d1753affc0db74d01ea48`（两文件：`http_store.py` 两处 source fd、`test_http_file_tasks.py` 回归 + `running_server(port)`）。
- spec：`docs/reference/protocol.md`（PATCH 原字节、commit 重复 200 同一 `job_id`）；`sdk/README.md`（resume 按服务端 `confirmed_offset` 只传未确认原始字节，不换地址）。
- 风险档：internal。视角：`sdk/capswriter_asr/http_client.py` 的 `submit_file_http` / `resume_file_http` / recovery `base_url`+`confirmed_offset` / `_commit_upload`，反向核测试边界，不按 Store 自述解释。
- OCR：`/tmp/caps-pr82-h2-review-ocr.json` status=reviewed profile=minimax coverage=complete findings=0；未读理由、未重扫。
- `git diff --check`：exit 0。
- failure-visibility: clean

## 不变式 · 代码与测试锁

1. 原字节 PATCH（protocol PATCH 行）：`http_server._patch_upload` 经 `_read_body`（`request.content.read` → `bytes(buffer)`）把真实请求体交给 `HttpStore.append_bytes`；source 创建/追加 fd 为 `os.open(...) | getattr(os, "O_BINARY", 0)`（`http_store.py` 创建与 `append_bytes`）。锁：`test_http_binary_payload_survives_append_recovery_and_commit_replay` 用 41B `\x00/\n/\r\n/\x1a/\xff` 源走真实 SDK+TCP，断言 handler 入参 `patches==[(0,[:7]),(7,[7:14]),(7,[7:])]`，且盘字节/sha256 等于源。
2. 未确认尾按 DB offset 截断（protocol 持久化：不以文件长度冒充确认）：`append_bytes` 先 `ftruncate(fd, confirmed)`。锁：同测在确认前缀后写入 `unacknowledged-tail`，同端口重启真实 listener/Store 再 `resume_file_http`；盘相等、size=41、GET/DB `confirmed_offset==size_bytes==41` 任一漏截或失真即红。
3. commit 重放不造第二 job（protocol commit 行）：handler 先 `committed_job` 再预算。锁：SDK resume 已受理后 httpx 再 POST `/commit`，断言 200、同一 `job_id`、`SELECT job_id FROM jobs` 行数=1。
4. POSIX 原行为：`O_BINARY` 缺省 0，两处 flags 与改前按位相同。无新抽象：只给已有 `running_server` 加 `port: int = 0`。

## 五问

1. 41B 源→handler→盘/DB：有真实断言（上节 1：patches / 盘 / GET / `_read_db`）。
2. 漏截或失真却绿：不能（上节 2）。
3. 重放造第二 job 却绿：不能（上节 3）。
4. POSIX default 0 保持原行为：是。
5. 新增不必要抽象：无。

## Findings

无。未发现源代码未解决缺陷。本结论不是模型/M7/正式 CI 完成。Windows 自动 CI、存量与一般安全假设不在本轮；不以本机未跑 pytest 冒充代码错误。无法溯源 spec 的泛化不阻塞。
