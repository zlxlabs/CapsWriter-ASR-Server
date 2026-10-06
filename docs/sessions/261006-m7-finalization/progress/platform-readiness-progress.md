---
lane: http-integration
milestone: M7
card: platform-readiness
stage: planning
---

# M7 三平台隔离入口只读准备 — 进度

## 当前阶段

planning / 只读准备（`local-docs-v1`）。本卡不启动服务、不实施基线。

## 本段结论（第一段：环境事实）

- 三平台连接实时结果：Linux 本机直接可查；macOS 隔离机（Mac mini）SSH 可达；Mac Studio 经既有跳板 SSH 可达；Windows 计划任务主机 SSH 可达。四处本次都取得了实时读数，没有依赖历史收据代替。
- 隔离源码：Linux、macOS 隔离机、Windows 三处都存在 SHA 前缀 `492fe19` 的隔离树；Mac Studio **没有** M7 隔离树，只有生产 clone（SHA 前缀 `d251618`）。
- 运行时：Linux 隔离 venv Python 3.12.3、macOS 隔离机 venv 3.12.15、Windows 隔离 venv 3.12.12 均在位。macOS 隔离机的系统 `python3` 是 3.9.6，不能当隔离运行时用。
- 模型缓存：Linux 与 macOS 隔离机读数为非空（约 544 MB 权重）；Mac Studio 生产 clone 下非空；**Windows 读数未定，记 unknown**。
- 样本与参考稿：Linux、macOS 隔离机、Windows 三处都有同一批已授权匿名样本（3 组 WAV/MP4）与 gold 组（5 个格式文件）；MP3/AAC/M4A/Opus 四格式各 1 份且非空，参考稿 1 份非空。Mac Studio 两者皆无。
- 端口：三处已抽样候选高位端口本次均空闲，属带采样时间的准备线索，不是承诺。

## 关键决策

1. **历史收据只作背景，不作运行时资格。** Windows 那台机器历史 health 曾报 `model=paraformer`，但本次探针读数未定，就写 unknown，不用历史数字补齐。
2. **读数缺失不写零、不写「不存在」。** Windows 模型缓存探针返回 0，但 PowerShell 5.1 递归不跟随 reparse point，一次改用 junction 探测的尝试无可解析输出，因此判定为 unknown 而非缺失，并记下一步复核命令方向。
3. **不新增采集工具。** 只读探针是一次性本地脚本 + 远端 stdin 执行，留在本地私有目录，不入仓、不产生第二消费者；对外只落两份文档。
4. **公开文档不含宿主路径/IP/用户名/私样本名/正文/哈希。** 主机一律以平台标签（Mac Studio / Mac mini / Windows 计划任务主机）出现。
5. **端口空闲写成采样线索**，基线卡执行时必须重新抽样。

## 已否决方案（延续并强化）

- 用生产动作换 readiness：启动服务、装依赖、下模型一律否决。
- 临时凭据/网络绕行：SSH 不通就换地址、绕认证一律否决；本次四处都走既有主机别名或既有地址，无绕行。
- 私数据输出：打印样本路径、媒体哈希、转写正文一律否决。
- 用旧平台数据背书新源码：`492fe19` 树的存在不等于它是共同正式合并 SHA。
- 读数缺失当零：Windows 模型缓存这一项就是靠这条纪律才没写成「缺失」。
- 凭「计数相同」推「集合相同」：三机样本计数一致只能说明格式齐备，不能推断内容同一。
- 新建基线框架或采集工具入库：无第二消费者，不建。

## 下一步唯一动作

把本清单交主脑，由主脑决定是否派真实 M7 基线卡；本卡到此为止，不自行测量、不自行部署。Windows 模型缓存复核可由后续基线卡顺带完成，也可由主脑单独派只读复核。

## 与卡面的偏差

- SSH 实际连接次数：Mac mini 2 次、Mac Studio 4 次、Windows 3 次，共 9 次，超过卡面 ≤6 次的建议上限。超的原因是 Mac Studio 首次探测的准备根猜错（探测了一个不存在的根），以及 Windows 端两次 PowerShell 参数传递失败重发。多出的连接都是只读、无副作用，但应记为偏差。
- Windows 的 junction 探测没有返回可解析输出，因此该项留下 unknown 而非读数。这是本卡唯一没有闭合的白名单项。
