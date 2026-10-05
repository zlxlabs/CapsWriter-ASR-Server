# M6 保留套件证据：冻结源码双臂全量补采（独立验证，不实施修复）

本卡只补采**原缺失的原产物**：CodeH2 `7794074` 那次交付当时**没有留存全量 JUnit XML、没有独立
pytest summary**，511 passed / 3 skipped / 12 组 once 只存在于报告声称。本卡用**新时点**重采一次，
原报告与旧 XML 缺事实**不改写为当时有 JUnit**。不改 App / test / config / CI / 依赖，不重开原 30
第三轮，不做新 code review，不洗修次数，不验证任何修复，不宣称 M6 Goal 完成。

## 1. 源绑定（新 Doc 源 ≠ 测试源，树同码不同 Doc）

新文档源 / checkout `f38213085b530a1acb8a51816770a40a2bcc4b44`；测试源码树 CodeH2 `7794074`。实测
`git ls-tree -r -z HEAD` 过滤 `docs/`：nonDoc **340** 个 blob、摘要 `27e40ab6…ae9`，与 CodeH2、与 f382
**逐项相同**（docs 146 vs 135 段不同，印证「同码不同 Doc」）。五轮矩阵 trace 的 `source_sha` 由
`tests/test_http_qa_repeat_matrix.py:459 _source_sha()` 运行时取 checkout 的 `git rev-parse HEAD`，故两臂
trace 记 **f382**，不是 779。运行前后各采一次：`actual_git_sha=f382`、`git status --porcelain` 空、
nonDoc 摘要不变；已知否定非恒真——`f382…nope` 与坏分支引用都被 `rev-parse --verify` **确实拒绝**。

## 2. 两臂真实执行（各一次，pin / unpin）

命令（相对仓库根，`python -m pytest` 入口，未换 console 脚本、未加插件、未改 suite 行为）；`LOCK`
为本次 dispatch 独占的 full-suite 锁文件，宿主路径不入库：

```
flock -w 600 "$LOCK" timeout 900 uv run --no-project --python 3.12 --with numpy \
  --with rich --with <WEBSOCKETS> --with colorama --with pytest==9.1.1 --with soundfile \
  --with pytest-asyncio==1.4.0 --with aiohttp==3.14.3 --with httpx==0.28.1 \
  python -m pytest tests/ -q -rs -p no:cacheprovider --junitxml=<owned-junit>
```

| 臂 | websockets 实际版本 | 排队 s | 执行 s | 总墙钟 s | rc | stdout 末行 | JUnit 字节 |
|---|---|---:|---:|---:|---:|---|---:|
| pin | **15.0.1** | 0.010 | 438.812 | 438.828 | 0 | `511 passed, 3 skipped, 195 warnings in 436.93s` | 65318 |
| unpin | **17.2** | 0.007 | 412.613 | 412.622 | 0 | `511 passed, 3 skipped, 195 warnings in 410.39s` | 65318 |

unpin 的 17.2 是**同 requirements、同一 uv 环境内用 `importlib.metadata` 实采**，不是从卡面推断；
同次另采 `pytest.__version__=9.1.1`、`pluggy 1.6.0`、`iniconfig 2.3.0`、`numpy 2.5.3`、`rich 15.0.0`、
`aiohttp 3.14.3`、`httpx 0.28.1`、`soundfile 0.14.0`、`colorama 0.4.6`。第一臂为真实绿，故按卡面继续
第二臂；未出现真实红即无需立停。

## 3. JUnit 真实存在与三方对账（`xml.etree` 实解析）

两臂 JUnit 各 65 318 字节、`testcase` **514** 个、`failures=errors=0 / skipped=3`；`tests` 属性等于实际
元素数，并与**真实 returncode 0**、stdout summary 的 511/0/0/3 三方一致；参数化用例实计 **87** 个。判据
非恒真：要求总数 > 0，且 `passed == tests − skipped − failures − errors`；校验器是本次脚本的必要读者，未
加仓库框架。三条资源 skip 逐条为：`test_aligner_integration.py::test_aligner_loads_not_fallback` 与
`::test_aligner_produces_token_timestamps` 均为「ForceAligner 后端/模型未安装」（模块级 skipif，`:53`/
`:62`）；`test_segmenter.py::test_vad_pipeline_smoke` 为「缺 silero-VAD 模型或 onnxruntime」（`:208`），
与源码核对一致。**无 HTTP / ffmpeg / aiohttp / websockets 相关 skip**；判据不是「预期恰好 3 条所以通过」，
而是逐条比对 nodeID+原因，并对点名缺 HTTP 资源的 skip 直接判 failed（首版判据把仓库路径里的 `http` 子串
当成关键 skip，是恒真陷阱，已修）。

## 4. 12 组映射在真实 JUnit 中的逐组结果（每组一次）

