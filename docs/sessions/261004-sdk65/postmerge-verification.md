# SDK65 合并后主干验证（PR #66 合并产物）

- 日期：2026-10-04
- 被测 commit（冻结）：`b0818dc7859d1d8100e42f5c70cb75d34da422f7`
- 验证分支：`card/sdk65-postmerge-261004`（证据分支，不开 PR）
- 关联 issue：#65

## 1. 验证对象与基线关系

| 项 | 值 | 取得方式 |
| --- | --- | --- |
| 远端 `master` | `b0818dc7859d1d8100e42f5c70cb75d34da422f7` | `git ls-remote origin refs/heads/master` |
| 验证树 HEAD | `b0818dc7859d1d8100e42f5c70cb75d34da422f7` | `git rev-parse HEAD` |
| merge commit 父 1（master 侧） | `820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2` | `git log --format='%H %P'` |
| merge commit 父 2（PR #66 head） | `fee1f4e94d955d56a22409d302f8010c294592f6` | 同上 |

两个父提交均为 `b0818dc` 的祖先（`git merge-base --is-ancestor` 双向核实通过），
即本轮验证对象确为 PR #66 的合并产物，而非其任一父提交。

被测源码指纹（防止「测的不是合并后那份代码」）：

| 文件 | SHA256 |
| --- | --- |
| `sdk/capswriter_asr/client.py` | `eccec1a69b81c4a2360d33e15f0ddb8adffb85725dc93d41f8e3150a0863f6c7` |

## 2. 环境与命令

- 解释器：Python 3.12.3 / Python 3.11.15；`websockets` 17.2；pytest 9.1.1；pytest-asyncio 1.4.0
- 依赖清单：numpy、rich、websockets、colorama、pytest==9.1.1、soundfile、pytest-asyncio==1.4.0、
  aiohttp==3.14.3、httpx==0.28.1（两次运行完全一致）
- 一律 `uv run --no-project`，不读项目依赖、不污染仓库环境
- 外层硬截止 `timeout 400`（3.12 全量）与 `timeout 400`（3.11 窄测），均未触顶

## 3. 验证结果

| 运行 | 命令 | 结果 | 真实退出码 |
| --- | --- | --- | --- |
| Python 3.12 全量 | `uv run --no-project --python 3.12 … python -m pytest tests/ -q -p no:cacheprovider` | `453 passed, 3 skipped, 149 warnings in 249.21s` | `0` |
| Python 3.11 窄测 | 同依赖清单，`--python 3.11 … -m pytest tests/test_sdk_client.py tests/test_sdk_deadline_stage.py -q -p no:cacheprovider` | `34 passed in 18.05s` | `0` |

3.11 窄测与 3.12 全量在合并后主干上均通过，与 #65 主路径修复前「3.10/3.11 挂死」的现场记录形成对照：
合并产物未引入回归，3.11 下 SDK 相关用例全绿。

## 4. accept_precheck（原实现链复跑）

对 PR #66 的原实现链派发 `dlg-20261004-085556-e4760d` 复跑验收前置检查：

```
python3 <runtime>/scripts/delegate/accept_precheck.py \
  --dispatch-id dlg-20261004-085556-e4760d \
  --repo-path <本卡验证树> \
  --commit-range 820c3a2ee4fccc1b44187bd99c40cf99c16e1ca2..fee1f4e94d955d56a22409d302f8010c294592f6
```

结构化结论（`status = green`）：

| 检查 | 状态 | 依据（原文摘要） |
| --- | --- | --- |
| `scope` | green | commit-range 内 executor commits 的 7 个变更文件均匹配声明的 Scope-Globs |
| `verify_on_merged_main` | green | `453 passed, 3 skipped, 149 warnings in 220.97s`，exit_code 0；`main_sha_at_check = b0818dc7859d1d8100e42f5c70cb75d34da422f7` |
| `ci` | green（仅线索，不参与判定） | 合并后 1 个 push run（CI，run id 37192492431）conclusion=success；skipped checks 仅 `gate / notify`；工具自述查询分支与 `--commit-range` 端点不同源，仅供参考 |

产物 `accept_precheck.json` 保留在原派发目录下，未移动、未改写：

```
<delegate-state>/20261004-085624-resume-kimi-pi-dlg-20261004-074109-52b55e-dlg-20261004-085556-e4760d/accept_precheck.json
```

本卡未修改任何实现、测试或工作流来「凑绿」；两次 3.12 全量与一次 3.11 窄测均为独立复跑。

## 5. 本轮不能宣称的事

以下均为**已知未验证/未修复**项，本轮一律只上报不修，不得据此宣称 #65 全部根治或生产恢复：

1. **生产未验证**：未部署、未做下游 `VideoTranscriptAPI` 端到端验收。
2. **3.10 兼容问题仍在**：`except TimeoutError` 别名继承差异未修，3.10 套件仍有继承失败。
3. **3.11 默认预算下连接拒绝仍有 120s P2 有界延迟**（默认预算 120.145s 后才交付
   `AsrError(code="connection_lost")`），本轮接受不修，见 `root-cause.md` 与 `reviews/` 下两份 verdict。
4. **主干基线 CI 在派发时刻不可用**（`gh api request failed`），「继承红 / 新红」无法以基线判定；
   就本卡自身而言：新红 = 无（两套 pytest 与 accept_precheck 均绿）。

## 6. 结论

在冻结的合并 SHA `b0818dc7859d1d8100e42f5c70cb75d34da422f7` 上：

- Python 3.12 全量 `tests/`：**绿**（453 passed / 3 skipped，退出码 0）
- Python 3.11 SDK 相关窄测：**绿**（34 passed，退出码 0）
- 原实现链 accept_precheck：**green**（scope / verify_on_merged_main / ci 三项均绿）

即：#65 主路径修复已随 PR #66 进入主干且在 3.11 与 3.12 上可复现通过；生产恢复与 #65 剩余 P2
（3.10 兼容、默认预算 120s 有界延迟）不在本卡结论内，仍需单独处置。