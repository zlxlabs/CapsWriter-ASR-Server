# HTTP 与 WebSocket v2 基线

`scripts/_baseline_http_ws.py` 使用仓库 SDK 的实际 producer，测量 HTTP 文件任务与默认 WebSocket v2 的本机应用层 payload、完成耗时和 token/timestamp 事实，并可与一份显式参考稿比较。它只连接 loopback 地址；服务必须在同一隔离主机运行。`status=ok` 表示采集和结果落盘完成，不是识别质量通过。

## 实际实验范围

本工具是本批**可信所有者操作的短素材基线实验采集**，不是「通用任意长媒体」采集器，也不保证「各种输入、任意大小」失败都受控。

已指定并完成容器/解码元数据实测的样本：约 77.184 秒 WAV 与同长 MP4，以及约 231.552 秒三倍 WAV。当前最大 decoded PCM 为 14 819 328 字节（约 231.552 秒、16 kHz 单声道 float32）。任意大媒体在有限内存下的可靠性不属本轮已验范围。

这不是代码强制时长上限：CLI `--input` 没有机械上限，工具也没有拒绝超限、流式解码或内存上界保护。不能把上述观测写成「已保障 ≤240 秒」或「服务端 / SDK 文件任务协议只支持约 232 秒」。协议与 SDK API 未因本实验收窄。整段 PCM 只用于 decoded 帧字节事实计量，与 SDK WebSocket 分段和线上 wire bytes 不同；源文件字节、PCM、FLAC/应用 payload 的计量定义见下一节，保持不变。

## 测量口径

- HTTP 输入是原始文件。分别记录源文件字节、以本机 ffmpeg/soundfile 解码为 16 kHz 单声道 `f32le` 后的 PCM 字节、SDK 实际发出的 PATCH body 累计字节和 create 控制 JSON 字节。
- WebSocket 使用 SDK `transcribe_file` 的默认 v2 路径和 `encoding="flac"`；SDK 把音频放进 UTF-8 JSON 文本帧，`data` 字段为 Base64，不发送二进制帧。工具计实际 `send()` 的 JSON UTF-8 字节与二进制字节；Base64 音频字节另列，不用 float32 源 buffer 长度冒充线上 payload。
- HTTP 同一 `Upload-Offset` 再次发送相同 body 时，第二次及以后 body 计入 `http_retransmitted_bytes`。HTTP SDK transport retries 固定为 0，工具不自动恢复；如需 SDK 显式恢复，应单独记录恢复调用及当次实际请求。
- 以上是应用 payload，不含 HTTP headers、TCP、TLS、WebSocket frame 或链路层开销。传输层 TCP 重发对 SDK `send()` 不可见。
- 每个协议单独执行一个任务。MP4 与 WAV 用不同匿名 fixture ID、分开记录；比较时两协议必须使用同一源文件、同一服务模型、同一 `seg_duration` 和 `seg_overlap`。
- 工具校验 `/health` 的 `status`、`worker_alive`、模型、协议版本和运行 `git_sha`。健康端点目前返回短 SHA；要求它是指定完整 server SHA 的至少 7 位前缀。结果同时记 benchmark tool SHA 和 SDK 版本，不把工具提交 SHA 说成服务版本。
- 私有 JSON 保存源绝对路径和哈希、参考稿、完整 final 文本/token/timestamp、请求体摘要及模型与工具信息，要求仓库外目录权限为 `0700`，文件权限为 `0600`。stdout 仅含匿名 ID、字节数和指标。CLI 捕获的普通 Exception（含当前观测到的 `MemoryError`）写 `BASELINE_FAILED` 到 stderr 并非零退出；这是 fail-loud，不能证明内核 OOM 受控。未知大型输入上的内核 OOM 可能直接杀死进程，从而绕过 `BASELINE_FAILED`。

## Linux 隔离运行

