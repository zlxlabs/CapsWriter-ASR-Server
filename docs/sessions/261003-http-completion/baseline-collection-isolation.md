# 全量 collection、只执行两个 HTTP CLI 基线节点

记录日期：2026-10-05（UTC+8）。源码头 `946bc99860709e3908032667367a6f48a4e4bdef`。只新增本文；未改实现、测试、CI、原诊断文档或 PR82。

## 结论

在本隔离 worktree 用 `python -m pytest tests/` 做一次标准全量 collection，并用 `-k` 只执行两个 CLI 基线节点：`collected 503 / 501 deselected / 2 selected`，两节点均 PASSED，pytest rc=0。这只说明「导入全部测试模块后再跑这两例」在本臂可绿，不能据此断定 29 号全量红来自 fixture 顺序，也不能把观察器通过写成 funnel 绿。29 号 6aa/946 全量的 pytest stdout/tb 本体不在可读取现场，首因仍为 unknown；本卡停止，不再 full、不再加臂。

## 旧 producer 工件（只读指定根）

允许范围：29 号报告根 `20261005-101422-big-codex-http-windows-integrity-pr-delivery-261005`、补诊根 `…104704-resume-…038013`、以及 29 自有树 `http-windows-combo-failure-diagnosis-261005`。未灌入 provider 整段 stdout、`.env`、邻路径或系统扫描。

| 来源角色 | 两节点 | 行号 | 异常类型 | CLI returncode | stderr | resourceMissing / ImportError |
| --- | --- | --- | --- | --- | --- | --- |
| DLG29/report.md 全量表 | 两节点均列出 | 无 | AssertionError；FileNotFoundError | 未知 | 未知 | 无 |
| DLG29/codex-stdout.log | 仅叙述「断言 + FileNotFoundError」 | 无 pytest.tb | 同上 | 未知 | 未知 | 无 |
| WT29 `.pytest_cache` nodeids | 仅补诊两节点名 | 无 | 无失败缓存 | 无 | 无 | 无 |
| DLG038 报告 | 定向两节点通过 | 无旧全量帧 | 旧全量仍 unknown | 补诊当时 rc 0/1 | 补诊 stderr 类型 ValueError | 无 |

未发现 6aa/946 全量臂的 pytest 源 log 或 traceback 字节。不回填缺失工件。`--tb=line` 的旧 JUnit 只有类型，没有首因帧。不能用报告类别把「无首帧」说成已经定位。

## 本臂输入

cwd 为本隔离树根，HEAD `946bc99`。先 mkdir 自有 TMPDIR（实测目录模式 `775`）。`uv run --no-project --python 3.12`，pytest 9.1.1、pytest-asyncio 1.4.0、aiohttp 3.14.3、httpx 0.28.1、websockets **15.0.1**、numpy 2.5.3、rich 15.0.0、colorama 0.4.6、soundfile 0.14.0。标准 `tests/conftest.py`，无 `--noconftest`，无 skip，无依赖重装。入口是 `python -m pytest tests/ -k 'test_cli_http_producer_payload_and_private_json_bytes or test_empty_reference_fails_loudly_before_health_or_upload'`，另 `-p` 加载仓外观察器插件；不是 `pytest.main()`，与 038013 的 python -c 入口不同。

派发 unit `delegate-dlg-20261005-111651-8addce.service`：TasksCurrent=61、TasksMax=1024，MemoryCurrent=457904128、MemoryMax=8589934592。本臂无 child 资源错误类别，不据此猜配额。

## 真实 child（wrap 原方法）

观察器转发 `asyncio.create_subprocess_exec` / `communicate` / `returncode`，两次都调用了原方法（`create_called=true`，`real_create_preserved=true`）。未 patch CLI、未模拟 HTTP 成功。解释器与 `sys.executable` 相同；CLI 模块角色为 worktree `scripts/_baseline_http_ws.py`；cwd 未单独传入，角色为 worktree_root。loopback 只记测试服务角色，不记地址。

1. producer 节点：argv 含 protocol/server/health/wav/fixture/sha/model/private/reference/status/timeout；`env` 显式传入；CW_MODEL_TYPE 长度 27、M7_BASELINE_TEST_SENTINEL 长度 20。child rc=0，stderr 0 字节，stdout JSON `schema_version=1`、顶层 17 字段、`producer_payloads` 11 字段。private_dir 存在、权限 `700`、1 个 json。pytest PASSED。
2. 空参考稿节点：无显式 `env`；child rc=1，stdout 0 字节，stderr 45 字节，`BASELINE_FAILED` JSON，`error_type=ValueError`，无 error_code。private_dir 存在、权限 `700`、条目 0。与源码 `_run` 先 `_private_dir`（`scripts/_baseline_http_ws.py` 456–458）再空归一化抛 ValueError（466–467）、health 在 468 行之后一致。pytest PASSED。

本臂 PYTHONPATH 长度 122（观察器目录）、VIRTUAL_ENV 长度 40（uv 运行时）。29 号全量臂记录这两项未设置。本臂仍绿，不能用这项差异解释旧全量红，也不能把观察器绿当成原 funnel 绿。

## collection 前后真正变化

白名单键长度在 configure / collection_finish / sessionfinish 不变：PATH 498，PYTHONPATH 122，TMPDIR 129，XDG_RUNTIME_DIR 14，DBUS_SESSION_BUS_ADDRESS 28，VIRTUAL_ENV 40；CW_* 与 token 键 absent。解释器 3.12.3，cwd 始终 worktree_root。

变化在导入身份：`sys.modules` 620→854；collection 后 `_baseline_http_ws` 已加载且文件就是本树 CLI；`capswriter_asr.http_client` 来自本树 `sdk/`。`sys.path` 在 collection 中被多个测试模块 import 期 `sys.path.insert` 反复插入 `scripts/` 与 `sdk/`（静态消费者包括 `tests/test_http_baseline.py:20-21`、`test_http_file_tasks.py`、`test_http_qa_e2e.py`、`test_http_file_runner.py`、`test_http_client.py`、`test_e2e_sdk_server.py`、`test_sdk_client.py` 等）。环境键没有随之变。该副作用在「只执行两节点」下没有让两例失败。

## 决策表（一次判定）

**全 collection、执行 2、两例通过。** 可缩小的是「仅因 collection 导入全局状态就必然红」；不能自己断定 fixture 顺序，也不能把未执行的其余 501 例运行时资源/调用上下文排除。本臂没有失败行。29 号全量只留下异常类型，没有 CLI rc、stderr 类型或首帧，故旧 AssertionError / FileNotFoundError 的测试行不能从物理证据指认（候选消费者仍是 `tests/test_http_baseline.py` 257 行 returncode 断言或其后 payload 断言，以及 361 行 `private_dir.iterdir` 在目录不存在时的 FileNotFoundError，但均未在原 stdout 上核到）。最少欠缺的下一 producer 帧：那次全量失败当时的异常函数/行号、CLI rc、stderr 错误类型、private_dir 是否存在。本任务停止。不新增防御式 try/catch、重试或环境钳制。
