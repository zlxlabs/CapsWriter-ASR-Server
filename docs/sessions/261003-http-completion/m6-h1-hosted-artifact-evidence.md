# M6 H1 Hosted 五轮矩阵工件证据

<!-- delegate-outcome: succeeded -->

## 结论与范围

本记录只证明 PR83 的 H1 Hosted CI 实际产物、生产者来源和文件消费者闭环，不把
Draft gate 的绿、旧 H0 工件或代码审查结果当作生命周期批准。H1 Hosted 3.12
job 真实运行一次 `pytest tests/`，在同一隔离服务上完成 5 轮，每轮包含
`concurrency`、`cancel_io`、`restart`、`legacy_ws` 四个 phase；3.11 的两个
job 只运行 SDK tests，不能计作另外两个 M6 cycle。

## Run、来源与 CI 链路

- PR：[83](https://github.com/zlxlabs/CapsWriter-ASR-Server/pull/83) 仍为 Draft，
  base 为 `master@6aa76f6c6935e9cef00afc1bcbcf8327e7c95488`，H1 文档头为
  `337689689c9b2a314548b70667e447841bf070ad`，代码头为
  `d5b5717323eac858b95cdfacec125cfc9ee0012f`。
- Hosted CI run：[37311065357](https://github.com/zlxlabs/CapsWriter-ASR-Server/actions/runs/37311065357)，
  attempt 1、`pull_request`、head `3376896…`，结论 success。目标 job 为
  `111766323793`（Python 3.12）；`运行 pytest`、`校验五轮矩阵工件结构`、
  `保存五轮矩阵工件` 均 success。两个 3.11 job 的后两步均 skipped。
- 工件：[m6-repeat-matrix-py312](https://github.com/zlxlabs/CapsWriter-ASR-Server/actions/runs/37311065357/artifacts/11346765500)，
  artifact id `11346765500`，大小 1059 bytes，只含 `trace.json`。同一次 CI
  的 consumer 在 `tests/test_http_qa_repeat_matrix.py` 以 `importlib` 加载；
  `.github/workflows/ci.yml` 将 pytest、consumer、upload-artifact 绑定到同一
  `M6_REPEAT_MATRIX_ARTIFACT_DIR/trace.json`。
- `trace.json.source_sha` 为
  `f99b7517c01d9fc7b7b7218ade1a1eda65900ce2`。这是本次 PR merge checkout：
  parents 为 `6aa76f6c…` 与 `337689689c…`，tree 为
  `6b129a73a5520bd36021cb2f818d5e7e0a66fe0a`，与 H1 头的 tree 相同，不能
  回填为事后 live ref 或代码头 `d5b5717…`。3.12 checkout/HEAD 日志白名单行
  同时出现该 merge SHA、H1 SHA 和 base SHA；未读取完整 provider/test log。
- source tree API `recursive=1` 返回 `truncated=false`、578 个 entry、475 个
  blob；本地 `git ls-tree -z` 的 H1 tracked tree 非空（475 个 NUL 分隔文件，
  47879 bytes）。H0 `da81cacc…` 的 tree 为
  `43c3274004ed58bc40ec68c8dd11592abaaeffcc`，H1/H0 内容比较返回 rc=1；
  不存在的坏 ref 返回 rc=128。H0 仅作为来源判据的反例，不评价源码优劣。

## 实际 producer 与实际文件

CI 测试入口在 `tests/test_http_qa_repeat_matrix.py`：它用真实 `git rev-parse
HEAD` 写 `source_sha`，用真实 Python runtime 写 `source_runtime`，每轮完成后将
JSON 编码字节写入 `trace.json`；最后在同一测试进程调用消费者。Hosted workflow
随后以 `python -` 的 importlib 入口再次读取该路径，最后才上传该文件。生产者
角色来自实际工件，且没有用手造 metadata 补齐：

`http-sdk`、`ws-frame`、`ffmpeg-shim`、`recording-worker`、
`managed-http-subprocess`、`io-thread-barrier`。

消费者还对实际文件字节执行 schema、空 skip、source runtime/SHA、绝对路径、
凭据/IP、phase、round job id、真实 ffmpeg argv/log offset 约束；因此这里只报告
文件中真实存在的字段，不把没有字段的内容伪造为验证结果。

## 下载原件的字段摘要

原件 `schema_version=1`、`source_runtime=python-3.12`、`skips=[]`；
五轮和四个 phase 均为 `pass=true`，每轮 `data_dir_role` 都是
`persistent-httpdata`。下表中的 ffmpeg offset 是累计日志中的事件索引，不是
字节数。

| round | ffmpeg offset / 本轮 start 数 | cancel-first：pending/mailbox/slot | io-first：pending/mailbox/slot | 并发 body/PCM oracle | 重启 result/engine calls | 新实例 WS |
|---:|---:|---|---|---|---|---|
| 1 | 0 / 4 | 1 / 31 / true | 0 / 32 / false | true / true | true / 0 | true |
| 2 | 7 / 4 | 1 / 31 / true | 0 / 32 / false | true / true | true / 0 | true |
| 3 | 14 / 4 | 1 / 31 / true | 0 / 32 / false | true / true | true / 0 | true |
| 4 | 21 / 4 | 1 / 31 / true | 0 / 32 / false | true / true | true / 0 | true |
| 5 | 28 / 4 | 1 / 31 / true | 0 / 32 / false | true / true | true / 0 | true |

每轮并发 phase 的 `http_source_bytes=24525`、源文件与落盘字节匹配；
`pcm_segment_oracle_ok=true`。每轮 restart phase 都有正向 prefix/suffix
offset（2/4）、DONE 回放、known-empty 防止自动重跑、重启后 engine calls 为
0，且完整 result payload 相等。每轮 legacy WS 都收到 final，并标记为连接在
仍存活的重启后实例。

## 独立 consumer 验证

对下载后的原始 `trace.json` 实际字节调用 `consume_repeat_matrix_trace` 一次，
正例通过。随后只复制并改写 clone 文件，先确认 clone 字节已变化并写入
`FAULT_INJECTION_REACHED` 标记，再逐个调用同一消费者；以下 5/5 均得到
`AssertionError`：

1. 删除第 5 轮；
2. 删除 `cancel_io` phase；
3. 将已完成 I/O 的 `io_first.slot_held_before_release` 改为 `true`；
4. 将 `restart.result_payload_equal` 改为 `false`；
5. 将第 4 轮 `ffmpeg_log_offset` 改为第 3 轮的值。

本地外置脚本第一次调用因临时脚本目录遮蔽标准库而未进入消费者，修正导入路径
后正例通过、五个反例全部变红；该次 ImportError 不计作行为红验。没有重跑矩阵
或全量 suite。

## 安全边界、红绿判定与未覆盖项

- 工件消费者实际检查并通过了无凭据赋值、无 IP、无绝对宿主机路径；本记录只保留
  匿名 SHA、计数、字段名和 producer role，不记录 argv/path、env body、音频
  hash、token 或原始响应。
- `http_source_bytes_match`、`pcm_segment_oracle_ok`、`result_payload_equal` 和
  `ws_on_restarted_instance` 都有真实 producer 字段和消费者约束；它们证明的是
  本次隔离服务边界与 payload shape，不是模型识别质量，也不等同于 12 组各跑
  五次。
- gate run：[37311066371](https://github.com/zlxlabs/CapsWriter-ASR-Server/actions/runs/37311066371)
  为 Draft gate；primary、OCR 和相关审查 job skipped，不能作为审批。派发时
  主干基线 API 不可用，因此继承红与新红无法比较；本次新 H1 run/job/artifact
  未发现失败步骤。
- 本卡没有取证裸 shell、真实模型/录音、物理容量压测、12×5 全矩阵或独立代码
  审查；这些保持 unknown，不能由本工件扩大声明范围。
