# PR64 规范意见风险物理分诊

failure-visibility: p2-only

固定对象：primary 生产者 `820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2` → H0 `4e8ecaa69417bb4883b2d19c2352bc1b62f15a0b`（PR 64、run 37188220228 attempt 1、callee `6fd21e0ab5a27a279fe5cd15dd74edaa0b079fe9`）。规范输入为 audit-safe 对象 B（8256 字节、SHA `948ce79ae2f82db68655971195d405c2a1b4b824dd57c9f8ece20dd4543978d6`，reviewer `codex-sub`，`executedModel` 键缺）。本轮只分诊这 3 条，不改 App/SDK/collector/tests，不新开全量审查。

`docs/sessions/261003-http-completion/m7-platform-inventory.md` 在本树不存在；用途与规模取自 `docs/guides/http-baseline.md`、`m7-linux-baseline-evidence.md`，以及已授权 Linux `temp/{full.wav,full_x3.wav,000_video.mp4}` 的容器元数据（不读音频/字幕正文）。

## 结论

没有满足本仓 P1 两问的 finding。三条规范意见的物理前提成立或仅指针差一行：B1/B2 判 **P2 accepted**，B3 判 **nit/P3**。不因「指南叫换新 fixture ID」或「隔离 RLIMIT 不是生产 Host」把真缺陷说成假。不写 streaming/内存池/为 nit 补用 `shutil`。

