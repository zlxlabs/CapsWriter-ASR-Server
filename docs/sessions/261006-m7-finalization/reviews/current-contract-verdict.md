# H1 当前契约独立审查

- 审查对象：`e849c21748392ad848131e07ff17d32e4cc83a8b` → 固定对象 `ae03d04c7728b56c7baefd2309b44597f7f41155`。
- 范围：H1 的 `core/server/http_store.py`、`tests/test_http_file_tasks.py`；WS 旧断言只按已合并基线契约核验。
- 未运行测试、未 SSH、未安装；未读取 H1 的 progress/report/原 verdict 文件。
- `failure-visibility: na`
- `delegate-outcome: completed`
- 结论：无 H1 当前运行时代码 P1/P2 缺陷；四个旧 WS 断言已由 e849 中祖先提交 `d251618e` 正式废止。H1 真实 producer 证据因两份允许的 JUnit 均为 `skip` 而保持 unknown；不放行 Windows 原生验证、Ready 门禁或 M7。

## 当前运行时代码与 producer 边界

1. `ae03d04` 的两处 `os.open` 均保留 main flags 并加入 `getattr(os, "O_BINARY", 0)`：创建
   `core/server/http_store.py:591-601`，恢复/追加 `:657-671`。因此 Windows 的创建和重新打开都走二进制模式，POSIX 上原组合不变；未声称已在 Windows 执行。
2. 新测试 `tests/test_http_file_tasks.py:325-404` 的 producer 链真实成立：SDK 导入在 `:25-29`，
   `running_server` 在 `:72-95` 启真实 aiohttp TCP listener；handler 在
   `core/server/http_server.py:520-545` 把原始请求体交给 Store，Store 在
   `core/server/http_store.py:632-686` 物理写入、截断、fsync、提交 offset。测试直接断言
   物理 prefix、恢复后的全字节、长度、SHA、SQLite offset/state/job。
3. `server._store.append_bytes` 的 `:334-345` 只是第二段前的故障注入；没有替换 listener、
   SDK、HTTP handler、Store 或 SQLite。`patches` 在 `:371-379` 断言真实 handler 交给 Store
   的 payload，故不是同进程 mock 假绿。commit replay 通过真实 listener 的 `httpx` 请求
   `:381-404` 验证同一 Job。
4. 风险/未决：`test_http_binary_payload_survives_append_recovery_and_commit_replay` 在
   `pinned.xml` 与 `unpin.xml` 都是 `skip`，所以“producer 事实”不能写成 PASS；这属于证据
   缺口，不是已证实的运行时错误。

## 四个旧断言的现行契约资格

已合并出处：`d251618e` 是 e849 的祖先；`git log e849 --first-parent` 记录
`fix(ws): 加 I-owner 进展看门狗，修 #76`。其 diff 正式把
`docs/reference/protocol.md` 的旧 `bad_request`/“背压暂停计时”/“主进程非零”改为
`decode_stalled`、I-owner 互斥看门狗和“只终结该任务”；e849 当前 blame 落在
`protocol.md:71-72, 151-160`。

| 旧测试（fce 源定义） | 旧要求 → 已批准新要求 | 当前实现/近似测试 | JUnit（pinned / unpin） |
|---|---|---|---|
| `test_upload_idle_returns_bad_request`（`tests/test_backpressure.py:277-288`） | 空闲报 `bad_request` → 无在途且超过上限报 `decode_stalled`，连接/解码器回收 | `process_manager.py:49-89`；S4 `tests/test_ws_progress_watchdog.py:343-386` | absent / absent；S4 `pass / pass` |
| `test_backpressure_pauses_upload_idle_timer`（`tests/test_backpressure.py:292-325`） | 背压暂停/推迟 idle 计时 → 任何状态不推迟判定；有 `pending_segments` 时由段看门狗负责 | `ws_recv.py:169-179`、`process_manager.py:52-65`；`tests/test_protocol_v2.py:196-237` | absent / absent；替代测试 `skip / skip` |
| `test_segment_watchdog_errors_and_exits_main_nonzero`（`tests/test_error_contract.py:203-233`） | 段超时令主进程非零退出 → 仅该任务 `inference_timeout`，服务保持存活 | `process_manager.py:209-231`；S5 `tests/test_ws_progress_watchdog.py:390-430` | absent / absent；S5 `pass / pass` |
| `test_compressed_consumer_backpressure_pauses_upload_idle`（`tests/test_protocol_v2.py:196-228`） | 压缩背压可推迟 idle → 不刷新 `last_progress_at`、不延长任何截止时间 | `state.py:402-440`；`tests/test_protocol_v2.py:196-237` | absent / absent；替代测试 `skip / skip` |

因此四项均为 **obsolete（契约已废止）**，不是要求当前实现恢复旧行为；但替代测试的
`skip` 不能冒充真实 PASS，尤其不能推出 Windows 字节行为或 M7 已完成。

## 踩到的坑

- 当前 checkout 基线是 e849，而 H1 必须从固定 object `ae03d04` 读；没有把工作树状态误当 H1。
- JUnit 中“旧 testcase 不存在”只作为身份事实，未把测试删除当成通过依据；废止结论来自
  `d251618e` 的协议 diff、git log/blame 与 e849 的实现/替代断言。

## 闸与绕过

- 仅读取允许的 `pinned.xml`、`unpin.xml`；没有重跑测试。`git diff --check` 和固定对象
  `git diff --name-only` 已执行；固定范围无 whitespace 错误。
- 没有绕过 skip，也没有以 Linux 的 `getattr(..., 0)` 结果替代 Windows 原生字节证据。

## 卡面偏差

- H1 固定 diff 还包含 progress/native-verdict/posix-verdict/review1-verdict 四个文档对象；
  按卡面边界未读取、不将其自述当证据。产品相关 H1 代码事实仅为上述两处 O_BINARY 和一条
  真实 SDK 测试。
- `docs/reference/protocol.md` 的正式变更属于已合并 e849 祖先 d251，不把 H1 误写成重做 WS。

## 最贵一步

最贵的是逐项把 fce 的四个旧断言与 d251 的已合并协议 diff、e849 blame、当前实现和两份
JUnit testcase 身份对齐；结果是“契约废止”与“替代证据 skip”两条结论同时成立，不能合并成
“旧测试删掉所以通过”。
