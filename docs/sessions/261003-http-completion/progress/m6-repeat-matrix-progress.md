# M6 五轮矩阵进度

阶段：implementing → 已提交 Draft，等待主脑独立审生产者红绿与 CI artifact。
结论：具名入口在同一 `persistent-httpdata` 上机械跑满 5 轮（并发 / 取消交错 / 受控重启 / 旧 WS），
CI 3.12 与无会话 `env -i` 各消费一份工件；**不是** 12 组各 5 遍，也不是 500 条测试重复 5 次。
假引擎只锁边界，不是 ASR 质量。Draft 绿 ≠ M6 Done。

## 入口与同服务身份

- 测试：`tests/test_http_qa_repeat_matrix.py::test_five_round_same_service_concurrency_cancel_restart_ws`
- 循环：`REPEAT_COUNT = 5`，`REQUIRED_PHASES = (concurrency, cancel_io, restart, legacy_ws)`
- 同服务：五轮共用一个 `httpdata`；重启只换 PID，不换目录。
- 复用 `running_runner_server` + `ws_recv`（QA）与 `ManagedHttpServerHarness`（supervision），未改 harness / App / SDK / 旧 tests。

## 工件消费者

- `M6_REPEAT_MATRIX_ARTIFACT_DIR` 必须由调用方给出已存在目录。
- `consume_repeat_matrix_trace` 读文件字节：缺第 5 轮、缺 cancel/restart、自贴 round 标签均 `AssertionError`。
- CI 3.12：同一次 `pytest tests/` 写出工件 → `importlib` 再读同一函数 → `upload-artifact`（`if-no-files-found: error`）。不第二次跑该模块。
- py3.11 仍只跑 SDK，不计五轮。

## 验证（HEAD `c57ca9d`，含 origin/master `6aa76f6`）

| 环境 | 命令要点 | 计数 | 新模块 skip |
|---|---|---|---|
| 会话 uv 具名入口 | `pytest tests/test_http_qa_repeat_matrix.py` | 6 passed / 22 s | 0 |
| 无会话 `env -i` | 白名单 HOME/PATH/TMPDIR/工件目录，无 DELEGATE_* | 6 passed / 11.74 s；消费者 `[1,2,3,4,5]` sha=`c57ca9d` | 0 |
| 全量 pin `websockets==15.0.1` | flock 600 + timeout 900 | **505 passed, 3 skipped** / 260 s；wait 0.002 s | 0 |
| 全量 unpin（解析到 17.2） | 同上 | **505 passed, 3 skipped** / 282 s；wait 0.002 s | 0 |

3 个 skip 身份与历史相同：`test_aligner_integration.py:53/:62`（ForceAligner 模型未装）、`test_segmenter.py:208`（silero-VAD / onnxruntime）。没有 HTTP/ffmpeg/aiohttp 类 skip。

卡面记载的 `test_http_baseline` 两条 CLI 失败在本机这两次 Linux uv 全量**未出现**；独立补诊 `dlg-20261005-104647-038013` 仍在进行，**本卡不宣称 root 已修**，也没有把它们从套件里排除。

Hosted CI 尚未跑齐，不能用 Draft 检查绿代替 artifact 五轮。

## 主干

`git ls-remote origin refs/heads/master` → `6aa76f6`（相对基线 902 只多 `docs/maintainers/project-memory.md`，无 Win App flag）。已 `with-merge-lease.sh --record-merge` 合入本分支。
