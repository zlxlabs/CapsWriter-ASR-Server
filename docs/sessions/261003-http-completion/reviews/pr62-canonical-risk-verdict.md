# PR62 规范 finding 实测分诊 verdict

failure-visibility: p2-only

- 阶段：factual disposition preparation；不自签、不 rerun、不 merge、不改应用代码
- 审查对象冻结：H0 `c2818c5cba71ac86ddc0da1bee54538d34cdfe6b`；规范生产者基准 `b0818dc7859d1d8100e42f5c70cb75d34da422f7`
- 官方输入：audit-safe 对象 A，`size_bytes=11408`，SHA `fde59a980f9bdd07d8a9fe677dbe057dd459a0ed695029eb87fa482f38821c43`；producer repo `971940657` / run `37204722377` / att `1` / callee `6fd21e0ab5a27a279fe5cd15dd74edaa0b079fe9`；reviewer `codex-sub`；`executedModel` 原键缺，保持 unknown
- 风险等级：internal。外部 major 不因模型评级直接 P1
- spec：`docs/sessions/261001-http-files/design.md`、`qa.md`、`docs/sessions/261003-http-completion/m4-plan.md`
- 本卡不是第 4 个全量 cold review；只处置官方 5 条
- 私有证据（目录 0700 / 文件 600）：dispatch `dlg-20261004-170855-24eadd` 的 `evidence/`（不入库）
- 主干 CI 基线：派发时刻 `gh api` 失败，继承红未能判定

## 五条对照

| ID | 工具 severity / 精确前提 | 第一问：真实触发 | 第二问：后果 | 本仓 | 锁
|---|---|---|---|---|---|
| A1 | major；`cleanup_terminal_sources` 无 `conn.commit()`，**若 SQLite 仍处事务中**则 close/PermissionError 回滚，重开 UPLOADING、GET 非 410 | 实测触发了清理两条路径（正常 unlink + 真实 `PermissionError` errno 13）。前提「仍处事务中」不成立：`isolation_level=None`，UPDATE 后 `in_transaction=False`；独立只读连接在生产者未 close 时已读到 `EXPIRED` | 关闭/新进程重开 + 真实 HTTP GET 均为 410 `upload_expired`；partial SHA 保持；DONE/FAILED 合格源被 unlink、不合格源保留。假 ROLLBACK 生产者使「仍为 EXPIRED」断言变红 | **refuted**，非 P1 | `a1-persist.json` + `a1-refuted.json`；断言：独立连接 `state=EXPIRED`、close/reopen GET 410、partial SHA、假回滚变红 |
| A2 | minor；显式 `stop` 与 `serve` finally 并发，second 在 first 把 task 置 `None` 后绕过等待 cleanup | 真实 inflight：first 调度后 `_source_cleanup_task is None` 且 `_source_cleanup_inflight is True`；second 先返回，随后 first 返回；子进程 rc=0 | 无 `AttributeError`；SQLite 终态 `EXPIRED`；partial 仍在；worker/store 最终 None。可观测为抢先拆 listener，不是数据损坏 | **P2** 接受不修 | `a2-stop-reentry.json`；断言：两路 `stop` 都返回、rc=0、EXPIRED 仍在、无数据损坏 |
| A3 | minor；每小时 `fetchall` 全历史 DONE/FAILED，线性内存/worker 延迟 | 生产 HTTP 默认关闭：`CW_HTTP_DATA_DIR`/`CW_HTTP_PORT` 长度均为 0。本机发现的 `http.sqlite3` 为 pytest/tmp 残留，max jobs=9、max uploads=11。QA 文档规模：32 未完成上传 / HTTP 运行 1 | sandbox 8/32/128 行 cleanup 0.38ms / 0.49ms / 3.4ms，RSS 增量 ≤8KB。当前真实规模不可触发不可接受延迟。百万行未观测，不虚构 | **P3** 接受不修（未知生产百万行 ≠ P1） | `a3-scale.json`；断言：env 未配置、max jobs=9、128 行 cleanup <10ms |
| A4 | minor；naked `ProbeRun.start` 用 `env=dict(os.environ)`，与注释「只白名单」/`env -i` 证据不同 | 实际 `Popen(env=…)`：哨兵 `CW_PR62_SENTINEL` 继承为真，额外键 91，伪造敏感名也在 env 里。systemd 本沙箱无 user bus，该 launcher **unknown**，不读真环境值 | `httpx.AsyncClient(trust_env=False)`；探针 HTTP 不发送父进程环境。继承 ≠ 泄密。测试夹具，非生产 listener | **P3** 接受不修 | `a4-a5-probe.json`；断言：sentinel_in_popen_env=true、extra_key_count=91、trust_env=False。本树 `tests/` 与 `.github/` 无 `env -i` 字面量 |
| A5 | nit；`open`+`dup2` 后未 close 原 handle | 子进程 fd 4→5（delta=1）；`original_handle_still_open=true`；源码无 `handle.close` | 进程退出 OS 回收。仅探针生命周期 | **nit / P3** 接受不修 | `a4-a5-probe.json`；断言：delta=1 且原 fd 仍开，exit 回收 |

