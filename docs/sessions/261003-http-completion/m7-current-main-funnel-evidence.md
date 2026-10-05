# M7 当前主干集成验证证据

## 结论与边界

- Dispatch-Id：`dlg-20261005-015757-d65d06`
- 分支：`card/http-m7-current-main-funnel-261005`
- 基线：`a550a2cfe455485a16fe39ca4c6e64f05aae5cdc`
- 正式 C2 主干：`4de4a7ffa44dfb50b48c252510927c4b2166cc77`
- 当前候选合并提交：`16d7623e847765355c3a50fd41add31623333d6a`
- 验证结论：本候选只把正式 C2 主干以普通 `--no-ff` 合入，未手改产品代码、SDK、collector、既有测试或 workflow；本文件与同目录 progress 文件是本轮新增验证记录。

本轮验证的是 SDK/producer 合入兼容性和两套测试依赖矩阵，不是 P2 修复，也不声称模型识别质量、任意大媒体受控或所有失败都能被普通 Python 异常捕获。旧 finding 的事实、级别和 deferred 政策结果保持原样。

## 合并来源与不变量

主干提交身份已核验：`4de4a7f` 是 PR 62 的正式 merge，提交时间为 `2026-10-05T01:50:12Z`，其父提交为 `3d7436c` 与 `7a3a964`。当前 HEAD 以它为第二父提交；`git merge-base --is-ancestor 4de4... HEAD` 通过。

主干带入的产品源变更按实际 source scope 枚举如下；三点的变更均来自合并提交，未在本卡重写：

| 文件 | `4de4^1..4de4` 插入/删除 |
|---|---:|
| `core/server/app.py` | 49 / 17 |
| `core/server/http_server.py` | 42 / 0 |
| `core/server/http_store.py` | 44 / 4 |

SDK/App 的当前差异 provenance 只命中候选合并提交 `16d7623`；本卡没有 SDK/App 的手工 diff。工具 `scripts/_baseline_http_ws.py` 的去 docstring AST 哈希如下，原始 `4e8`、基线 `a550` 和当前 HEAD 三者相同：

```text
original-4e8  f76c41d796a9cd5a80c6af0f949bfb33ea8cc4712052b2350f2385034a429034
base-a550     f76c41d796a9cd5a80c6af0f949bfb33ea8cc4712052b2350f2385034a429034
head          f76c41d796a9cd5a80c6af0f949bfb33ea8cc4712052b2350f2385034a429034
```

`git diff --check a550..HEAD` 通过。合并后 `a550..HEAD` 实际为 5090 插入、65 删除、5155 行总差异，超过卡面 3300 目标和 4000 硬预算；该超额来自被明确授权且未压缩的正式主干合入，未以删改产品或测试迎合预算，作为本轮预算偏差保留。

## 两套全量矩阵

每套命令都独立取得名称为 `caps-http-261005-fullsuite.lock` 的系统锁，锁等待上限 600 秒，拿锁后测试命令自身上限 900 秒；套件结束立即释放锁。未使用原服务 unit、全局信号、宽泛进程扫描或自动重试。

固定版本命令：

```text
uv run --no-project --python 3.12 --with numpy --with rich --with websockets==15.0.1 --with colorama --with pytest==9.1.1 --with soundfile --with pytest-asyncio==1.4.0 --with aiohttp==3.14.3 --with httpx==0.28.1 python -m pytest tests/ -q -rs -p no:cacheprovider
```

结果：`487 passed, 3 skipped, 149 warnings in 224.76s`，退出码 0。3 个 skip 是两个 ForceAligner 依赖/模型缺失用例和一个 silero-VAD/onnxruntime 缺失用例；没有 HTTP decode skip。

去 pin 命令：

```text
uv run --no-project --python 3.12 --with numpy --with rich --with websockets --with colorama --with pytest==9.1.1 --with soundfile --with pytest-asyncio==1.4.0 --with aiohttp==3.14.3 --with httpx==0.28.1 python -m pytest tests/ -q -rs -p no:cacheprovider
```

实际解析的 WebSocket 版本为 `17.2`。结果：`487 passed, 3 skipped, 149 warnings in 226.00s`，退出码 0；墙钟从启动到结束为 409 秒，其中包含等待并行验收释放独占锁的时间。3 个 skip 与固定版本套件相同，无 HTTP decode skip。

当前候选中的 `tests/test_http_baseline.py` 11 个 producer 契约用例随上述完整套件实际执行：包括 HTTPX 实际 POST/PATCH/commit 请求、默认 WebSocket v2 实际文本帧、CLI 子进程、私有 JSON 字节落盘、时间戳边界和空参考稿 fail-loud。没有复制同进程 fake 计数来替代这些跨进程测试。

## 私有跨进程短素材探针

