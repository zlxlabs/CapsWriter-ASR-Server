# Windows 普通文件传输与小命令分离：原生字节资格

本记录只谈源码字节在 Windows 上的红绿资格，不谈识别模型质量、CER 或生产服务。

结论：**blocked**。小 SSH 入口可达；按卡面「父目录存在且所有者等于当前交互账户」核完后停止。未创建新短期目录、未 SCP、未解压、未跑 pytest，因此没有本轮 JUnit，也不把 ACL 闸伪装成旧 Store 字节红。

## 本地源码身份（固定 Git object）

- 负控修订 `e849c21748392ad848131e07ff17d32e4cc83a8b`。`core/server/http_store.py` SHA-256 `23055c5cffd334762f19d7233bff8221ee3b973f7c4080d99fdb141eac035394`，不含 `getattr(os, "O_BINARY", 0)`。
- 正控修订 `ae03d04c7728b56c7baefd2309b44597f7f41155`（`git cat-file -t` 为 commit）。同路径 SHA-256 `afa25f1b6bbddc2f964b061d06c86429a61ec1e6b5aa9ce360b40dfde3126576`，含 `O_BINARY`。
- 单测文件 SHA-256 `ff10e53a08efa34d0159bf4e97a50f48bc0a56c196973734e8c3c27525c8ee86`，节点 `tests/test_http_file_tasks.py::test_http_binary_payload_survives_append_recovery_and_commit_replay`。
- 路径过滤：`core`、`sdk`、`tests`、`config_server.py`、`config_proxy.py`、`start_server.py`、`start_proxy.py`。负控包用正控整份测试文件覆盖基线同名文件。
- 重建 gzip：负控 1505672 B / SHA-256 `6aae5a30750631b3e46100009210b498d6fc8dc3a44af212fd2c7b7514c6b069`；正控 1490937 B / SHA-256 `78c061ed6f9068cfef9fe48660c56fd14489355d0dd7b5e5f40e1b8bf8c00d72`。与旧大 EncodedCommand+binary stdin 留下的 1505672 B 归档一致；该旧路径零 JUnit。卡面另引 135168 B 归档，本轮缓存未找到同长度活文件。

## 消费者边界（未发远端）

- 同一 `require_match(path, sha, length)`：好包接受；已知坏 SHA（64 个 `0`）且期望长度 1 被拒绝。拒绝来自实际读文件后的长度/哈希比较，不是两个字面量相比。
- 计划一次标准 SCP 同时复制上述两包 + 一个运行脚本，再用 ≤2KB EncodedCommand、无 binary stdin 指向已复制脚本。失败后不换 `-O` / legacy SCP / BASE64 / 别的协议。

## 实际 SSH（2/4，其后停止）

- SSH#1 准备：EncodedCommand 1892 B（≤2048），无 stdin，外层 rc=1，耗时 1.817 s。stdout 结构化 `parent_owner_mismatch`。未执行 `New-Item`。
- SSH#2 只读状态（失败后读已知目标，不重做有副作用操作）：EncodedCommand 1496 B，外层 rc=0，耗时 1.817 s。父存在且为目录；新短期名不存在；隔离 `venv/Scripts/python.exe` 存在；父 ACL 所有者为内置特权身份，当前账户为机器本地交互账户，二者不相等。用户配置目录所有者为 `NT AUTHORITY\SYSTEM`，同样不等于交互账户。
- 未 SCP，未 SSH#3/#4，无 child pytest rc，无 JUnit。

## 红绿与基线

- 负控/正控均未启动。setup 闸，不是字节/offset/SHA 预期失败。
- 派发时主干 CI 基线不可用（`gh api request failed`）。继承红：未能判定。本卡新测试红：无（测试未跑）。
- `git diff --check` 对本文件清洁。源码与 tests 零改。
