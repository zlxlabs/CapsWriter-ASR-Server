# Windows HTTP 字节完整性独立审查结论

failure-visibility: clean

## 结论

审查对象固定为 `492fe191e3f9568ea178b61970c732c9d37c4e29..9e0dd6db68e30c2d9c109705957845aca7d77f03`。本轮没有确认的 P1/P2 缺陷；Windows 原生行为、Linux 旧坏已确认前缀拒受、POSIX 保持性和跨边界测试约束均有独立证据。`reviewpass/fail` 与本次执行器完成状态正交，本 verdict 的状态为 clean。

## 输入与隔离

- 指定私输入只在进程内读取了 `windows` 字段的结构信息：文件存在且可读，5706 字节、0600、uid 1000；`windows.target_private` 为字符串、长度 14。没有回显或记录其值，也没有读取音频、token、主机地址、凭据或 profile。
- H0 源码归档来自完整项目提交 `9e0dd6db68e30c2d9c109705957845aca7d77f03`，本地与 Windows 消费端归档字节数均为 10178560 且 SHA-256 相等；源身份只以公开 Git SHA 记录，不在此文件写入归档或 producer hash 值。
- Windows 使用新建的任务临时树和已缓存的 Python 3.12.12；未改原 prep venv、系统 Python、PATH 或模型缓存。测试依赖实际版本为 pytest 9.1.1、pytest-asyncio 1.4.0、aiohttp 3.14.3、httpx 0.28.1、websockets 15.0.1。

## 源码全消费点审查

审查不是只看 diff：按 HTTP 源文件的创建、追加、恢复、校验、清理与读取调用点逐一核对。

- `core/server/http_store.py:591-599`：创建 source 的 `os.open` 使用 `O_CREAT|O_EXCL|O_RDWR|getattr(os, "O_BINARY", 0)`，创建后 `fsync`。
- `core/server/http_store.py:657-669`：PATCH 追加使用同一二进制 flag；先 `ftruncate(confirmed_offset)`，再 `lseek` 到确认位置，循环 `os.write`，最后 `fsync`。未确认物理尾不会被当作已确认内容。
- `core/server/http_store.py:688-701`：commit 前读取 source 使用 `"rb"`，独立核对完整物理长度和 SHA-256；长度或摘要不符时上抛 `integrity_mismatch`。
- `core/server/http_store.py:703-748`：幂等重放先返回原 Job；只有完整校验、准入和推理协调者检查通过后，才在事务内更新 upload 并插入唯一 Job，保持首次 202、重放 200 的语义。
- 其他相关调用点也逐一核对：`_ensure_private_file` 只创建/收紧 DB、WAL、SHM 空文件而不写 source 数据；锁文件使用 `"a+b"`；HTTP handler 以 bytes 读取请求体；SDK producer 以 `"rb"` 读取源文件；runner 只读取服务端已生成 source 路径。未发现第二个 source 数据写入路径。
- `getattr(os, "O_BINARY", 0)` 的缺失常量语义仅发生在 POSIX：值为 0，且 `os.write` 直接写文件描述符，不存在文本换行转换。Windows 原生环境提供该常量并实际使用；这不是业务重试、fallback 或静默吞错。

## 独立实证

### Windows H0 与反向红验

运行的是完整项目 conftest 下的指定用例：

`tests/test_http_file_tasks.py::test_http_binary_payload_survives_append_recovery_and_commit_replay`

- 基线 492 加入新用例后：`pytest_rc=1`，`1 failed`，失败类型为真实 `AssertionError`；无 ImportError、无 INTERNALERROR、无 SKIP。
- H0：`pytest_rc=0`，`1 passed`；无 ImportError、无 INTERNALERROR、无 SKIP。
- payload 由真实 HTTP `PATCH` producer 发送，覆盖 NUL、LF、CRLF、`0x1a` 和高位字节。用例实际核对磁盘 readback 与 producer 输入逐字节相等，并核对声明 offset/长度、SHA、首次 commit `202`、重放 `200` 和同一 `job_id`，数据库 Job 计数为 1。
- 额外在真实 HTTP 请求中注入 `os.open` 记录探针，确认两个 source 打开点真的被执行：基线 flags 为 `[1282, 2]`，随后在二进制 flag 断言处真实 `AssertionError`；H0 运行通过，且断言两个 source 打开均带 `O_BINARY`。因此基线红不是导入失败、skip 或未走到 source open。

### Linux 合成旧坏 confirmed prefix 反向输入

使用真实 aiohttp TCP listener、httpx 请求和实际 `HttpStore`：

- 先实际 PATCH 合法前缀，再把已确认前缀替换为同长度的旧 Windows 坏字节；之后实际 PATCH 合法 suffix，确认恢复路径仍按数据库 offset 工作。
- 对该旧坏 source 执行实际 commit：HTTP `422 integrity_mismatch`；upload 保持 `UPLOADING`，confirmed offset 为完整声明长度，Job 数为 0，result 数为 0。没有自动修复、截断历史前缀、重处理或伪造失败成功。
- 对同类合法 producer 输入执行完整上传：首次 commit `202`，重放 `200`，两次返回同一 Job；唯一 Job 数为 1。该对照验证了拒受判据不是恒真拒绝。

### OCR 前置扫描

- 固定范围：`492fe191e3f9568ea178b61970c732c9d37c4e29..9e0dd6db68e30c2d9c109705957845aca7d77f03`。
- background 摘要为 1026 字节，低于 8000 字节上限。
- stdout JSON envelope：`status=reviewed`、`profile=minimax`、`reason=primary_selected`、`cli_status=complete`、`coverage=complete`、`verify_status=completed`、`total=1`、`verified=1`、`confirmed=0`、`refuted=1`、`unverifiable=0`。
- OCR 唯一意见是低严重度的重复表达式/所谓缺失 `O_BINARY` fallback。独立核验确认重复表达式存在，但 fallback 前提错误：POSIX 的 0 是合法无 flag 语义，Windows 实测使用真实 `O_BINARY`，且底层是 `os.write`。该意见不构成 finding，不进入修复或 backlog。

## 其他验证与边界

- `git diff --check HEAD^ HEAD`：通过。
- 冻结范围 `git diff --check 492fe191e3f9568ea178b61970c732c9d37c4e29..9e0dd6db68e30c2d9c109705957845aca7d77f03`：通过。
- 未运行全量质量矩阵、真实识别质量、生产部署或模型重复准备；这些不影响本次字节持久化独立审查结论。
- 派发时主干基线查询不可用，因此没有把任何未核实的同名 CI 红归为新红或继承红；本次结论只依据上述可复现的源码和聚焦证据。
