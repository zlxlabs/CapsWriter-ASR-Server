# POSIX HTTP 二进制存储独立审查 verdict

- **Verdict：pass；未发现本次冻结 diff 新引入的 finding。** 审查固定于 `492fe191e3f9568ea178b61970c732c9d37c4e29..9e0dd6db68e30c2d9c109705957845aca7d77f03`，`risk-tier: internal`。
- 冻结范围的源码/测试变更只有 `core/server/http_store.py` 的 create 与 append 两处 `O_BINARY`，以及 `tests/test_http_file_tasks.py::test_http_binary_payload_survives_append_recovery_and_commit_replay`；progress 文件仅为提交物，未用作原因链。
- POSIX 真入口探针走 `CapsWriterServer.start()` → `HttpServer`/`HttpIoWorker`/`HttpStore` → `HttpFileRunner`/真实 `FileSourceDecoder`/ffmpeg → multiprocessing `TaskHandler` → SQLite/result → SDK 新客户端。只 stub 了模型检查与 ASR 引擎；真实 `CapsWriterServer.start()`、`ProcessManager`、`multiprocessing.Manager`、worker 进程、队列、HTTP listener、ffmpeg 与 SDK 都实际运行。
- 探针以 SDK 上传含 LF、高位字节且非全零的 16,044 字节 WAV；实际 PATCH wire body、服务端源文件字节和 SHA 完全相同。独立 ffmpeg oracle 为 32,000 字节 PCM，worker 跨进程收到的 `Task.data` 与 oracle 逐字节相同。commit replay 返回原 Job，新 SDK client 取回 DONE result；ASR 调用计数仍为 1。该 fake-engine observer 不代表 ASR 识别质量。
- 运行时观测到 POSIX `O_BINARY=0`，create/append 实际 flags 分别为 `194`（`O_CREAT|O_EXCL|O_RDWR`）与 `2`（`O_RDWR`），与改动前 POSIX flags 相同；create mode 与源文件、锁、SQLite 文件权限均为 `0600`。所有源文件 `os.open` 在同一个 `http-io_0` worker 线程。`_verify_source` 仍以 `rb` 读并核对真实长度/SHA；append 的 truncate/seek/write/fsync → SQLite offset → ACK 顺序未变。
- SDK 真上传后分别注入「源文件长度多 1 字节」和「长度相同但内容/SHA 不符」；两者均收到 `422 integrity_mismatch`。上传仍是 `UPLOADING`、offset/声明长度不被重写、SDK 只发一次 create/PATCH/commit，SQLite 未为坏源新增 Job/result。资源证据：源声明预留超限被拒且不新增 upload 行；result/WAL reservation commit 失败时真实 Job 数维持 `2`；物理余量 commit 拒收时 Job 数为 `0`，等值放行后为 `1`。
- 正常停机探针只跟踪自己的 server/worker/Manager PID 与启动身份；三者运行中均匹配，SIGTERM 后均消失，HTTP/WS 端口均释放，SQLite DONE/result 与源文件仍在。资源测试使用缩小常量验证阈值与拒收顺序；未做 1 GiB/16 GiB/2 GiB 真实体量压测。
- 已知答案为“否”的变异验证在 `scripts/git/scratch-worktree.sh` 创建的 H0 临时树中进行：将 append 的 LF 扩展为 CRLF 后，新增测试在实际磁盘字节断言处失败；基准未变异运行通过。临时树已从 worktree 注册表移除，主工作树未改源码/test/CI。
- OCR：`status=reviewed_fallback`、`coverage=complete`、`findings=[]`、`cli_status=complete`；主腿失败原因未分类，deepseek 备用腿完成审查；finding verifier 为 `skipped` 且总 finding 数为 0。OCR 不替代本次人工源码与运行时审查。
- 未验证：真实模型/真实音频质量、跨 ffmpeg 版本差异、真实部署磁盘上限压力。本审查未重跑 Windows CRT 或整套测试。派发时主干基线不可用（`gh api request failed`），继承红未能判定。

failure-visibility: clean