仓外私有报告标签：`m7-synthetic-025`；私有目录权限为 0700，报告文件为 0600，完整源指纹、producer JSON、argv、ffmpeg argv 和私有结果正文均不写入仓库或 stdout。stdout 只有安全汇总，未包含私有文本、哈希或主机路径。

探针以独立 producer 子进程分别执行 HTTP 与默认 WS v2，连接本机真实 TCP/WebSocket listener；识别响应使用显式 synthetic fixture，不代表模型质量。真实 ffmpeg runner 的 decode/transcode argv 同步写入私有报告。

| 计量对象 | 实测值 |
|---|---:|
| 源 FLAC 文件字节 | 10075 |
| 解码 PCM 字节 | 16000 |
| PCM 格式/时长 | `f32le/16000/mono` / 0.25 秒 |
| HTTP producer PATCH body | 10075 字节，等于源文件字节 |
| HTTP producer control JSON | 198 字节 |
| HTTP application retransmission | 0 字节 |
| WS v2 UTF-8 JSON 文本帧 | 1 帧 / 13677 字节 |
| WS v2 Base64 音频字段 | 13436 个 ASCII 字符，解码后 10075 字节 |
| WS v2 二进制帧 | 0 |

HTTP listener 实际收到 health、create、PATCH、commit、job status、result 六个 TCP 请求；producer meter 对 health 校验之外的五个 HTTP 应用请求计量。PATCH 的 `Upload-Offset=0` body 与源文件逐字节相等。WS listener 实际收到的 JSON 帧含 `source=file`、`encoding=flac`、`is_final=true`、`samples_total` 等字段；实际 producer 发的是 UTF-8 JSON，不是二进制帧。

源文件在两次 producer 操作前后指纹一致；源文件字节、解码 PCM 字节和应用层 payload 分开计量，没有用容器大小猜 PCM，也没有把 float32 buffer 大小冒充 HTTP/WS wire payload。两个 producer 的私有结果均为 `status=ok`，token/timestamp 形状由 synthetic result 锁定。

## Whole SDK71 合同与已知事实

| 不变量 | 代码位置 | 本轮/既有已执行锁定 |
|---|---|---|
| 默认 WS v2 是 UTF-8 JSON，音频 `data` 为 Base64，不发 binary frame | `sdk/capswriter_asr/client.py` 的 `_audio_frame` / `transcribe_file` | `tests/test_http_baseline.py::test_ws_meter_observes_actual_sdk_v2_send_payload`；本轮私有 WS TCP probe |
| HTTP PATCH 重复 offset 的同 body 计入 retransmission | `scripts/_baseline_http_ws.py::PayloadMeter.record_http` | `tests/test_http_baseline.py::test_http_meter_counts_emitted_patch_and_repeated_offset_bytes`；本轮实际 PATCH 为 10075 字节、重复计数 0 |
| 源文件、decoded PCM、HTTP/WS application payload 分开计量 | `scripts/_baseline_http_ws.py::_file_sha256`、`_decode_pcm_bytes`、`PayloadMeter` | `test_cli_http_producer_payload_and_private_json_bytes`；本轮私有报告保留实际文件字节/PCM/producer payload |
| safe summary 不带私有正文、哈希或主机路径 | `scripts/_baseline_http_ws.py::safe_summary` / `main` | `test_cli_http_producer_payload_and_private_json_bytes` 的 stdout 红验；既有两轮合格验证保持，不新开计数 |
| 私有结果独占创建、权限和格式可核验 | `scripts/_baseline_http_ws.py::_private_dir` / `_write_private_json` | `test_cli_http_producer_payload_and_private_json_bytes`；本轮两个私有结果均 `status=ok` |

原 B1 whole-buffer 事实仍是：WAV 快路径一次性 `soundfile.read`，其他格式一次性 ffmpeg stdout；这不是本轮修复。原 B2 recovery 事实仍是结果领取后、结果校验/私有 JSON 写入前清理 recovery；这不是本轮修复。fresh fixture ID 只是避免实验产物冲突，不是修复；普通 `MemoryError` 可由 CLI fail-loud，不等于内核 OOM 必然可控。

旧正式 fail run `37188220228` attempt 1 与 H0 `4e8ecaa...` finding identity 保留在 `reviews/pr64-canonical-risk-verdict.md`；政策 deferred run `37224512609` 被拒不能当签据；当前 HEAD 是主干集成验证，不是偷换旧 finding 的反证。该 verdict 与 `docs/guides/http-baseline.md` 均仍在 HEAD，本文只做指针，不改写旧 evidence/作者报告或敏感私有旧证据。

## 继承红与新红

派发时主干基线 `gh api` 不可用，因此与基线同作业名/首失败步骤的红无法分类；按卡面要求标为**继承红未能判定**。本轮两套全量矩阵与私有探针在收尾时若均为 0，则没有新红；任何非零结果只记录原始失败，不自动重试或把它归为 skip。
