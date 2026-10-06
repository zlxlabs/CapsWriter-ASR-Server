<!-- delegate-outcome: succeeded -->
failure-visibility: p2-only

# M6 H0..H1 四问专项增量审查

- 审查范围：`da81cacc13061be8a7693775ebca7e413a29a189..337689689c9b2a314548b70667e447841bf070ad`。
- 结论：本轮五条登记缺口都有对应代码和本机行为证据；未发现应用 P1。记录 1 条 P2 文档自相矛盾，不阻断本次增量审查。此结论不是 M6 整体完成证明。
- 旧登记只按 `03e8e48` verdict 的五条 findings 条款对照；不以旧测试报告或旧行为推理作证据。

## 四问

### 1. 本轮是否只修登记 findings：是

1. restart second 不再停止后重建另一套 WS harness：第二受管服务仍存活时直接调用 `_phase_legacy_ws`，见 `tests/test_http_qa_repeat_matrix.py:909`、`:988`、`:1033`。
2. DONE 回放比较重启前后完整 JSON 对象，`replay_again.json() == replay`，见 `tests/test_http_qa_repeat_matrix.py:880`、`:928`。
3. 源文件与实际落盘文件逐字节比较；跨 Queue 收到的真实 `Task.data` 逐段对独立 ffmpeg PCM oracle 比完整 SHA-256，见 `tests/test_http_qa_repeat_matrix.py:684`、`:695`、`:491`。
4. io-first 的 `pending`、mailbox 值与 slot 状态来自 handler 取消后的真实 worker 时点；字段值不再固定为 true，见 `tests/test_http_qa_repeat_matrix.py:719`、`:785`、`:834`。
5. 每轮从实际调用日志偏移切出新的 ffmpeg start 事件，并核对 shim 收到的 argv/env 标记，见 `tests/test_http_qa_repeat_matrix.py:1064`、`:1081`、`:1084`；消费器检查轮次偏移递增，见 `:237`。

新增 artifact 路径规则只补普通 pytest 的兼容入口：无 env 时使用 pytest 提供的 `tmp_path`；env 已设置时仍要求路径存在，见 `tests/test_http_qa_repeat_matrix.py:34`。CI workflow 运行和 importlib 消费步骤都显式设置同一目录，见 `.github/workflows/ci.yml:55`、`:63`、`:75`。

### 2. 有无未经批准抽象：无

`enable_ws` 是 managed test harness 的 opt-in；`published` 只跨子进程发布真实 WS 端口。`info_queue` 仍发送、仍按旧 `(http_port, worker_pid)` 二元组解包，见 `tests/harness/server.py:363`、`:373`、`:427`、`:457`。端口必须跨进程传回父测试才能建立真实客户端连接；保留旧 tuple 可兼容现有 harness 调用方。新增范围限于测试 harness，没有新增产品配置、API、通用 IPC 框架、线程资源层或多池机制。

### 3. 状态、事实与 fallback 是否有依据：有

- `http_source_bytes_match` 在字节相等断言后记录；PCM 字段在真实 worker Task 的完整摘要通过独立 ffmpeg 对照后记录。`Task.data` 摘要取自 worker 收到的对象本身（`tests/harness/worker.py:43`）。
- mailbox/pending 来自真实 handler 与 I/O worker；DONE 相等来自真实两次 `GET /result`；重启后 WS 字段在实际 frame 返回、同一 state 收到任务且 second 进程仍存活后记录。
- shim 日志记录真实子进程 argv、环境标记、PATH 首项，并执行实际 ffmpeg；矩阵只把当前轮新 start 计入工件（`tests/test_http_file_runner.py:112`、`tests/test_http_qa_repeat_matrix.py:1081`）。工件不写 argv、路径或媒体摘要。
- 普通无 artifact env 运行和带显式目录的裸环境运行均完成；CI/Bare 路径没有被 `tmp_path` 默认值代替。工件消费者读的是同一实际文件字节。
- 在 H1 临时 worktree 中把 `slot_held` 注入为错误的 true，保留真实 I/O producer、pending=0/mailbox=32，并把实际 phase 交给 trace consumer；消费者以 `AssertionError: round 1 io_first I/O 完成后槽位必须已归还` 失败。注入行已核实，失败不是 ImportError 或缺依赖。

