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
