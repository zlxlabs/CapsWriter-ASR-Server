# H1 当前契约独立审查

- 审查对象：`e849c21748392ad848131e07ff17d32e4cc83a8b` → 固定对象 `ae03d04c7728b56c7baefd2309b44597f7f41155`。
- 范围：H1 的 `core/server/http_store.py`、`tests/test_http_file_tasks.py`；WS 旧断言只按已合并基线契约核验。
- 未运行测试、未 SSH、未安装；未读取实现者 report/progress。
- 结论：无 H1 当前运行时代码 P1/P2 缺陷。四个旧 WS 断言已由 e849 祖先 `d251618e` 正式废止，对应新测试在允许的两份 JUnit 中均为 PASS。不放行 Windows 原生验证、Ready 门禁或 M7。

failure-visibility: clean

## 当前运行时代码与 producer 边界

1. `ae03d04` 两处 `os.open` 均保留 main flags 并加 `getattr(os, "O_BINARY", 0)`：创建
   `core/server/http_store.py:591-601`，恢复/追加 `:657-671`。Windows 创建与重开走二进制模式，POSIX 原组合不变；源码审查不等于 Windows 实测。
2. 新测试 `tests/test_http_file_tasks.py:325-404` 约束真实 producer：SDK `:25-29`，
   `running_server` `:72-95` 启真实 aiohttp TCP；handler `core/server/http_server.py:520-545`
   把原始请求体交给 Store；Store `:632-686` 物理写入、按 offset 截断、fsync、提交 offset。
   断言物理 prefix、恢复后全字节、长度、SHA、SQLite offset/state/job。
3. `:334-345` 只在第二段确认前注入失败；未替换 listener/SDK/handler/Store/SQLite。
   `:371-379` 断言真实 PATCH bytes；`:381-404` 经 listener 重放同一 Job。
4. ElementTree 读既有 XML：`tests.test_http_file_tasks::test_http_binary_payload_survives_append_recovery_and_commit_replay`
   在 `pinned.xml`/`unpin.xml` 均为无子标记 PASS（time=0.109 / 0.149）。这锁的是该套件运行平台上的 producer 字节，不是 Windows 原生门禁。

## 四个旧断言的现行契约资格

已合并出处：`git merge-base --is-ancestor d251618e e849` 成立；`git log e849 --first-parent`
   记 `fix(ws): 加 I-owner 进展看门狗，修 #76`。该提交把 `docs/reference/protocol.md` 的旧
   `bad_request`/“背压暂停计时”/“主进程非零”改为 `decode_stalled`、I-owner 互斥看门狗和
   “只终结该任务”；e849 blame 在 `protocol.md:71-72, 151-160`。

JUnit 分类：`xml.etree.ElementTree` 按 `testcase@class/name` 取节点；无 `skipped|failure|error`
子元素记 PASS；已知 skip 负控三条命中 `skipped`；四个旧名负控为 absent。

| 旧测试（fce 源定义） | 旧要求 → 已批准新要求 | 当前实现/近似测试 | JUnit（pinned / unpin） |
|---|---|---|---|
| `test_upload_idle_returns_bad_request`（`tests/test_backpressure.py:277-288`） | 空闲报 `bad_request` → 无在途且超过上限报 `decode_stalled` | `process_manager.py:49-89`；S4 `tests/test_ws_progress_watchdog.py:343-386` | 旧名 absent；S4 PASS / PASS |
| `test_backpressure_pauses_upload_idle_timer`（`tests/test_backpressure.py:292-325`） | 背压推迟 idle → 任何状态不推迟判定；有 `pending_segments` 归段看门狗 | `ws_recv.py:169-179`、`process_manager.py:52-65`；`tests/test_protocol_v2.py:196-237` | 旧名 absent；替代 PASS / PASS |
| `test_segment_watchdog_errors_and_exits_main_nonzero`（`tests/test_error_contract.py:203-233`） | 段超时主进程非零 → 仅该任务 `inference_timeout`，服务存活 | `process_manager.py:209-231`；S5 `tests/test_ws_progress_watchdog.py:390-430` | 旧名 absent；S5 PASS / PASS |
| `test_compressed_consumer_backpressure_pauses_upload_idle`（`tests/test_protocol_v2.py:196-228`） | 压缩背压推迟 idle → 不刷新 `last_progress_at` | `state.py:402-440`；`tests/test_protocol_v2.py:196-237` | 旧名 absent；替代 PASS / PASS |

四项均为 **obsolete（契约已废止）**，且新版契约测试已在允许 XML 中 PASS。非同语义迁移。
PASS 不等于 Windows 原生字节验证，也不等于 M7。

## 踩到的坑

- 空 PASS 节点 `children=[]`，`bool(elem)` 为 False；若用元素真值或贪婪跨 `testcase` 正则，会把 PASS 误判成 skip/absent。负控：`test_aligner_loads_not_fallback` 等三条才是 skip。
- 旧名 absent 不能当作通过；废止来自 d251 协议 diff 与 e849 实现/替代断言。

## 闸与绕过

- 只读允许的 `pinned.xml`、`unpin.xml`；未重跑。`git diff --check` 清洁。未把 Linux PASS 说成 Windows 实测。

## 卡面偏差

- H1 固定 diff 另含 progress/native/posix/review1 文档；未读、不采信。H1 代码事实仍是两处 O_BINARY 与一条真实 SDK 测试。
- 协议变更属已合并 e849 祖先 d251，H1 未重做 HTTP/WS 协议。

## 最贵一步

用 ElementTree 对每个 `testcase` 单独分类并喂已知 skip/absent 负控，纠正先前把空 PASS 节点记成 skip 的证据错误。
