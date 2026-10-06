<p data-outcome="pass">PASS — P2 only</p>

- delegate-outcome: complete
- verdict: pass_with_p2
failure-visibility: p2-only
- fixed range: `dccca739131ac95e54f75bf5611508aa7ff3c20a..084704c6d201ede2599d1753affc0db74d01ea48`
- risk-tier: internal
- spec: `docs/reference/protocol.md` HTTP PATCH/commit and persistence clauses; `sdk/README.md` HTTP submit/resume contract

## 踩坑

- I1 字节：`core/server/http_store.py` create 与 append 的 `os.open` 都加 `getattr(os, "O_BINARY", 0)`；POSIX 得到 0，保留原 flags。新增 `test_http_binary_payload_survives_append_recovery_and_commit_replay` 使用真实 SDK、listener、PATCH handler 和磁盘，记录 handler 交给 Store 的 bytes，并断言磁盘 bytes、长度、SHA-256。
- I2 恢复：该测试先确认 offset=7，再追加未确认物理尾；真实 listener/Store 关闭后在同端口重启，以同一 base URL 调 `resume_file_http`。断言恢复 PATCH 从 offset 7 开始且磁盘最终逐字节等于源文件。Store 的 `ftruncate(fd, confirmed)` 是恢复截尾点。
- I3 commit/保护：该测试重放 commit 断言 HTTP 200 与原 `job_id` 相同、DB 仅一条 job；原准入、并发和 Store 保护测试仍保留，diff 未删除旧 case。
- I4 判据：payload 含 NUL、LF、CRLF、0x1a 与高位字节；断言比较 handler 收到的实际 bytes 和最终磁盘内容，不是解析后计数。若在 Windows 执行，换行扩展会令字节、长度或 SHA 断言失败。

## 闸

- P2：回归目前没有 Windows 执行环境。`.github/workflows/ci.yml` 的测试 job 为 `ubuntu-latest`；POSIX 上 `os.O_BINARY` 不存在，回退值为 0，所以移除新增 flags 后这条 CI 测试仍不会因 Windows 文本模式换行扩展而失败。真实 Windows 下若回退到文本模式，PATCH 确认长度按输入字节增长、物理文件发生 LF→CRLF 扩展，commit 的物理长度/SHA 核验将返回 `422 integrity_mismatch`。这是测试漏检，不是本次源码仍有错误；失败可见，未定为 P1。Windows 部署上的真实触发频率未测。

## 偏差

- OCR：`reviewed`，profile `minimax`，coverage `complete`，findings 空；verifier `skipped`（total=0）。原始 JSON：`/tmp/caps-pr82-h2-review-ocr.json`。
- 仅运行任务卡要求的 `git diff --check`，未运行 pytest；不据此声称 Windows 回归或 M7 已完成。
- 派发时主干基线不可用（`gh api request failed`），继承红无法判定。pickup 无交接单；巡检 `orphan 0 / owned 0 / unattributable 0 / too-new 0 / recent-7d 0 / stale-over-7d 0 / missing_ledger_repos 0`；memory 探针报 `memory_dir_mismatch`。收件箱有 open issue #96（Windows 部署落后主干），未扩展审查范围。

## 最贵

- 尚未验证的是回归用例在真实 Windows CI/运行环境中执行；当前 Ubuntu 用例无法作为该平台的负控。源码 flags 与集成断言已具备，Windows 执行后才可证明此回归闸能拦住实际换行扩展。
