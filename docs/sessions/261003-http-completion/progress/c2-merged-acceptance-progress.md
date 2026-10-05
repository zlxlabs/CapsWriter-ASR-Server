# C2 合并主干正式验收进度

## 阶段

`verifying`；本卡是 tests-docs 窄验收，不承担产品实现、旧 unknown 诊断或 M4 总体
完成裁决。

## 已完成

- 核对 HEAD、`origin/master`、PR62 merge/head/tree：正式主干为 `4de4a7f`，与 candidate
  `7a3a964` 同 tree；主干 CI run 37252990501 三 job 全 success。
- 两套 Python 3.12 标准 uv 全量 suite 均在共享 flock 内完成，固定 ws15 与最新 ws
  各 `476 passed, 3 skipped, 149 warnings`，排队/执行耗时已写入正式 evidence。
- 当前树六文件 source probe 通过；真实裸子进程、TCP/ffmpeg/PCM producer、SQLite
  重开、EXPIRED/410、终态清理、replay、fatal/TERM/HTTP-disabled、SDK watchdog 的
  代码位置与测试锁定关系已写入正式 evidence。
- 仅新增本卡 scope 内两个文档；未改应用、SDK、tests、workflow、config、旧文档、
  GOALS、账本或生产服务。

## 下一步

1. 只 add 两个显式文档路径并做窄提交、push 当前 card 分支。
2. 在该提交之后仅运行一次 native `accept_precheck`，保留原始 JSON/status/main_sha/
   CI identity；`git diff --check HEAD^ HEAD` 作为 Verify-Command。
3. 写 `$DELEGATE_REPORT_PATH` 完整派发报告，报告含 suite、CI、precheck、继承红不可判定
   和未知项；不自判 overall M4Done。

## 未知与边界

- 派发时主干基线为 `gh api request failed`，继承红不能判定；当前实际三 job 与本地
  suite 没有新红。
- Restart-on-failure 生产部署重启、真实模型质量、生产认证未测；不把 stub engine、
  代码形状或旧私有 JSON 当作证据。
- 首次独立 source probe 因临时脚本路径未加入 repo `sys.path` 启动失败；修正后
  `source_probe=pass files=6`。该非 suite 失败不改产品，不隐藏在 suite 绿里。
