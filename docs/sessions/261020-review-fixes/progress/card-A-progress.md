# 卡 A 进度存档

## 2026-10-20 复现红态并落地 #6 #11

- **当前阶段**：implementing
- **本段结论**：设计前提 2 成立（commit 时 offset==size，PATCH 空包不写、非空 413，锁外哈希期间不会改写源文件）。四条复现测试在 89a5192 上全红。本段把过期上传改为删源并退出预留，容量扫描只扫 UPLOADING/COMMITTED。
- **关键决策与已否决方案**：过期后按状态排除扫描，而不是依赖 ENOENT 仍对历史行 stat。否决给 I/O worker 加线程。
- **下一步唯一动作**：把 commit 哈希移出准入锁与共享 I/O worker，并用隔离测试锁死。

## 2026-10-20 commit 哈希移出准入锁与共享 I/O worker

- **当前阶段**：implementing
- **本段结论**：HTTP commit 在锁外独立线程做整文件 SHA-256，准入锁内只做查重、计数和建 Job。隔离测试证明哈希进行中 WS 准入与 fail_job 写库都能在时限内完成。
- **关键决策与已否决方案**：HTTP 路由先核验再以 verify_source=False 建 Job，避免二次哈希占住 I/O worker。否决把 fail_job 5 秒退出改成重试。
- **下一步唯一动作**：最小注入红验新测试牙齿，再跑窄测与全量。
