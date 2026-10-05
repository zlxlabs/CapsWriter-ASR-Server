# Windows HTTP 源字节持久化独立审查

failure-visibility: skipped

## 审查对象与结论

- 风险等级：internal。
- 固定范围：`492fe191e3f9568ea178b61970c732c9d37c4e29..9e0dd6db68e30c2d9c109705957845aca7d77f03`；H0 固定为 `9e0dd6db68e30c2d9c109705957845aca7d77f03`。
- 全量审了三项差异：`core/server/http_store.py`、`tests/test_http_file_tasks.py` 与新增的 `progress/windows-http-integrity-fix-progress.md`。进度文档中的历史运行叙述没有作为本轮原因链或验证证据。
- 源码变更仅在新建与续写源文件的两个 `os.open` 调用加入 `O_BINARY`；在 POSIX 上取 0，在 Windows 上取平台定义的二进制位。未改变权限、截断位置、写入顺序、fsync、SQLite offset、长度/SHA 校验或 commit 幂等语义；没有新增状态、配置、重试或业务 fallback。
- 代码路径与新增 HTTP 用例在 Linux 上符合 R3/R5 的原字节、可信 offset、截断未确认尾、fsync 后 ACK、完整长度/SHA 与唯一 Job 契约。当前没有从源码或 Linux 用例确认的 P1/P2 行为缺陷。
- 本轮不能给 `clean`：指定的 Windows 私有上下文文件不存在，未能进行原生 Windows H0 红绿、492 基线反向红与移除二进制位的反向注入。尤其 Windows 的 `O_BINARY` 行为没有在消费平台实测，故本结论为 `skipped`，不是通过。

## 不变式与代码/测试落点

- 源文件写入点在 `http_store.py:591` 与 `http_store.py:658`；写入序列在 `:661-668` 先按数据库 `confirmed_offset` 截断，再 seek、循环写入、fsync，随后才条件更新并提交 SQLite offset。HTTP PATCH route 在 store 返回后才以 204 和新 `Upload-Offset` ACK（`http_server.py:443-469`、`:520-544`）。
- 首次上传先以 `O_EXCL` 建立空源文件并 fsync（`http_store.py:589-606`）。权限初始化 `_ensure_private_file` 只用于 POSIX 下的 SQLite/WAL/SHM（`:171-177`、`:243-246`），不是源字节写入点；独占锁用 `open(..., "a+b")`，本身已是二进制模式（`:185-192`）。源校验读取为 `open(..., "rb")`（`:688-700`）。
- commit 先识别已有 Job 重放，再要求 offset 达到声明长度、核对物理长度和 SHA 后建立 Job（`http_store.py:714-735`）；源路径由服务端生成的 `source_name` 构成（`:357-359`、`:832-844`），runner 将该路径交给 `FileSourceDecoder`（`http_file_runner.py:450-495`）。差异没有改动这些边界，也没有自动修复已确认前缀或放宽完整性条件。
- 新增用例 `test_http_binary_payload_survives_append_recovery_and_commit_replay`（`test_http_file_tasks.py:324-392`）走真实 aiohttp listener 和 HTTPX 请求，合成字节含 LF、CRLF、NUL、`0x1a` 与高位字节；断言首段 ACK 与磁盘前缀、未确认尾恢复后的完整磁盘字节、源 SHA、offset/声明长度、202/200 同一 Job 与单 Job 行。该用例发送原始 PATCH body，不是 SDK `submit_file_http` 调用；既有 `test_real_sdk_upload_bytes_match_server_disk_sha`（`test_http_qa_e2e.py:378-452`）锁 SDK producer 到磁盘字节，runner 用例 `test_real_container_upload_then_other_connection_takes_done_result`（`test_http_file_runner.py:341`）锁实际 FFmpeg argv 指向存储源文件，丢失 commit 响应用例 `test_lost_commit_response_recovers_with_exactly_one_recognition`（`test_http_qa_e2e.py:495`）锁一次解码和一个 Job。这些 Linux 用例不替代本次要求的原生 Windows 对照。
- 相关契约：`design.md` §R3/§R5，`qa.md` 第 1、3、4 组，`protocol.md` HTTP PATCH 与持久化提交顺序，`http-baseline.md` 的 producer/字节计量边界。新增进度文件仅按变更文档审阅，其自述没有被采纳为本轮 Windows 证据。

## 运行证据与未达项

- OCR 前置扫描状态：`reviewed_fallback`，备用腿覆盖完整、finding 为空；主腿 reason 为 `primary_failed_unclassified`。envelope 中 verifier 为 `skipped`、`verified=0`，所以只作为 OCR 扫描记录，不当作独立验证或无缺陷证明。背景摘要为 1,494 字节；完整 JSON envelope 和 reason 保存在本派发完整报告中，临时副本为 `/tmp/capswriter-http-windows-review1-ocr.json`。
- Linux CI 标准裸环境命令使用 `uv run --no-project --python 3.12`，pytest 9.1.1、pytest-asyncio 1.4.0、aiohttp 3.14.3、httpx 0.28.1、websockets 15.0.1，以及 numpy/rich/colorama/soundfile；用 `env -i` 显式提供 HOME、PATH 与 uv 缓存定位变量，未禁用项目 conftest。实际 Python 3.12.3、`os.name=posix`、`O_BINARY` 不存在。`tests/test_http_file_tasks.py -q -rs -p no:cacheprovider`：33 passed、0 skipped、1 条 aiohttp `NotAppKeyWarning`，44.59 秒。
- 当前节点 `systemctl is-system-running` 返回 `degraded`（查询退出码 1）；本文件用例没有 systemd 依赖或 skip。Linux 测试通过不代表 Windows 文件模式通过，也不证明 ASR 质量、2 GiB 峰值或生产无风险。
- Windows 原生上下文的指定 `private-context.json` 在给定位置缺失；因此没有 SSH 到 Windows、没有创建 Windows 实验目录或子进程，也没有可保存的 Windows Python runtime/argv/flag、PID/ctime/parent 或物理 readback artifact。没有用 `--noconftest`、系统 Python、模拟 OS 名称或 POSIX 结果冒充原生证据。492 基线仅拷新用例的 Windows 红验与移除二进制位后的新用例红验均未执行；POSIX 上 `O_BINARY` 缺失，Linux 基线绿不能作为负控。
- 派发时主干基线查询不可用，继承红与新红不能按同名 CI 步骤比较；本轮没有运行 Gate。继承红标记为“未能判定”。
