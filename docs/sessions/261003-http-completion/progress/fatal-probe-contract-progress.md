# fatal probe producer 契约：观察点移到真实 `_mark_fatal` 存储之后

- **Dispatch**：`dlg-20261005-051229-27db25`
- **Base**：`492fe191e3f9568ea178b61970c732c9d37c4e29`（runtime `core/` / SDK / collector 字节未改）
- **红提交**：`d1f063413d936ebb9ab827d60d5d328312bbaa14`
- **failure-visibility**：本卡测试/文档；不改旧 evidence / 原报告标记

## 现契约缺陷（可证）

`run_fatal_scenario` 在 `pre_fatal` 后用 `_wait_until(..., sleep 0.01)` 等 `http_server.fatal`，`except AssertionError: return`。consumer `test_fatal_cleanup_exits_process_and_reaps_children` 却强断言 JSONL `post_fatal` 为 `PermissionError` / `injected source unlink denial`。

全链路单次在本机 1.5s 内碰巧写出 `post_fatal`（exit=1，phases=`pre_fatal,post_fatal`），**不能**当成结构已锁。独立子进程把真实 `HttpServer._mark_fatal` 与 `loop.stop` 放进同一 `call_soon` turn：红阶段 JSONL 无 `post_fatal`，失败类是 `AssertionError`（不是 ImportError / 无 collector / TMPDIR 缺失）。

否定输入（空列表 / 仅 pre_fatal / `OSError` / 错 message / 缺 `fatal_type` / 错 source sha / 错 job_id）由 `_require_specific_unlink_fatal` 转红。

## 绿：最小观测移动

- class 包装 `HttpServer._mark_fatal`：原方法写入 `self.fatal` 后同步 `emit` JSONL；已有 fatal 再入只 `event.set`，不伪造成功。
- 同步包装 `_on_source_cleanup_done`，内部 `type(self)._mark_fatal(...)`，覆盖 I/O worker 构造期 bound callback 与 cleanup done 两条来源；实例晚绑不能冒覆盖 worker 已保存的 class 方法。
- `fatal` 模式在 `app.start()` / `prepare()` 之前安装包装；`same_turn_observer` 在构造 `HttpServer` 之前安装。
- 去掉 10ms 轮询与 `except AssertionError: return`。emit 失败 fail-loud。
- TERM / HTTP disabled / 装配失败断言无 `post_fatal`。

## 消费环境

| 项 | 事实 |
|---|---|
| UID | 1000 |
| `/run/user/UID` | 存在，目录 |
| bus 插座 | 存在、socket、属主 UID 相同；地址长度 28 |
| `XDG_RUNTIME_DIR` 长度 | 14（本 Cursor 会话缺省未设，测试 helper 按 UID 组装调用 env，不改 user bus） |
| `/bin/true` preflight | `systemd-run --user --wait --collect --service-type=exec` **returncode=0**，stdout/stderr 空 |
| `systemctl --user is-system-running` | exit 1，stdout=`degraded`（长度 8） |
| cleanup 模块 | 16 passed / 0 skipped；四 mode × naked+systemd 全跑 |
| systemd 具名 skip 资源 | `ffmpeg`、user systemd `/bin/true` preflight、`aiohttp` importorskip。本次 **0 skip**，不是用 skip 反推 systemd 跑过 |
| 本卡不 PR | 全套 CI 由主脑后续 PR；本机两套 pytest 见报告 |

Task09 pin 481+3+1、无效 TMPDIR 6fail、Task10 两 493 绿、Task11 skipped（`/bin/true` 未传 bus）不重开诊断。原报告 Env unknown 不拿新 env 回填。

## Unknowns

- 主干基线作业名：派发时刻 `gh api request failed`，继承红 **未能判定**。
- 本机 `is-system-running=degraded`：preflight 仍 0，四 mode unit 实测通过；不把 degraded 写成 running。
- transient `--collect` 后 unit 名不保留；pass 数按 pytest nodeid，不编造 journal 里的旧 unit。
