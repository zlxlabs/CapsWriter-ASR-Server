# HTTP fatal probe 最终独立审查

- 固定审查范围：`492fe191e3f9568ea178b61970c732c9d37c4e29..ec961294d02bae99e1b8f2a4d4baca233cd29ff4`
- Verdict：**PASS**；审查风险等级：`internal`。该等级描述本次审查工作，不代替代码 verdict。
failure-visibility: clean

## 审查范围与增量结论

- 完整范围仅有三份冻结文件：fatal probe fixture、cleanup 测试、contract progress 文档。
- `185035e4df95f7497e74d8dfd50f2b469cb6c3af..ec961294d02bae99e1b8f2a4d4baca233cd29ff4`：145 增、170 删。增量只收束 fatal 观察、user systemd 调用环境和相应负例，没有扩展到产品行为。
- 专项压缩 `7106df62a906f45eaaf9d13dc5b8493b04ab0ac2..ec961294d02bae99e1b8f2a4d4baca233cd29ff4`：48 增、92 删。删去单消费者 emit 包装并内联；负例改为表驱动，原 cleanup callback 身份断言仍在真实 worker 测试中。
- 原始 `492fe..7106df6` 履历为 450 增、41 删，共 491 行，超过当时 450 行预算 41 行；该历史未被改写。当前压缩增量为 140 行，完整 `492fe..ec961` 为 407 增、42 删，共 449 行，处于 450 行预算内。
- 四问：只修登记约束——是；新增无依据抽象——否；无依据状态、事实源或 fallback——否；留下并行实现路径——否。快照仅关联同一测试进程的 source/job；`_user_bus_env` 被预检、launcher、query、cleanup、log 多处消费。
- 相对 `492fe..ec961`，SDK、核心服务、工具、配置、CI 和脚本无改动；不涉及 Windows `O_BINARY` 修复。

## 关键不变式与证据

| 不变式 | 实现位置 | 锁定测试与结论 |
|---|---|---|
| observer 先调用原 `_mark_fatal` 写入 `self.fatal`，再同步写 JSONL、flush、fsync；worker 保存的 bound callback 可到达 observer，原 `_on_source_cleanup_done` 身份不变 | `tests/fixtures/http_fatal_exit_probe.py:93,147-179`；原方法 `core/server/http_server.py:296,383` | `tests/test_http_cleanup.py:1393-1405,1442-1461,1476-1508`；类 callback 身份、worker 早绑定及 same-turn 子进程文件写入均通过 |
| worker 与 cleanup-done 两来源使用独立 fresh server 和独立空 JSONL；消费端拒绝错误 phase/type/message/source/job、空文件与 only-pre 记录 | `tests/test_http_cleanup.py:1171-1184,1373-1390,1442-1508` | 两条真实 producer 路径各读自己的文件；主 fatal 路径从真实 JSONL 校验 source SHA 与 job。source 元信息缺省时保留 `null`，未伪造 snapshot |
| WAV → SDK HTTP → ffmpeg → multiprocessing/Manager → 真实 `TaskHandler` → SQLite DONE → 具体 source unlink denial → 父进程非零、子进程回收、端口关闭、源和结果保留 | `tests/fixtures/http_fatal_exit_probe.py:115-138,182-198,214-372`；`tests/harness/worker.py:92-125`；`core/server/app.py:142-177` | `tests/test_http_cleanup.py:1220-1289` 断言实际源 SHA/长度、result payload、DONE、非零退出、reap 与端口关闭。识别引擎是测试 stub，不作为 ASR 质量证据；重启后 DONE/result 可读由既有 `tests/test_http_supervision.py:577-620` 锁定 |
| `env -i` 调用方与 systemd 所有消费者使用同一 owner bus；show 通信错误失败；cleanup 仅凭真实 `LoadState=not-found` 接受回收 | `tests/test_http_cleanup.py:846-869,921-955,1042-1119,1513-1585` | user manager 测试真实执行 preflight/launch/query/stop/reset/log，并对去掉 bus 的 query 与 `LoadState=loaded` + “not loaded” 文本做负验；真实 user systemd 生命周期通过 |
| 修复局部留在测试边界，不改生产机制 | 三文件冻结范围；产品源文件差异为空 | 没有新增业务配置、线程、资源账本或 fallback；不改变旧 WS 路径 |

## 实测、OCR 与限制

- 唯一 cleanup 模块复验：`env -i` 启动、`uv --no-project`、Python 3.12、pytest 9.1.1、pytest-asyncio 1.4.0、aiohttp 3.14.3、httpx 0.28.1、websockets 15.0.1 及指定依赖；**19 collected / 19 passed / 0 skipped**。
- 生命周期四组分别为 `naked-shell` 4/4 passed、`systemd-unit` 4/4 passed。另有 predicate、same-turn、worker-bound、原 cleanup callback、user manager 和 loaded 错误负例，全部通过。ffmpeg 可用；真实同 owner user bus 预检退出码为 0。
- 裸环境外层仅传 4 个变量；uv 测试进程环境共 8 个键，`XDG_RUNTIME_DIR` 与 `DBUS_SESSION_BUS_ADDRESS` 值长均为 0。HTTP/WS 探针子进程分别使用 12/10 个白名单变量；systemd user bus helper 提供 2 个键。没有读取或报告环境原值。
- OCR wrapper 按固定 `492fe..ec961` 调用，但完整 envelope 是：`{"status":"skipped","profile":"minimax","model":"MiniMax-M3.1-Flash-Preview","reason":"no_reviewable_items","findings":[],"cli_status":"skipped","coverage":"none","verify":{"verify_status":"skipped","verifier":"none","concurrency":4,"counts":{"total":0,"verified":0,"confirmed":0,"refuted":0,"unverifiable":0,"unverified":0},"reason":"","budget_s":900.0,"finding_timeout_s":120.0},"attendance_ledger_write":"ok"}`。因此 OCR 未扫描，空 findings 不作为审查证据；人工完整审查未缩小范围。
- 固定 H0 scratch worktree 中，将真实 observer 改为保留原 fatal 写入但不 emit JSONL；实际 producer marker 记录 `PermissionError`，唯一被选中的消费者测试收集 1 项并以“没有观察到 post-fatal”断言失败。scratch worktree 已移除。包装脚本的收集行锚点误报退出 2；独立核对原始测试输出、断言和 marker 后确认预期红验成立，未重跑该测试。
- 主干同作业基线因派发时 GitHub API 不可用而缺失：继承红无法判定；本次唯一 cleanup 模块无新红。未跑完整测试套件或 hosted CI；未验证真实模型识别质量，这些不属于本次变更证明范围。
- 无独立 finding，故无 P1/P2 两问条目；OCR skipped、基线缺失和真实 ASR 质量均作为未证边界记录，不推断为通过。
