# 复核进度

## 里程碑 1：发现 1–5

- 当前阶段：已完成 1–5 条代码追踪与其中 1、4 条最小运行探针。
- 本段结论：1–5 均为 CONFIRMED；1–3、5 的真实触发条件已按 I/O 队列与超时阈值量化，4 用不同权重双后端桩复现。
- 关键决策与已否决方案：不启动识别模型；使用真实 `HttpIoWorker` 配合阻塞函数验证队列超时，HTTP 文件提交路径只做代码追踪。
- 下一步唯一动作：复核 6–10 条并补充对应探针证据。

## 里程碑 2：发现 6–10

- 当前阶段：已完成 6–10 条代码追踪与 Store、proxy、SDK、WS 状态、Linux GPU 权限探针。
- 本段结论：6–10 均为 CONFIRMED；过期上传探针复现 16 GiB 永久预留，70 行扫描实测 70 次 stat；HTTPX 默认超时与 Linux `windll` 失败均在本机实测。
- 关键决策与已否决方案：SDK timeout 的后果限定为提交结果不确定；恢复文件仍可显式续接，不把它扩大解释成任务或源文件丢失。
- 下一步唯一动作：复核 11–15 并补齐最终汇总与严重度裁决。

## 里程碑 3：发现 11–15 与收口

- 当前阶段：15 条复核正文、实测证据、触发条件、修复方向及汇总表已完成；准备跑接收判据并推送。
- 本段结论：11、12、15 CONFIRMED，13 REFUTED，14 PLAUSIBLE；累计 13 条 CONFIRMED、1 条 REFUTED、1 条 PLAUSIBLE。4 小时合成结果的生产 JSON 编码基准在 960 段约 543.9 MB/5.135 秒，在最短 5 秒段长的 2,880 段约 1.63 GB/16.622 秒；固定段结果量时段数翻倍、编码字节约增至 4.1 倍。
- 关键决策与已否决方案：未启动真实 ASR/VAD 模型；全量 pytest 的唯一模型用例通过 `-k not test_vad_pipeline_smoke` 排除。`python -m pytest tests/ -q -k 'not test_vad_pipeline_smoke'` 于 401.92 秒被中断，报告 **126 passed / 2 skipped / 1 deselected / 3 failed / 57 warnings**；三条失败均为 `tests/test_http_cleanup.py` 的 systemd-unit 探针：`test_fatal_cleanup_exits_process_and_reaps_children` 观测 unit `ActiveState=failed, ExecMainStatus=1` 且未产出报告；`test_normal_sigterm_still_exits_zero` 120 秒未见 `ready`（unit 显示 result success）；`test_http_startup_failure_exits_nonzero_without_hanging_worker` 120 秒未见 `pre_http_assembly`。未在本卡改动这些测试或生产代码；基线未提供，继承/新增红不能判定。
- 下一步唯一动作：完成接收与 scope 检查，提交本里程碑并推送派发分支。
