# Windows 普通文件传输与小命令分离：原生字节资格

本记录只谈源码字节在 Windows 上的红绿资格，不谈识别模型质量、CER 或生产服务。

结论：**blocked**。第一轮停在过严的父 Owner 字符串比较（观察保留，不洗）。第二轮已撤销该前提，在用户标准临时目录独占创建唯一目录并完成一次 SCP；负控在 `python -m pytest` 报 `No module named pytest` 处停止（setup，不是字节红）。未安装包、未换解释器、未跑正控。无本轮 JUnit。

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

## 第一轮红绿与基线

- 负控/正控均未启动。setup 闸，不是字节/offset/SHA 预期失败。
- 派发时主干 CI 基线不可用（`gh api request failed`）。继承红：未能判定。本卡新测试红：无（测试未跑）。
- `git diff --check` 对本文件清洁。源码与 tests 零改。

## 第二轮：撤销 Owner 相等后的 split 传输

主脑明确：Windows SYSTEM/Administrators 所有者不等于 Token 无写权限；不改 DACL/owner，不碰既有未知实验/生产目录，不因此调低权限。唯一目标在 `[IO.Path]::GetTempPath()` 下用任务前缀+GUID 独占创建（先核 absent，`New-Item` 无 `-Force`）。

- SSH#1 准备：EncodedCommand 1672 B，外层 rc=0，1.820 s。私回执含 principal SID 与 canonical path。未写原 prep 父目录。
- SCP 一次：两 gzip + 运行脚本，60 s 内，rc=0，2.119 s。argv 先自检；未改 `-O`。
- SSH#2 校验：EncodedCommand 640 B，rc=0，1.970 s。远端消费者读到负控 1505672 B / `6aae5a30…`、正控 1490937 B / `78c061ed…`，与本地 manifest 一致；已知坏 SHA/长度被同一 `require_match` 拒绝。
- SSH#3 负控：EncodedCommand 632 B，外层 rc=1，3.274 s。已解压；阶段 `pytest-base`；JUnit 文件不存在。等待期已打开 stdout/stderr 文件。
- SSH#4 只读（不重做测试）：EncodedCommand 1936 B，rc=0，1.819 s。工作目录在；JUnit 仍不在；stdout 0 B；stderr 97 B，文本为隔离 venv 的 `python.exe: No module named pytest`。
- 未跑 H1。无 child pytest JUnit。不安装 pytest，不换解释器，不把缺模块写成字节红。
- 源码与 tests 仍零改。本轮无新测试红（未形成字节断言失败）。继承红仍未能判定。
