阶段：implementing → 自测完成，等待主脑验收（C2 合并后需 retarget master 并重跑全量）
结论（计数已订正）：base `5134720` 上**7 组整体闭合**（2/4/5/6/8/9/12），1 与 10 组**部分**闭合，
合计 5 条真实缺口（1/3/7/10/11），逐条写在 `m6-qa-evidence.md` 覆盖表。
此前本文件开头把 1、10 与 7 组整体闭合混写成 9 个组号、又同时声称「只有 5 条缺口」，
自相矛盾；已按上述口径改正。`docs/sessions/261001-http-files/qa.md` 的 12 组「当前证明」
已逐组回填到真实测试与证据路径。
基线：`451 passed, 3 skipped`（3 skip 全是模型/VAD：ForceAligner×2、silero-VAD×1），
无 HTTP 解码类 skip；ffmpeg 在本机 `/usr/bin/ffmpeg` 存在。
决策与否决：复用 `tests/test_http_file_runner.py` 已入库的真实服务骨架（真 HTTP listener +
真 runner + 真 ffmpeg + 真识别子进程），不自造 harness；缺口测试集中放
`tests/test_http_qa_e2e.py`，不改动既有测试的期待值、不放宽任何超时、不改业务代码。
否决：用 mock dict 充当跨进程证据；把「未确认重发字节」伪报为 0；只改文档说已测；
把组 10 的格式矩阵扩成任意编解码组合（本卡只补重采样/降混这一类真实缺口）。
下一步唯一动作：主脑合并 C2 后，把本分支 retarget `master`、合入最新主干并重跑两套 websockets
全量，然后走主审/ready/merge。

## 全量验证（本卡分支 `c346892`+docs，两套 websockets 各跑一遍）

- `websockets==15.0.1`：`457 passed, 3 skipped, 163 warnings in 242.46s (0:04:02)`
- `websockets`（本机解析到 17.2）：`457 passed, 3 skipped, 163 warnings in 236.82s (0:03:56)`
- base `5134720` 同命令是 `451 passed, 3 skipped`，净增 6 条（5 个测试函数，其中重采样矩阵 2 个参数）。
- 3 条 skip 的身份（`-rs`）：`test_aligner_integration.py:53`、`:62`（ForceAligner 后端/模型未安装）、
  `test_segmenter.py:208`（缺 silero-VAD 模型或 onnxruntime）。**没有 HTTP 解码类 skip**，
  本机 `/usr/bin/ffmpeg` 存在，新增解码用例没有 skip 路径（缺 ffmpeg 时显式 assert 失败而不是冒充通过）。
- 新增文件窄跑 5 轮稳定：`6 passed` ×5（websockets 15.0.1 与 17.2 各再跑 1 轮，均绿）。

## 历史 commit 读超时观察（不掩盖为未发生）

原主干 `2919…` 那次并发 commit 读超时的根因仍未知，公开证据见
`fix55-merged-acceptance-evidence.md`。本卡按卡面要求对对应窄 case 各重复 5 轮：

```
tests/test_http_file_tasks.py::test_concurrent_http_commit_respects_budget
tests/test_http_file_tasks.py::test_concurrent_mixed_admission_respects_shared_total
tests/test_http_capacity.py::test_two_real_tcp_commits_race_for_last_storage_capacity
```

实测 5 轮全部 `3 passed`（7.75–7.86s/轮），**未复现**该读超时。RPC/worker 锁时序在本机
没有留下可分析的现场，因此根因仍判定为未知；没有延长任何超时、没有加自动重试来藏红。

## 已提交单元

- `tests/test_http_qa_e2e.py::test_real_ws_and_http_share_one_worker_without_key_pollution`
  （组 7）：同一个真 worker 子进程同时收到 `owner_kind=ws`（带真实 socket_id）与
  `owner_kind=http`（socket_id 为空）的段；空 socket 期间 HTTP 照常 DONE；断开的 WS 任务
  从 `state.tasks`/`connection_tasks`/`pending_segments` 消失且 worker 不再收到它的段，
  同窗口 HTTP Job 仍 DONE。运行：`1 passed in 5.39s`。

## 反向红验

四条注入相反实现的 scratch 红验全部拿到目标 `AssertionError`（脚本均不入库；保留位置见
`m6-qa-evidence.md`「红验记录」：`/tmp/m6-red/` 的 A/B 三支脚本，
`/tmp/m6-red-dlg-20261003-170302-cea070/` 的 C/D 两支 Python 脚本——后者原在仓库 `tests/`
下未跟踪，已移出仓库，仓库未跟踪面现为空）：