1. 使用独立 Python 3.12 环境。不要激活或覆盖已有服务环境：

   ```sh
   PRIVATE=/absolute/private/capswriter-m7
   mkdir -m 700 -p "$PRIVATE"
   uv venv "$PRIVATE/venv" --python 3.12
   uv pip install --python "$PRIVATE/venv/bin/python" -r requirements-server-linux.txt
   ```

2. 准备 Paraformer 和 Punct-CT-Transformer 权重到私有缓存。服务配置将模型路径锚定在代码目录 `models/`；让对应的两个模型目录软链到私有缓存，软链和模型都不得进入 Git。Paraformer 走 ONNX CPU；不需要下载 GGUF、llama.cpp 或 GPU 包。缺失、空文件或路径不匹配时停止，不切假引擎。

3. 在隔离 checkout 中检出要测的**已合并 server SHA**，不从正在开发的 benchmark 分支启动服务。为 WebSocket 和 HTTP 各选一个随机高位端口，先用 `ss -Hln` 确认都未监听；配置不接受端口 `0`，冲突时停止并重新准备一组端口，不让服务自动换端口。数据目录使用稳定的私有绝对路径：

   ```sh
   WS_PORT=$(shuf -i 49152-65535 -n 1)
   HTTP_PORT=$(shuf -i 49152-65535 -n 1)
   test "$WS_PORT" != "$HTTP_PORT" || exit 1
   ss -Hln "sport = :$WS_PORT" | grep -q . && exit 1
   ss -Hln "sport = :$HTTP_PORT" | grep -q . && exit 1
   export CW_ADDR=127.0.0.1
   export CW_PORT="$WS_PORT"
   export CW_HTTP_PORT="$HTTP_PORT"
   export CW_HTTP_DATA_DIR="$PRIVATE/http-data"
   export CW_MODEL_TYPE=paraformer
   "$PRIVATE/venv/bin/python" start_server.py > "$PRIVATE/server.log" 2>&1 &
   server_pid=$!
   ```

   先确认 PID 属于这次启动，再由基线工具探测 `/health`。日志只重定向到私有文件；不要整段输出。结束时只向确认过的 `$server_pid` 发 `TERM` 并 `wait`，不使用 `pkill`。

4. 对同一 WAV 先后运行两种协议。MP4 再单独运行一对命令；不要并行提交任务：

   ```sh
   COMMON="--input /private/source/full.wav --fixture-id wav-private-01 --expected-server-sha <40位SHA> --expected-model paraformer --private-dir $PRIVATE/results --reference /private/source/000_video.srt --reference-status unverified"
   uv run --no-project --python 3.12 --with numpy --with soundfile --with rich --with colorama --with websockets==15.0.1 --with httpx==0.28.1 python scripts/_baseline_http_ws.py --protocol ws-v2 --server "ws://127.0.0.1:$WS_PORT" $COMMON
   uv run --no-project --python 3.12 --with numpy --with soundfile --with rich --with colorama --with websockets==15.0.1 --with httpx==0.28.1 python scripts/_baseline_http_ws.py --protocol http --server "http://127.0.0.1:$HTTP_PORT" --health-url "http://127.0.0.1:$WS_PORT/health" $COMMON
   ```

   `--fixture-id` 不得包含文件名、路径或语音正文。参考稿来源未核实时用 `unverified`；CER 只表示相对该参考稿的差异，不表示识别正确率。归一化规则固定为：剥离 SRT 独立编号和时间轴、拼接断行、删除空白与 Unicode 标点、对剩余字符做 `casefold()`。无参考稿可省略 `--reference`；归一化后为空会在发请求前失败。

