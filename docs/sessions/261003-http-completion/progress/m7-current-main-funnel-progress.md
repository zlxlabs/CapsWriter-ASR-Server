# M7 当前主干集成验证进度

- Dispatch-Id：`dlg-20261005-015757-d65d06`
- 阶段：implementing → verification
- Base：`a550a2cfe455485a16fe39ca4c6e64f05aae5cdc`
- 正式主干：`4de4a7ffa44dfb50b48c252510927c4b2166cc77`
- 候选合并 HEAD：`16d7623e847765355c3a50fd41add31623333d6a`

## 2026-10-05 当前主干合入

- 已核 remote 身份与正式 merge commit，使用 `git merge --no-ff 4de4...` 正常合入；无冲突、无产品手工改动。
- `core/server/app.py`、`core/server/http_server.py`、`core/server/http_store.py` 的实际三点源变更全部来自该合并；SDK/App 未有本卡手工变化。
- 基线工具 `4e8` / `a550` / 当前 HEAD 去 docstring AST 严格相等；`git diff --check a550..HEAD` 通过。
- 合并后实际差异 5090 插入、65 删除，共 5155 行，超过卡面预算；这是正式主干带入的事实，未删改源/测试压预算。

## 验证结果

- 固定 `websockets==15.0.1` 的锁隔离全量：`487 passed, 3 skipped, 149 warnings`，退出码 0，224.76 秒。
- 3 个 skip 的具体原因：两个 ForceAligner 后端/模型缺失、一个 silero-VAD 模型或 onnxruntime 缺失；无 HTTP decode skip。
- 去 pin 实际解析 `websockets==17.2`：`487 passed, 3 skipped, 149 warnings`，退出码 0，226.00 秒；墙钟 409 秒含等待同一独占锁，3 个 skip 与固定版本相同。
- `tests/test_http_baseline.py` 的 11 个 producer contract case 随 full suite 实际执行，未复制 fake 同进程计数。
- 私有 `m7-synthetic-025` 跨进程 probe 通过：源 10075 字节，解码 PCM 16000 字节/0.25 秒；HTTP PATCH body 与源逐字节相等，WS v2 为 13677 字节 UTF-8 JSON 文本、0 binary frame；真实 ffmpeg argv、producer JSON/argv、源指纹和私有结果在仓外 0700/0600 报告中。

## 已知风险保持不变

- 原 B1 whole-buffer、B2 recovery cleanup order、普通 `MemoryError` 与 kernel OOM 的区别、fresh fixture ID 非修复均保持原 verdict；不实现 P2。
- 派发时主干基线 `gh api` 不可用，继承红无法判定；不把它改写为新红。
- 新证据详见 `m7-current-main-funnel-evidence.md`；旧 `pr64-canonical-risk-verdict.md`、`docs/guides/http-baseline.md` 与作者证据不改写。
