# 卡 F 进度

## 2026-10-20 GPU 权限检测

- 当前阶段：implementing
- 本段结论：POSIX 下 `_check_admin` 按 `os.geteuid() == 0` 判断管理员；base 上 euid=0 断言红（`assert False is True`），修复后两例绿。
- 关键决策与已否决方案：按 `os.name == "nt"` 分支，不用 `except Exception` 兜平台差异。
- 下一步唯一动作：修标点/ITN 吞异常并让任务以 inference_failed 结束。

## 2026-10-20 标点/ITN 失败上抛

- 当前阶段：implementing
- 本段结论：去掉标点/ITN 与简单拼接的 `except Exception` 吞错；标点桩抛错时 TaskHandler 产出 `error_code=inference_failed` 且 `is_final=False`。base 上该断言红（实际 `error_code==''` 并 WARNING 后 DONE）。
- 关键决策与已否决方案：不新增协议字段；沿用既有 `inference_failed`。否决交付原文本并标记降级。
- 下一步唯一动作：删除 pipeline 里恒为 False 的 `is_first_segment` 死参数。

## 2026-10-20 删除 is_first_segment 死参数

- 当前阶段：implementing
- 本段结论：pipeline 不再计算或传递恒为 False 的 `is_first_segment`；merger 仍用默认 False，首段靠空 `prev_tokens` 短路，合并逻辑不变。
- 关键决策与已否决方案：不改 `token_merger.py`（不在 Scope-Globs）；不改合并算法。
- 下一步唯一动作：把协议文档 HTTP 容量改成与 `http_job_budget` 一致。

## 2026-10-20 HTTP 容量文档

- 当前阶段：implementing
- 本段结论：协议资源起点不再写「8 个 QUEUED+RUNNING」；改为 HTTP+WS 共享 `max_tasks`，HTTP 预算 `http_job_budget(max_tasks)=max_tasks-WS_RESERVED_SLOTS`（当前默认 6）。`grep -n "8 个" docs/reference/protocol.md` 已无匹配。
- 关键决策与已否决方案：只改文档，不改协议字段与错误码词表。
- 下一步唯一动作：给 `_run_bare_probe` 传 `PYTHONUSERBASE`，`_wait_for` 失败带上 stderr。

## 2026-10-20 裸探针 HOME 隔离

- 当前阶段：implementing
- 本段结论：`_run_bare_probe` 显式传 `PYTHONUSERBASE=site.getuserbase()`，子进程在 `HOME=tmp_path` 时仍能加载用户 site；`_wait_for` 失败带 stderr。base 上该测试红（`未等到 HTTP_LISTENER_READY=`）。
- 关键决策与已否决方案：不拷贝父进程整份 environ（保持无 PI/DELEGATE 身份）。卡面 `HOME=/tmp/cw-home-probe python -m pytest ...` 会让父进程 conftest 丢 numpy，需父进程也带 PYTHONUSERBASE 才能收集测试。
- 下一步唯一动作：跑 Narrow-Verify 与全量测试，做 scope check，push。