5. CLI 导入旧 `_baseline_asr.py` 的归一化代码，隔离运行时需显式安装它已有的 `rich` 与 `colorama`；本命令还需 `numpy`、`soundfile`、`websockets` 和 `httpx`。每协议完成后检查私有 JSON 的 `status=ok`、server/tool SHA、SDK 与 ffmpeg 版本、DONE/final 状态、token/timestamp 数量、单调性、覆盖范围、耗时和 producer payload 摘要：`token_count` 应与 `timestamp_count` 一起看，并核对完整 `is_final`、覆盖和时长区间字段。空时间戳没有质量证据；单调性对空列表按 Python 规则为真，也不表示质量通过。参考稿未核实的 CER 只表示相对该稿的差异，不是识别正确率。失败项和未量项如实保留；工具当前不测 CPU/RSS，也不推算 TCP/TLS 开销。

## 超时后的人工检查

HTTP 请求超时并不能证明服务端没有接收上传或开始任务。私有目录中的 `<fixture-id>.http-recovery.json` 保留 SDK 恢复凭据；它可能包含访问令牌，继续限制为仅本人可读，不要打印文件内容。相同 fixture ID 和私有目录再次运行会因 `recovery_exists` 失败退出，不会恢复、取消或重发原任务。

每次新测量都使用新的匿名 fixture ID，不要用含路径、文件名或语音正文的字段值作 ID。超时后 recovery 尚存时，同 ID 会在上传前因 `recovery_exists` 被拒；这是恢复记录仍在的情形。若测量已成功且结果 JSON 已存在，再用同 ID 不是恢复：当前行为可能先创建新的 HTTP job，随后在独占写结果时以 `FileExistsError` 可见失败；旧结果不覆盖，但新 job 可能已重复计算，且 SDK 已清理本次新任务对应的 recovery 文件。不要因此自动清理文件、重试、恢复或取消任务。

需要确认原任务状态时，可在隔离环境中只调用 SDK 状态查询接口；它只查一次，不轮询，也不取回转录正文：

```python
from pathlib import Path
from capswriter_asr.http_client import get_file_job_http_sync

status = get_file_job_http_sync(
    "http://127.0.0.1:49152",  # 换成本轮的 HTTP_PORT
    resume_path=Path("/absolute/private/results/wav-private-01.http-recovery.json"),
)
print(status.state, status.result_available, status.source_available, status.error_code)
```

不要自动删除 recovery 或结果文件，也不要自动重试、恢复或取消任务。只有用户明确开始一次新测量时才使用新的匿名 fixture ID；这会创建可能重复计算的新上传/任务，不是对原任务的恢复。已有结果文件以独占创建方式写入，不会覆盖。此处的权限要求针对 Linux `0700` 目录和 `0600` 文件；Windows ACL 未在本指南的实测范围内。

上述独占落盘、fresh fixture ID，以及 recovery 在结果校验/写入前先删，是当前操作契约与已知限制，不是对本仓 #72 的行为修复。#72 仍 OPEN，后续扩大到超大媒体时再定义输入边界/计数与「结果写完再清 recovery」的验收。数据可再生成不等于零损失：同 ID 冲突时可能丢掉这一次新采集结果；旧用户媒体与旧结果不被覆盖。

## 回归验证

卡面全套验证命令：

```sh
uv run --no-project --python 3.12 --with numpy --with rich --with websockets==15.0.1 --with colorama --with pytest==9.1.1 --with soundfile --with pytest-asyncio==1.4.0 --with aiohttp==3.14.3 --with httpx==0.28.1 python -m pytest tests/ -q -rs -p no:cacheprovider
```

上面的全套测试命令包含 `pytest`/`aiohttp` 等测试依赖。单独运行基线 CLI 时，按示例安装 `numpy`、`soundfile`、`rich`、`colorama`、`websockets` 和 `httpx`；不要依靠全套测试环境替指南补依赖。

`tests/fixtures/http_baseline_producer.json` 是 SDK 实际 HTTP 请求体和 WS v2 `send()` 帧的合成契约产物；它只验证 producer 序列化，不是模型质量数据。旧 `scripts/_baseline_asr.py` 仍是 WS v1 Base64 JSON，未改其默认行为，不能拿它的 float32 输入长度代替 v1 JSON payload、SDK v2 字节或 HTTP 原文件字节。