### 4. 是否留下双路径或服务边界：重启路径闭合，生产入口未覆盖

| 相位 | 实际启动与状态 | 判断 |
|---|---|---|
| concurrency / cancel_io | 每轮一个 `running_runner_server` 上的真实 HTTP listener、`HttpFileRunner`、独立 recording worker、queue 与 SQLite store；两相位共用该实例 state 和 `tmp_path/httpdata`，结束后 teardown。WS 并发相位使用同 state 上的真实 `ws_recv`。 | 同一受管测试实例内的真实 HTTP/worker/WS 数据路径；cancel 屏障留在 I/O worker 所在进程边界。 |
| restart / legacy_ws | `ManagedHttpServerHarness` first 在同一 `data_dir` 受控 SIGTERM；second 重新打开同一 store，PID 改变，并由同一 child 启动真实 `HttpServer`、worker 与 opt-in `ws_recv`。`legacy_ws` 在 second 仍活着时收到 final frame；DONE 的重启前后完整 JSON 相等。 | first→second 是持久化根不变的逻辑服务重启；没有 `stop(second)` 后另起第三套 WS state。 |

完整矩阵跨两种既有 harness 形态，不是单个进程连续承载所有 phase；源码、HTTP listener、数据根与 SQLite store 一致。重启专用 fake engine 仅 first 配置 delay 以构造 RUNNING 状态，second 恢复普通 fake engine，因此该证据不代表真实模型配置或识别质量相同。

`CapsWriterServer.start/_serve_all` 与生产 `SocketManager.start` 未被调用；本轮只证明测试 harness 直接装配的真实 `HttpServer`、`HttpFileRunner`、`ws_recv` 和 worker。M6 QA 文档限定隔离服务与客户端/文件/进程边界、不访问生产端口/模型，因此不把生产入口当成本轮已测，也不以此单独判 M6 失败；生产启动编排仍是未验证边界。

## P2 记录

**P2-1：设计文档仍自相矛盾地禁止改 harness。** `m6-repeat-matrix-design.md:31` 保留“不改 harness”，而同文件新增 H1 段 `:61`、`:73` 明确说明给 `ManagedHttpServerHarness` 增加真实 WS listener；实际改动在 `tests/harness/server.py:363`、`:427`。任务卡已明确授权最小测试 harness 修改，代码属于本轮登记范围；这是文档边界过时，不是未经批准的代码抽象。本轮仅记录，不改其他文件。

## 验证与未覆盖项

- 普通无 artifact env：聚焦矩阵与旧 harness SIGTERM/重启用例 `12 passed`。
- 白名单 `env -i`，显式 artifact 目录：同一聚焦集合 `12 passed`；独立 importlib 消费器读到 rounds `[1,2,3,4,5]`、真实 io-first `pending=0/mailbox=32/slot_held=false`、五轮 restarted-instance WS 均为 true。受管 child 进程均以 PID、创建时间及 parent identity 采样后定向收尾；测试后无存活 child。
- scratch 行为负控：真实 io-first producer 错值被消费器以 AssertionError 拒绝；临时 worktree 已由 `scratch-worktree.sh` 清理。
- 按任务要求未跑全量 500+/依赖矩阵/真实模型/私有媒体/Windows/systemd；未重跑或读取 H1 Hosted CI artifact。Hosted CI 的 H1 五轮证据仍未知，不能据本地测试宣称 M6 最终完成。
- 主干基线：`gh api request failed`；继承红无法判定。本轮新正向验证无新红；scratch 负控的 AssertionError 是预期红。
- OCR：`skipped`（两次主腿调用在观察时段内无 stdout envelope，后一次于五分钟上限中断）；reason 为未产出 envelope/观察上限中断，coverage 与 verifier 均未知。没有把空输出当 clean。