| 编号 | 注入 | 目标 | 实测 |
|---|---|---|---|
| A | `ws_recv` 断连清理不 pop `state.tasks`/`pending_segments` | 组 7 | `AssertionError: 等待「断开的 WS 任务从 state.tasks 移除」超时 (30.0s)` |
| B | runner 的 ffmpeg argv 去掉 `-ar 16000` | 组 10 ×2 | `assert 882000 == 320000`（44.1k 立体声）、`assert 160000 == 320000`（8k 单声道） |
| C | `HttpFileRunner.fail_job` 先发布缺段结果再失败 | 组 11 | `assert 'DONE' == 'FAILED'` |
| D | SDK 在 `connection_lost` 上自动重发 | 组 3 | `assert 2 == 1`（commit 真发了两次） |

红验 A 顺带暴露了本卡自己写的一条**恒真断言**（`TaskKey` 下标用错，`key[1]` 是 socket_id），
已修正后重跑 A 才拿到红——这正是「恒真断言等于没写」的实例。

## 交付物

- draft PR：https://github.com/zlxlabs/CapsWriter-ASR-Server/pull/63 （draft，执行器不置 ready）
- 分支 `card/http-m6-qa-261003`，base `5134720`，远端 tip 已用 `git ls-remote` 核对。
- 提交序列：`8337998` 组7 → `611b273` 组1 → `2f9e3ff` 组3 → `6266273` 组10 → `fa5b861` 组11
  → `a112db7` 恒真断言修正 → `c346892` 在场窗口兼容新版 websockets → `86eb4c1` 覆盖表与红验记录
  → `30f7474` 本文件补全量结果。

## 补正轮（只改文档与文件搬移，未改实现）

四项：
1. **红验脚本搬出仓库**：C/D 两支从 `tests/red_c_partial_publish.py`、`tests/red_d_auto_retry.py`
   **移动**到 `/tmp/m6-red-dlg-20261003-170302-cea070/`（未删除、未覆盖他任务脚本）；
   sha256 `7bb59214…d9fa4` / `cea436c8…6b654`，1217 B / 1374 B，搬运前后一致。
   并从新位置实跑一次：`2 failed`，红点仍是 C 的 `assert 'DONE' == 'FAILED'`（`status.state`
   断言处）与 D 的 `assert 2 == 1`（`len(recorder.dropped) == 1`，自动重发让被丢弃的 202 变成 2 个），
   证明脚本搬走后仍能复现红，而不是「pytest 不收集所以合规」。
   `git status --porcelain` 现为空，无未跟踪越界文件；未用 `git add -A`，未动其他文件。
2. **qa.md 契约事实回填**：12 组的「待测」契约/错误边界/未授权生产限制原样保留，只把
   「当前证明」换成实际测试与证据路径（新增用例 + 既有用例的文件:行），并保留未知项：
   组 1 未实跑红验、组 9 未按真实体量压测、组 10/12 的真实三平台与 ASR 质量基线未验证。
   明确写入：**假引擎 + 真子进程/真解码不等于真实 ASR 识别质量**。
3. **计数矛盾修正**：见开头「结论（计数已订正）」，qa.md 同步加了口径说明。
4. **m6-qa-evidence.md 事实订正**：组 1 的反向红验由「已验证」降为**未实跑**；
   红验脚本保留位置改为真实 /tmp 路径与字节/hash。

仅文档增量的四问：
- **踩坑**：第一次从仓库 `python -m pytest` 跑搬过去的红验脚本得到 `2 skipped`，红点是
  `未安装 aiohttp==3.14.3`——那不是脚本失效而是系统 `python` 缺 aiohttp（本仓库测试环境在
  `/tmp/*-venv`）。换本卡此前用的 `/tmp/c2-review2-systemd-venv/bin/python`
  （websockets 15.0.1、aiohttp 3.14.3）重跑才拿到真红。结论随环境变，不能只在顺手的环境里跑。
- **闸与绕过**：本次没有绕过任何测试、断言或闸——不改测试逻辑、不放宽断言、不加 retry/fallback，
  只改文档字句与文件位置；红验仍以相反实现得到 `AssertionError` 为准。
- **卡面偏差**：无。Scope 只含 3 个 md 文件；未新增/删除测试，未改业务代码，未重跑全量 suite，
  457 passed / 3 files 是上一轮历史实测，本次没有复跑，不当成本轮结果。
- **最贵一步**：从新 /tmp 位置实跑 C/D 两条红验（各起真实服务与识别子进程），是本轮唯一执行动作。
## M6R1-1：组 10 逐段 PCM 内容断言补强（只补测试观测，业务源码零变更）