| ID | 工具 severity | 实测前提 | 两问（真实 case / 后果能否接受） | 本仓 grade | 实测指针与断言 | 范围建议 |
|---|---|---|---|---|---|---|
| B1 `reliability_unbounded_decode_buffer` | major | `_decode_pcm_bytes`（H0 L347）对 `.wav` 走 `sf.read(..., dtype=float32, always_2d=True)` 一次装入；非该快路径走 `ffmpeg ... -f f32le pipe:1` 且 `stdout=PIPE`。返回 `(pcm_bytes, duration_s)` 写入私有 JSON `source.decoded_pcm_bytes`/`duration_s` 与 stdout 摘要。授权素材实测：`full.wav` 16 kHz/mono/pcm_s16le/77.184s/2 469 966 字节 → pcm `4 939 776`、shape `[1234944,1]`、dtype float32、无 ffmpeg；`full_x3.wav` 同格式 231.552s/7 409 742 字节 → pcm `14 819 328`；`000_video.mp4` 77.184s/18 974 961 字节、音频 aac/48 kHz/stereo → ffmpeg argv 与源码一致、pcm `4 939 776`。导入后 RSS 约 48 MiB，解码峰值增量约等于 decoded 数组。隔离稀疏合法 WAV（逻辑 140 000 044、物理约 4 KiB、预期 f32 280 MiB）在子进程 `RLIMIT_AS=256MiB`（非生产 Host）得到 **MemoryError、rc=2、非 signal 9、stderr 无 BASELINE_FAILED**（直接调函数不经 `main()`）。 | Q1：当前真实使用最大 231.552s / 解码 14.8 MiB，无 >2 GiB case；本机 MemAvailable ≈ 38 GiB。Q2：现有规模后果可接受。若将来喂超大文件，采集进程可能 MemoryError 或被内核 OOM 杀掉；后者绕过 `main()` 的 `BASELINE_FAILED`。不损用户 ASR 语料。 | **P2 accepted** | 私有脚本 `01_decode_measure.py` 结果字段：`cases[].stdout_json.sf_read.dtype/shape/nbytes/sample_rate`、`ffmpeg_calls[].argv_redacted/stdout_pipe`、`pcm_bytes`、`ru_maxrss_kb`、大档 `error_type=MemoryError` 且 `signal is null`。H0 工具 SHA `65c572c9665a0cf08ccbfdc1e7a644c055bdcd5ccd966ad839d0ac92eb1c857b`。 | 不要上 streaming 框架。若以后要修：在 `sf.read`/ffmpeg 大分配前用 `soundfile.info`/容器时长做静态上限，超限 `BASELINE_FAILED` 非零退出；或按块累计字节并丢弃 PCM。保持现有 `decoded_pcm_bytes = frames×4`（16 kHz mono f32）口径。 |
| B2 `reliability_http_recovery_cleanup_order` | minor | `run_http` 在 `get_file_result_http` 之后、`is_final`/token-timestamp/源 SHA/`_write_private_json(O_EXCL)` 之前 `recovery_path.unlink`（H0 L273）。SDK 本身不在领取结果后删 recovery，只在 `submit_file_http` 时若文件已在则 `recovery_exists`。实测：独立 loopback stub + 真实 CLI/SDK；合成 364 字节 16 kHz mono WAV；同 ID 结果文件预置 32 字节、SHA `15d92bb0efa2971ec78d93e439a909f3004b6c2da1cb964978e762055ff00ff2`。stub 实际看到 POST `/v1/uploads`、PATCH（body_len=364=源字节）、commit、两次 GET job、GET result；CLI `rc=1`，stderr 仅 `BASELINE_FAILED`+`FileExistsError`；recovery 运行前已知不存在、运行后仍不存在；旧结果哈希未改。未读 recovery 正文、未打印 token。 | Q1：同 ID 且结果已在时会触发（指南已描述，但行为仍在）。Q2：fail-loud；用户源与旧 private 结果仍在；丢失的是**这一次新采集产物**，stub 侧 job 已 DONE，可用 SDK 只读状态查询，不自动 retry。不升级为用户数据损坏。 | **P2 accepted** | `02_recovery_order.py` 断言：`stub_saw_commit/result_get`、`old_artifact_unchanged`、`recovery_exists_after==false`、`stderr_safe.markers` 含 FileExistsError 与 BASELINE_FAILED、`rc==1`。 | 最小顺序调整：校验 + 独占写入成功后再 unlink；失败保留 recovery 或失败证据。禁止自动清 recovery/重试同 job。不凭「换新 ID」当缺陷不存在。 |
| B3 `design_unused_shutil_import` | nit | AST：L14 `import shutil` 无 Load 引用。工具写 L15，H0 上 L15 是 `subprocess`。本仓无 Makefile/`scripts/gate-quality`；gate-v2 quality 走 legacy，无 `lint:` 则跳过；单元 CI 只跑 pytest，不检 F401。 | 维护噪声，不改变采集语义。不能把 nit 升 App P1。 | **nit / P3** | `ast`：`shutil used=False`。 | 以后顺手删导入即可；不要为它加调用或抽象。 |

规范 B1 里「OOM 杀死导致 BASELINE_FAILED 不保证」在本隔离夹具上表现为 **MemoryError 而非 SIGKILL**；`main()` 的 `except Exception` 能包住 MemoryError。内核 OOM killer 仍可能不经该出口。整句不能标 `refuted`。B1 不是立体声计数字节问题，授权 WAV 均为 mono 16 kHz。

## 用途与「受控输入」差额

指南示例是操作者提供的私有 `full.wav` / MP4，loopback 测量工具，CLI `--input` 无机械上限。历史最大当前使用 = `full_x3.wav` 231.552s（解码 14.8 MiB）与 77.184s MP4（容器 18.1 MiB）。这与「任意巨大 CLI 输入也安全」不是同一命题；也不把「只用短素材」写成唯一契约。

## P2 deferred 候选（不建 issue、不签发 disposition）

1. Collector 解码前文档化并强制 size/duration 上限，超限 `BASELINE_FAILED`。
2. HTTP recovery 改为独占落盘成功后再 unlink。

## 未做

未 OCR 全 PR、未重跑 primary、未跟 master、未碰生产服务/模型/77s 真转写。主干 CI 基线派发时不可用，继承红 **未能判定**。