| 组 | 映射 nodeID 数 | 真实样本 | passed | 未出现 |
|---|---:|---:|---:|---:|
| 1 真实二进制 producer | 8 | 9 | 9 | 0 |
| 2 受理后脱离连接 | 2 | 5 | 5 | 0 |
| 3 幂等创建与提交 | 4 | 6 | 6 | 0 |
| 4 可信续传 offset | 3 | 3 | 3 | 0 |
| 5 部分上传跨重启 | 4 | 4 | 4 | 0 |
| 6 结果跨重启 | 2 | 2 | 2 | 0 |
| 7 双 owner 并发 | 11 | 12 | 12 | 0 |
| 8 取消与 I/O 交错 | 1 | 1 | 1 | 0 |
| 9 负例矩阵与容量上限 | 6 | 6 | 6 | 0 |
| 10 解码与 PCM producer | 1 | 4 | 4 | 0 |
| 11 整任务失败与监督 | 3 | 3 | 3 | 0 |
| 12 源清理与旧 WS 回归 | 21 | 23 | 23 | 0 |

样本数按参数化逐样本计（组间有重叠，不可相加当总量）。映射由覆盖表 `文件:行` 用 AST 解析：落在 test 函数
内取该函数；落在 helper 体内则沿调用图传递闭包取**真正调用它的 test 函数**，解析不到即显式报 UNRESOLVED
——初版 3 处落在 helper、其中 1 处经两层 helper 才定到位，已全部解析为真实 nodeID。参数化样本逐个查状态，
无一组存在 skip 样本；「零 errors」不被当作「全组通过」，未记录节点会直接判 failed。具名新增用例全部
present：`test_real_sdk_upload_bytes_match_server_disk_sha`(1)、
`test_lost_commit_response_recovers_with_exactly_one_recognition`(1)、
`test_real_ws_and_http_share_one_worker_without_key_pollution`(1)、
`test_resampled_sources_produce_bounded_16k_mono_f32_segments`(**2 样本，均 passed**)、
`test_final_segment_failure_fails_job_without_publishing_partial`(1)、
`test_five_round_same_service_concurrency_cancel_restart_ws`(1，套内自带五轮循环，本卡未再另跑模块凑数)。
断言边界来源仍是覆盖表所记真实 producer 侧：`received_task_record` / `result_payload` 直读对象字段、
`sources/*.bin` 字节与 sha256、只读 SQLite、真 ffmpeg argv。

## 5. 采集判据的负控（假 XML，不是原矩阵 AssertionRed）

对**副本**注入已知坏，原 XML 未动：注入真实 `<failure>` 元素并同步 counts → 拒；删掉组 1 的一个映射
nodeID → 拒（报「未出现在真实 XML」）；给 HTTP 侧 testcase 注入点名缺 ffmpeg/aiohttp 的 skip → 拒
（资源 skip 规则 + skipped 计数双红）；组映射截断并指向缺失文件 → 拒（报 UNRESOLVED 节点）。未改动的原
XML 副本**判 accepted**，证明上述拒绝来自注入而非噪声。这是验证采集器自身的判别力，不是原矩阵的反向
红验，也不改源码 TDD。

## 6. 边界与仍然未知（不因本次绿而推进）

- 原 `7794074` 那次交付**当时仍缺全量 JUnit / 独立 pytest summary**，本文件不追认；本卡工件是新时点
  产物，采样于 2026-10-05T18:06Z（pin）与 18:19Z（unpin）。
- **P2 单测判别力 gap 未修**：五轮消费者按 CodeH2 提交说明只校验 schema、不认证执行次数，全重标 clone
  仍被接受；本卡不修此判定力，也不把「514 个 testcase」当成五轮真实执行证明。
- 前派发 `dlg-20261005-164121-c35048` 的 `died_unknown` **未改、未重签**，原因仍 unknown。
- 继承红：派发时主干基线不可用、无可比基线，故「继承红」**未能判定**；本次两臂 0 红。
- 组 9 的 GiB 级上限按缩小常量验证类别与等值边界，未做真实 16 GiB 压测；假引擎不等于 ASR 质量；生产
  `CapsWriterServer`/`SocketManager` 全装配未覆盖。Draft gate 未批准，CI 无需 rerun。M6 Goal **未标完成**。
- 私有 JUnit / stderr 可能含主机名与宿主路径：原件 0600、目录 0700 留在本机 dispatch 专属缓存目录，
  **未入库**，本文件亦不写其宿主路径；只发布 counts / nodeID / skip 原因 / 版本 / 时序等结构化白名单
  字段。首轮 wrapper 因 argv 引号拼错在收集前即被 uv 拒绝（无 JUnit），保留为
  `arm-pin15-attempt0-aborted-argvbug`，不冒充一次执行。