根因：R1 独立复核发现两个重采样 case 只验长度/格式标签/`sample_count`；把 runner 的
`yield block` 换成 `yield bytes(len(block))`（同长度全零）后仍然 `2 passed`——
worker 实际收到什么内容从未被观测。评为 P2：这是**测试契约缺口**，不是生产 decoder 有 bug，
本卡也没有发现生产 decoder 的实际错误。

四项：
1. **producer fixture 观测字段**：`tests/harness/worker.py` 的 `received_task_record` 新增
   `data_sha256`（完整摘要）。原 `data_sha256_prefix` 保留不动——直接把前缀换成完整摘要会让
   既有的 `source_digest not in {…prefix}` 变成恒真断言。旧消费者（组 7、组 5 重启不重跑）
   语义不变。
2. **逐段内容比对**：`tests/test_http_qa_e2e.py` 新增 `decoded_pcm_bytes()`，在测试进程里用
   固定 argv 直接跑系统真 ffmpeg 解出整条 16 k mono f32 PCM（**不调用** `FileSourceDecoder`、
   不复用其状态）。两个 case 按每段实际 `offset` 切出参照片，逐段断言子进程真实收到的
   `Task.data` 完整摘要 == 参照片摘要，并断言段起点与上一段步长精确相接、`0 < overlap < samples`、
   参照片非全零（防「参考段也是零→恒真」）。
3. **红验 E（证明断言有约束力）**：注入 `pcm_chunks` 同长度全零 → 两个 case 都在
   `sha256(expected) == item["data_sha256"]` 处 `AssertionError`
   （`ad60dc8e…`/`bdb59e30…` vs `fec9afb5…`，后者是 96000×4 字节全零摘要）；还原后 `2 passed`。
   真修（断言 + fixture 字段）先 commit `7b42e45` 再注入，红验只临时改业务文件，
   回放脚本 `/tmp/m6r1-dlg-20261004-023118-2117b7/red_e_zero_pcm.sh` 自带
   「注入前必须无未提交修改 + grep 确认 + 还原后 git diff 复核」。
4. **真实环境整跑**：新文件窄 case 5 轮全绿；完整 `tests/` 四次整跑——
   裸 shell（`env -i` 白名单 HOME/PATH/TMPDIR/LANG）× websockets 15.0.1 与 17.2，
   以及真实 `systemd --user` 单元 `pi-m6r1-2117b7-full-pinned` / `pi-m6r1-2117b7-full-latest`
   各一次，四次均 `457 passed, 3 skipped`，3 条 skip 仍是 ForceAligner×2 + silero-VAD×1，
   **无 HTTP 解码类 skip**；未延长任何超时、未加自动重跑。单元用 `--collect`，收尾查询
   `ActiveState=inactive`、`MainPID=0`，`list-units 'pi-m6r1-2117b7*'` 为空，无残留进程。
   会话内已确认没有 `PROBE_*`/`CW_TEST_*` 变量，白名单环境不会改变测试分支。

仅本轮增量的四问：
- **踩坑**：第一版逐段断言里手滑写了一条 `a - b == a - (b)` 形式的恒真断言，自查时删掉换成
  `0 < overlap_samples < item["samples"]`；另一次是文档里写进一个 U+FFFD 乱码字符，
  `git grep $'\ufffd'` 扫出后修掉。教训：新增断言要逐条问「喂一个已知为假的输入会不会红」。
- **闸与绕过**：无绕过。红验 E 是先 commit 真修再注入、跑完立即还原（`git diff --quiet` 复核），
  没有整文件 checkout 吞掉未提交的真修；没有把长度/前缀比较冒充内容比较；没有为测试新造
  识别 pipeline、状态或账本；业务/SDK/runner/decoder 源码零改动。
- **卡面偏差**：无。Scope = `tests/harness/worker.py`、`tests/test_http_qa_e2e.py`、
  qa.md、m6-qa-evidence.md、本文件；`git add` 显式列路径，未用 `-A`；临时脚本只在唯一
  `/tmp/m6r1-dlg-20261004-023118-2117b7/`，仓库内无未跟踪文件；未创建任何 freeze；
  PR63 保持 stack C2 + draft，未 ready/merge/deploy；计数口径（7 组整体闭合 + 2 组部分）未回退。
- **最贵一步**：四次完整 `tests/` 整跑，每轮约 3 分 35 秒–3 分 47 秒（合计约 14 分半），
  是本轮主要墙钟成本；窄 case 5 轮合计不到 10 秒。
