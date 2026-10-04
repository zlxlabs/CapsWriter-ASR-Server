<!-- delegate-outcome: succeeded -->
failure-visibility: p1-found

# C2 修后第二独立冷审：初判

审查范围固定为 `820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..e2fa535d1daa03a1491084a749d0c6e2aa2e1c55`；只读 M4 设计、服务端源码与新增测试。初判提交后再做外部消费验证；不读取旧 review/verdict、作者报告/进度/证据或 Task06/09 推理。

## 初判

### P1 候选：HTTP 存储启动异常可能遗留 I/O 线程，阻止 fatal 进程退出

违反本卡启动失败清理不变式：启动期装配异常须先回收已创建资源，再真实非零退出。

- 代码路径：`CapsWriterServer.start()` 把 `HttpServer(...).prepare()` 的返回值赋给 `self.http_server`；赋值要等 `prepare()` 完整返回。`HttpServer.prepare()` 在创建 `HttpIoWorker` 后同步执行 `HttpStore.open()`，仅对 `HttpStoreError`、`OSError`、`RuntimeError` 关闭 worker。`HttpStore.open()` 对 SQLite 连接和 PRAGMA 的其他数据库异常可原样上抛。
- 异常结果：若 SQLite 文件导致 `sqlite3.DatabaseError`，`start()` 的新 fatal 分支会调用 `_drain_after_fatal()`，但 `self.http_server` 仍为 `None`，因此 drain 无法关闭已经启动的 `ThreadPoolExecutor` 工作线程。该线程池线程是进程退出的存活资源。
- 初步判断真实触发：HTTP 服务启动时读取其本地 SQLite 文件；损坏数据库是可达的存储失败输入。若线程确实遗留，监督看见的会是端口关闭但进程不退出，不能接受。
- 仍需验证：用私有临时目录中的真实畸形 SQLite 文件运行实际启动 producer，记录真实异常、I/O 线程与进程退出；确认该条件下的具体行为后定级。

## 尚未判断

- Manager 创建之前/之后的启动失败与真实 PID 回收。
- listener 运行 fatal、SIGTERM 以及二者交错时 shutdown future、HTTP callback、父异常与真实 exit 的先后。
- HTTP disabled 路径与所有已完成/在途 I/O callback 的组合。
- 新测试对关键生命周期断言的反向约束力，以及本地裸 shell/systemd 实际消费结果。

本文件是冷审初判记录，最终结论会在后续提交中补齐证据、未知项与完整 verdict。
