# 卡 F 进度

## 2026-10-20 GPU 权限检测

- 当前阶段：implementing
- 本段结论：POSIX 下 `_check_admin` 按 `os.geteuid() == 0` 判断管理员；base 上 euid=0 断言红（`assert False is True`），修复后两例绿。
- 关键决策与已否决方案：按 `os.name == "nt"` 分支，不用 `except Exception` 兜平台差异。
- 下一步唯一动作：修标点/ITN 吞异常并让任务以 inference_failed 结束。