## A1 精确 claim 与 acceptance_basis

官方精确断言：过期上传在进程内看似 EXPIRED，重启后恢复 UPLOADING，GET 不返回约定 410；清理异常路径还可能丢掉 EXPIRED 持久化。条件句是「若 SQLite 仍处事务中」。

acceptance_basis（覆盖正常 + 失败 + 独立 close/reopen + 410/partial）：

- 路径 a：`HttpIoWorker.run_sync` 调真实 `cleanup_terminal_sources`；独立 sqlite 只读连接在生产者连接未 close 时读到 `EXPIRED`；合格 DONE/FAILED 源已 unlink，不合格源保留；close 后新进程 `get_upload` → `HttpStoreError(upload_expired, 410)`；新 `HttpServer` 真实 GET 410
- 路径 b：`HttpServer.serve` 周期清理遇到 owned 目录 `chmod 0555` 产生真实 `PermissionError` errno 13（非 root 假绿）；出错瞬间独立连接仍为 `EXPIRED` 且 `in_transaction=False`；listener fatal=`PermissionError`；close 后新进程 GET 410；partial 字节 SHA 不变
- 红验：scratch 假生产者 `BEGIN`+UPDATE+`ROLLBACK` 后独立连接仍为 `UPLOADING`，「EXPIRED 持久」断言变红，证明本次判据能识别反例
- 不以静态 autocommit 单独签反证；生产者 payload 是真实 SQLite 行与 HTTP 状态码

四字段反证：`evidence/a1-refuted.json`（`result=refuted`）。不翻新 finding 正文。无需 bounded 修代码。

schema 源 SHA（H0 `http_store.py`）：`23055c5cffd334762f19d7233bff8221ee3b973f7c4080d99fdb141eac035394`

## A2 时序

子进程 PID 登记后：cleanup inflight → 两个 `stop()`。second 先完成（0.35s）first 后完成（0.40s）。`serve` 收尾 `CancelledError`（任务取消，不是数据错误）。不把不同退出码或 DoubleStop 自动当成损坏。后果可接受，不新增协调状态/锁。

## 未知项（不把整体改成 skipped）

- A4 systemd launcher：本环境 `systemctl --user` 无 bus，未测 `--setenv` 白名单路径；naked 路径已测，该路径才是 finding 正文
- A3 生产 HTTP 文件库：本机未部署（配置键长度 0）；规模取 QA + 本机残留 max，不外推百万行
- `executedModel`：官方对象 A 缺键，保持 unknown

无 P1。A2 为唯一本仓 P2（接受不修）。不为 P2/P3/nit 加防御、状态、重试或新抽象。
