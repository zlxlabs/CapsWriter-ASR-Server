# H1 pinned 消费环境：真实 producer 输入破坏探针

本文件只记录 **H1 pin** `337689689c9b2a314548b70667e447841bf070ad` 上两条物理输入边界是否被消费者锁住，**不是** M6 整体资格、也不是 500/QA 每组五的复跑。假引擎只锁边界，不评识别质量。Hosted 全量与 Win/Sys/生产 URL 未跑。

探针脚本与私有日志留在独立 0700 目录，由 `scratch-worktree.sh` 固定 H1 后自动拆树。公开字段只有角色 / 计数 / 布尔 / 异常类别。

## 场景 1：H1 源、白名单 `env -i`、一次 11 条矩阵

- **命令角色**：`env -i` → `uv --no-project --python 3.12` + 卡面 pin → `pytest tests/test_http_qa_repeat_matrix.py -q -rs -p no:cacheprovider`
- **环境角色**（8 键）：`HOME` / `PATH` / `TMPDIR` / `LANG` / `M6_REPEAT_MATRIX_ARTIFACT_DIR` / `UV_NO_PROJECT` / `SSL_CERT_FILE`（uv 取包）/ `H1_PROBE_LOGDIR`。`DELEGATE_*` 无、`VIRTUAL_ENV` 无、`PYTHONPATH` 无。
- **预建**：owned TMP 与 artifact 目录事先存在。
- **退出 / 计时**：exit 0，46 s（pytest 摘要 45.64 s）。
- **计数**：11 passed，failed 0，skipped 0。
- **版本实测**：Python 3.12；`websockets==15.0.1`（pin 命中）；pytest 9.1.1；pytest-asyncio 1.4.0；aiohttp 3.14.3；httpx 0.28.1。未钉死的实测：numpy 2.5.3、rich 15.0.0、colorama 0.4.6、soundfile 0.14.0。
- **工件消费**（trace.json）：`schema_version=1`；`source_sha` 长度 40 且等于 H1 pin；round `[1,2,3,4,5]`；五轮 `pcm_segment_oracle_ok=true`；五轮重启 `result_payload_equal=true`。
- **producer 角色**：HTTP file runner `queue_in.put(Task)`、recording worker `queue_in.get` 摘要、Managed HTTP 子进程落盘 / GET。本场景未破坏字节。

基准绿，才进入负向探针。原 API 全量 510 **不是** 本命令替身。

## 场景 2：Queue 前 `Task.data` 1 字节变异（长度不变）

- **台子**：`scratch-worktree.sh` 固定 H1；import 路径在 scratch cwd，不加载主 worktree。
- **注入点**：`HttpFileRunner._submit` 原 `queue_in.put`（源文件第 525 行），只改 HTTP `type=file` 段 payload 第 5 字节，XOR 1 bit；不改 `data_sha256` 计算、oracle、源文件、body、常量 bool。
- **生产原方法仍执行**：变异后仍调用原 `queue_in.put(Task(...))`；worker 侧原 `recording_get` → `received_task_record`。
- **命中**：marker `H1_PCM_BYTE_INJECT`；`hit_count=4`；`length_same=true`；`bytes_equal=false`；`task_type=file`。
- **消费者**：矩阵 `_assert_pcm_segments_match_oracle`（独立 ffmpeg oracle vs 反序列化后 `data_sha256`）。
- **结果**：pytest exit 1，1 failed / 3.07 s；异常类别 `AssertionError`（测试文件第 503 行 sha 比较）；无 ImportError / collection 红。负向探针成功。

## 场景 3：持久结果 JSON 非 final 字段破坏后再 GET

- **台子**：另一棵 H1 scratch；owned `httpdata`（新建，非生产 DB / 他 job）。
- **序列**：原 `submit` → DONE → 原 `raw_get(.../result)` 取得完整对象 → 停第一实例 → 改 SQLite `results.payload` 的 `duration` → 第二实例原 GET。
- **注入**：marker `H1_PERSIST_DURATION_INJECT`；`field_role=duration`；`disk_bytes_changed=true`；未改 job_id；`is_final` 仍为 true。
- **import**：`HttpStore` / `HttpFileRunner` 均来自 scratch（`import_from_scratch=true`）。
- **消费者**：原 `_get_result` → `HttpStore.get_result`；`assert second_obj == first_obj`（完整 JSON 对象相等）。
- **结果**：`first_get_ok=true`；`second_get_reached=true`；`full_json_equal=false`；异常类别 `AssertionError`；探针脚本 exit 2。负向探针成功。

## 未知与非本卡范围

- 派发时刻主干基线 `gh api` 失败：**继承红未能判定**。本卡未跑 Hosted 全量，不能把场景 1 的 11 绿写成 M6 Done。
- 未跑私有媒体 / Win / 系统服务 / 生产 URL；未改 App/SDK/H1 源。
- 若日后只改工件 bool / 观察器摘要而不碰 `Task.data` 或 `results.payload`，这两条物理边界仍未锁。
