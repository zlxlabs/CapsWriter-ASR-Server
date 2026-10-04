# M7 CPU 模型前置冒烟进度

## 本次执行范围

- 阶段：`implementing`；任务类型：`tests-docs`；风险级别：`internal`。
- 执行器只落了两份本卡文档；探针、源码快照、输入夹具和结果保留在各自私有隔离根，不进入 Git。
- 复用三台既有 Python 3.12 隔离环境：Linux 3.12.3、Mac 3.12.15、Windows 3.12.12。没有重建环境、补装 pip、重装整包或改原服务。
- CPU 明确为 1 线程；模型加载/推理每台硬预算 180 秒；三台均在预算内自然退出。

## 证据链

1. 从提交 `3d7436c499829eb8bb92fc3757b6e4968c88e548` 打包本任务自己的完整源码快照，不读取旧验证目录作为当前源码证据。
2. 在子进程中先加载并校验 manifest 指定的 10 个实际模块文件，再导入 `EngineFactory`；每个已加载文件的相对路径和 SHA-256 与该提交正本字节一致。
3. 从既有隔离模型根只读引用 Paraformer/Punct 四个必要文件；四个文件均存在，且尺寸与 SHA-256 见主文档。
4. 生产者输入是同一份 16000 字节 PCM；Linux、Mac、Windows 消费文件的完整 SHA-256 都是 `6d04345a...e7580bea`，解析为 4000 个有限 float32。
5. 真实调用走 `EngineFactory.create_asr_engine("paraformer")`、`create_stream`、`accept_waveform`、`decode_stream`，以及 `create_punc_engine`、`punctuate`；没有 dummy ONNX session 或 fake ASR。
6. 结果只保留类型、长度、数量、finite 和耗时：ASR 是 `RecognitionResult`，text 类型 `str`，token/timestamp 长度 `1/1`；Punct 是 `str`，长度 12；不保存正文。

## 运行记录

| 平台 | 状态 | 加载/推理耗时 | 峰值 | 退出证据 |
| --- | --- | ---: | ---: | --- |
| Linux | green | 2.489 s | 932.32 MiB | runner rc=0，`timed_out=false`，`process_gone=true` |
| Mac Apple Silicon | green | 1.254 s | 1021.14 MiB | runner rc=0，`timed_out=false`，`process_gone=true` |
| Windows | green | 2.891 s | 331.71 MiB | runner rc=0，`timed_out=false`，`process_gone=true` |

Windows 的 331.71 MiB 是原 runner 每 1 秒读一次 `WorkingSet64` 的该轮抽样观测最大值，不是操作系统全时峰值，也不能与 Linux/Mac `ru_maxrss` 直接横向比较。Windows 私有根 ACL 复核为 owner 1、admin/system 2、`otherCount=0`、Deny 0；POSIX 两台私有根最终均为目录 0700、文件 0600。

## 失败尝试与处置

这些失败发生在本卡自己的探针和判据层，不是模型质量失败，也没有触碰原服务：

| 尝试 | 现象 | 处置 |
| --- | --- | --- |
| Linux 首次 source manifest 校验 | CT-Transformer 包初始化文件的期望 SHA 多了 1 个字符，模型尚未加载，阶段为 `source_check_failed` | 保留失败 JSON；按 `git show 3d7436c:path` 重新核对正本字节，修正 manifest 后重跑通过 |
| Windows 首次 `-File` runner | stdout 与 stderr 都重定向到 `NUL`，PowerShell 拒绝相同目标 | 改成两个任务临时文件，进程结束立即删除；脚本重新上传并回读尺寸/SHA |
| Windows 第二次启动 | 调用了不带既有隔离根后缀的 Python 路径，系统报找不到文件 | 改用约定的隔离根；没有创建新环境，之后真实加载通过 |
| Windows 早期资源采样 | 采到了 launcher 或旧 PID，峰值不具约束力 | 删除旧 PID 夹具，按当前探针实际 PID 采样；最终 331.71 MiB 记录为有效值 |

失败尝试均没有无条件重试外部副作用；每次继续前先核对了目标状态。有效运行前后确认了自有子进程已退出。上述四行是原模型前置层，本续交不改写。

## Windows PID 退出契约续交

只改本任务私有 Windows runner 与夹具，不重跑 Linux/Mac，不否定原三台 CPU 正例。

- 旧夹具：真实 launcher 再拉 child，child 写 PID 后 sleep 30s，超时窗 3s。旧 runner 只停 launcher，child 21584 仍活着；JSON 记 `process_gone=false` 但 `process_gone_was_fail_condition=false`。
- 修正夹具：同一结构，超时后停可归属 probe 与 launcher；returncode=124，phase=`timeout-gone`，11228 与 16340 均为 observed-gone。
- 修正后模型一次：3d743 源码 + 同一 PCM + 四权重仍 green；launcher 27828 ≠ probe 11904；二者 gone；native 0。新增 `peak_working_set64_mib=333.56`，原 331.71 保留。
- 原 `out/windows-result.json` / `out/windows-runner.json` 字节未改（SHA 与 `correction-161729/original/` 副本相同）。私有证据指针见该 correction 目录下的 fixture/runner JSON，不把公开文档当唯一事实源。

## 原服务与未完成项

- Linux、Mac、Windows 的原服务均未启动、停止、重启、覆盖或做名称扫描；Windows 已知计划任务和 Mac 已知常驻进程未触碰。
- 没有修改全局 PATH、系统动态库、VC++ runtime、原始 venv、共享 Git 配置或仓库依赖；没有上传模型权重，只有源码快照、PCM 和探针脚本传到本任务根。
- 没有读取 profile/settings/.env、凭据、会话或用户 CLI token；输出未包含 URL、Host、凭据片段、recognizedText、音频或 raw response。
- 该 smoke 只证明当前隔离环境可以真实加载并调用一次 CPU 模型；准确率/CER、长音频、服务端协议、并发、工具共同 SHA、最终门禁和正式模型评审仍未完成。
