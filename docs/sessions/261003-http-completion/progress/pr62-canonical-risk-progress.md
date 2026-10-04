# PR62 规范 finding 实测分诊 progress

- Dispatch：`dlg-20261004-170855-24eadd`
- H0：`c2818c5cba71ac86ddc0da1bee54538d34cdfe6b`
- 规范生产者基准：`b0818dc7859d1d8100e42f5c70cb75d34da422f7`
- 官方对象 A SHA：`fde59a980f9bdd07d8a9fe677dbe057dd459a0ed695029eb87fa482f38821c43`（11408 bytes）
- 未改应用代码 / 测试 / SDK / 配置 / 依赖 / 旧报告
- 未自签 disposition / PR / ready / rerun / GitHub comment / merge

## 做了什么

1. 读审查纪律与 P1 两问；冻结 H0 实测，不跟 master 浮动
2. 私有脚本（目录 0700、文件 600）对官方 5 条做物理复现：
   - A1 正常 unlink 一次 + owned `PermissionError` 一次 + 假 ROLLBACK 红验
   - A2 cleanup-inflight 双 `stop` 子进程一次
   - A3 本机 HTTP sqlite 规模 + 8/32/128 行 cleanup 成本
   - A4 真实 `ProbeRun.start` Popen env 哨兵；A5 原 handle fd
3. 新两文档本 progress 与 `reviews/pr62-canonical-risk-verdict.md`

## 证据

私有目录（不入库）=`dlg-20261004-170855-24eadd/evidence/`：

- `a1-persist.json`
- `a1-refuted.json`（整条 A1 断言物理证伪）
- `a2-stop-reentry.json`
- `a3-scale.json`
- `a4-a5-probe.json`
- 脚本：同 dispatch 的 `scripts/run_a1.py`、`run_a2.py`、`run_a3.py`、`run_a4a5.py`

## 结论摘要

- A1 **refuted**（非 P1）：两条路径 EXPIRED 均持久，GET 410，partial SHA 保持
- A2 **P2 接受不修**：双 stop 可绕过 task 等待，无损坏，rc=0
- A3 **P3**：生产 HTTP 未部署；当前 max jobs=9；128 行 cleanup 3.4ms
- A4 **P3**：naked 确继承 91 个额外键；不经 HTTP 外泄；systemd launcher 本环境 unknown
- A5 **nit**：多 1 个 fd，进程退出回收
- `failure-visibility: p2-only`

## 未做

不扩大 cold review、不恢复 09 资格、不修代码、不记账。
