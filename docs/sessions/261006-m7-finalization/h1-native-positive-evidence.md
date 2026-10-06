# Windows 固定 H1 原生字节正控

<!-- 本文件只证明 remote 现存 H1 `ae03d04c7728b56c7baefd2309b44597f7f41155` 在已准备 Windows 环境上的唯一节点原生字节资格。不是 latest 合并资格、不是 Ready、不是 M7、不是 CI/gate、不是模型/质量/CPU/RSS。主干已变，后续仍需新组合正常准入。 -->

## 范围与对象

- 测试对象：只读 H1 源 `windows-h1.tar.gz` / revision `ae03d04c7728b56c7baefd2309b44597f7f41155`，cwd 为 H1 完整源 `source-h1/src`，不是 bootstrap 后的新 main。
- 对照旧 base：`e849c21748392ad848131e07ff17d32e4cc83a8b` 已在先前收据留下真实字节红（JUnit 1/1/0/0），prefix 期望 `00410a420d0a43`（7B）对实际 `00410d0a420d0d0a43`（9B）。
- 节点：`tests/test_http_file_tasks.py::test_http_binary_payload_survives_append_recovery_and_commit_replay`
- 测试文件 SHA-256：`ff10e53a08efa34d0159bf4e97a50f48bc0a56c196973734e8c3c27525c8ee86`（与 `git show ae03d04:tests/test_http_file_tasks.py | sha256sum` 一致；当前 worktree HEAD 该文件不同，未用来跑 H1）。
- H1 runtime manifest SHA-256：`e091ae99d63835d292fa2a280acbd4cf52f32d44eac01eb9ff81e5d07e0c65df`（286 files / 6567513 bytes），live `Get-FileHash` 与预检 identity 对齐后才启动 pytest。
- 未改产品 / SDK / tests / requirements / CI / 旧文档 / 环境 / ACL。未复用「base 非零就 exit 42」的 private runner。

## 实际 argv 与运行时

- 解释器：现成 venv `python.exe` 3.11.7；直接 `& python.exe -m pytest`，cwd=`source-h1/src`。
- 实测包装：pytest 9.1.1、pytest-asyncio 1.4.0、aiohttp 3.14.3、httpx 0.28.1、websockets 17.2、numpy 2.4.6（预检 import / 精确 node collect / `127.0.0.1` listener 已通过，本卡未重装）。
- 标志：`-q -rs -p no:cacheprovider --basetemp=<本任务唯一dir>/t --junitxml=<本任务唯一dir>/j.xml`。
- 外层 SSH 240s；pytest 墙钟 1.83s；SSH 往返 4.775s；`timed_out=false`。
- 不拿 SSH exit 0 代替 pytest 0：以 JUnit 文件与 pytest 摘要为消费者。

## 正控结果（真实消费者）

- JUnit：`tests=1 failures=0 errors=0 skipped=0`；testcase 名即上列节点；文件 382 bytes，SHA-256 `a28b071ec0c98e434ebac52bc375c95dd41943c2e58426b0a571b4dc62e8b219`。
- pytest 摘要（PowerShell 重定向为 UTF-16LE）：`1 passed in 1.83s` / `[100%]`；stderr 落盘 0 字节。
- 物理字节（basetemp 下 Windows 长路径截断目录 `test_http_binary_payload_survi0`，不是模拟 byte）：
  - `producer.bin` 41B SHA-256 `fed216220873ce83754f97f30927aa89ad37a4fc391ef590ae9c1e1188de721b`
  - `httpdata/sources/*.bin` 41B，同一 SHA，`physical_matches_source=true`
  - `resume.json` `confirmed_offset=41` `size_bytes=41`
  - sqlite `uploads`：1 行 `state=COMMITTED` `confirmed_offset=41` `size_bytes=41` `sha256` 与 source 相同；`jobs` 行数 1
- 与已证 base pair：H1 源前缀仍以 `00410a420d0a43` 开头（LF），base 红是同一 payload 被写成 `00410d0a420d0d0a43`（CRLF 扩展）。H1 全量 41B 与落盘一致，不再在 confirmed prefix 处分叉。

## 明确不是什么

- noReady / 无源码 PR / 无 Merge / 无 M7 / 无生产。派发时刻主干基线 `gh api` 失败，继承红未能判定。
- `git diff --check` 在写本文件前为 0；`git cat-file -t ae03d04c7728b56c7baefd2309b44597f7f41155` 为 `commit`。
