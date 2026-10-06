# 独立审查 verdict：PR #70 SDK 时间约束，第 2 轮（覆盖面）

failure-visibility: clean

- 审查对象：`b0818dc7859d1d8100e42f5c70cb75d34da422f7..a09e960def66314fd02e26cbd82d794bf8f8976e`
- H0：`44394ce72b3cb4f5f860ca2b7315da270198bfd0`
- H1：`a09e960def66314fd02e26cbd82d794bf8f8976e`
- 风险等级：internal（仓内 `AGENTS.md` 声明 `risk-tier: internal`）
- 本轮只新增本文件，没有改实现，也没有把实现提交拣进审查分支
- 解释器：CPython 3.11.15（`uv` 发行的 3.11，不是 GitHub hosted 的补丁号）。依赖装在 `/tmp/sdk-review2-venv311`，没有写本仓 `.venv`

## 结论

H0 到 H1 只做了已登记的那一件事：两条 Python 3.11 的 `pytest-targets` 从三个文件名改成同一个 `tests/test_sdk_*.py`。没有新抽象，没有新的状态或退路，枚举和 glob 没有同时活着。

在 3.11.15 上，这个 glob 由 bash 展开成 5 个文件。`websockets==15.0.1` 和当天解析到的 `websockets==17.2` 各跑一遍，都是 55 passed、退出码 0，输出里没有 skipped。默认预算连接拒绝连跑，两次 websockets 各 3 次，调用耗时 0.01–0.02 秒，墙钟都小于 1 秒。

卡面转来的覆盖缺口不升成 P1，也不记 P2。`tests/test_file_result_contract_e2e.py` 不走 SDK。`tests/test_e2e_sdk_server.py` 会调用 SDK，但显式传了 `deadline_total=240`，锁不住默认预算；它在 3.11 上是绿的，3.12 维仍跑整个 `tests/`。

## H0..H1 四问

对照 `git diff 44394ce72b3cb4f5f860ca2b7315da270198bfd0 a09e960def66314fd02e26cbd82d794bf8f8976e`：只改了 `.github/workflows/ci.yml` 和进度档，19 行增、6 行删。

1. 只修了已登记的 P2。两条 3.11 的目标从 `tests/test_sdk_client.py tests/test_sdk_deadline_stage.py tests/test_sdk_no_wait_for.py` 换成 `tests/test_sdk_*.py`。3.12 仍是 `tests/`。`client.py`、测试、公式、`pyproject.toml`、README 在这一段里没有改。
2. 没有新增抽象。glob 是原来那一格字符串的替换，没有新接口或包装层。
3. 没有新增状态、事实源或 fallback。进度档只记录这次替换。
4. 没有留下双路径。冻结树上 `pytest-targets` 只出现在 `ci.yml`：两条 3.11 都是 glob，3.12 是 `tests/`。旧的三文件枚举不再是会执行的选择器。

## glob 实际展开

在 H1 检出上用 `bash --noprofile --norc -eo pipefail` 执行 `printf "%s\n" tests/test_sdk_*.py`，得到 5 个文件：

```
tests/test_sdk_client.py
tests/test_sdk_deadline_stage.py
tests/test_sdk_no_wait_for.py
tests/test_sdk_samples_total.py
tests/test_sdk_transcode_track.py
```

workflow 里的命令是未加引号的 `python -m pytest ${{ matrix.pytest-targets }} -q`。同一 shell 形态下，pytest 进程的参数已经是上面这 5 个路径，不是字面量 `tests/test_sdk_*.py`。

把星号加引号，或换一个匹配不到的字面量 `tests/test_sdk_NO_SUCH_*.py`，pytest 都是退出码 4，并打印 `ERROR: file or directory not found`。当前这行不会在「一个测试都没收集到」时退出 0。

`tests/` 里调用 `transcribe_file` 的文件共 5 个。glob 覆盖其中 3 个：`test_sdk_client.py`、`test_sdk_deadline_stage.py`、`test_sdk_samples_total.py`。另外两个：

- `tests/test_e2e_sdk_server.py`：真的调用 `capswriter_asr.transcribe_file`，对面是假服务端和 proxy。调用处写了 `deadline_total=240`。设计写明显式 `deadline_total` 走不到默认预算重锚定，锁不住这条不变式。
- `tests/test_model_routing.py`：SDK 用例在建连前就因模型不匹配抛错。本轮没有跑这个文件。它不经过 upload / deadline_watch。

`tests/test_sdk_transcode_track.py` 不调用 `transcribe_file`，但在这 5 个文件里，测的是 ffmpeg 参数。H0 的三文件枚举没把它和 `test_sdk_samples_total.py` 算进去；H1 的 glob 把它们算进去了。

`tests/test_file_result_contract_e2e.py` 用测试夹具自己发 WebSocket，不导入 `capswriter_asr`。它是服务端文件结果契约，不是 SDK 生产路径。

## 不变式的本轮实测

测量都在 H1 的临时 worktree 里，Python 3.11.15。pytest 9.1.1，pytest-asyncio 1.4.0，httpx 0.28.1。ffmpeg 6.1.1 在 PATH 里，所以这两个文件顶部的「没有 ffmpeg 就 skip」没有生效。

| 不变式 | 本轮结果 |
| --- | --- |
| I1 生产包没有 `asyncio.wait_for` 调用 | 支持。自写 AST 先对「只提到名字、没有调用」得到 0，对植入的一次调用得到 1，然后扫 `sdk/capswriter_asr/` 的 6 个 `.py`，`WAIT_FOR_CALLS 0`。包内 `asyncio.timeout()` 也是 0。文本里剩下的 `wait_for` 只在注释。 |
| I2 默认预算、不传 `deadline_total`，5 秒内 `connection_lost` | 支持。见下面六次计时。 |
| I3 超时仍是 `AsrError(timeout)`，默认路径带「自动预算」 | 支持。`test_default_path_timeout_names_auto_budget` 在收集结果里，调用不传 `deadline_total`，断言码是 `timeout`、消息含「自动预算」。它含在 55 passed 里。 |
| I4 3.11 两个 websockets 维真跑，3.12 是全量 `tests/` | 3.11 两维都跑了，不是 skip。3.12 只核对了冻结 workflow：`pytest-targets: "tests/"`。本轮没有重跑 3.12 全量。 |
| I5 `requires-python >= 3.11`，无双路径，无 `asyncio.timeout()`，不改公式 | 支持。`sdk/pyproject.toml` 是 `>=3.11`；README 已写成 3.11，冻结树上不再出现 3.10。`sdk/` 下没有 `sys.version_info`，也没有 `asyncio.timeout`。`git diff` 里 `_auto_budget` 的改动行数是 0。 |
| I6 取消向上传播 | 支持到测试锁的粒度。`test_caller_cancellation_propagates_and_reclaims` 在 55 条收集结果里，窄测退出码 0。本轮没有另写一篇等待机制说明。 |

收集命令在 H1 上给出 `5/55 tests collected`，点名的是：

- `tests/test_sdk_no_wait_for.py::test_sdk_package_never_calls_wait_for`
- `tests/test_sdk_client.py::test_default_budget_connection_refused_returns_in_seconds`
- `tests/test_sdk_deadline_stage.py::test_default_path_timeout_names_auto_budget`
- `tests/test_sdk_client.py::test_caller_cancellation_propagates_and_reclaims`
- `tests/test_sdk_client.py::test_send_failure_surfaces_as_connection_lost`

窄测命令与 CI 相同的未加引号 glob，另加了 `-ra --tb=line` 以便看见 skip。两次都没有 skip 行。

- `websockets==17.2`：55 passed，45.91 秒，退出码 0
- `websockets==15.0.1`：55 passed，23.30 秒，退出码 0

I2 计时（pytest `--durations` 的 call，以及 `/usr/bin/time` 的墙钟）：

| 轮次 | websockets | call | 墙钟 | 退出码 |
| --- | --- | --- | --- | --- |
| 1 | 17.2 | 0.01s | 0.52s | 0 |
| 2 | 17.2 | 0.01s | 0.40s | 0 |
| 3 | 17.2 | 0.01s | 0.35s | 0 |
| 1 | 15.0.1 | 0.02s | 0.34s | 0 |
| 2 | 15.0.1 | 0.02s | 0.39s | 0 |
| 3 | 15.0.1 | 0.02s | 0.39s | 0 |

用例正文是 `await transcribe_file(audio_path, url)`，参数里没有 `deadline_total`。

红验在基线 `b0818dc` 的临时 worktree 上做，用完由 `scratch-worktree.sh` 拆掉。

- 只把 H1 的 `tests/test_sdk_no_wait_for.py` 放进去。第一次用没装 numpy 的环境，停在 `conftest` 导入，退出码 4，这次不作数。换上同一套 3.11 依赖后：1 failed、1 passed。失败点是生产代码里的两处调用，`sdk/capswriter_asr/client.py:516` 和 `:360`。旁边那条「植入一次调用必须被扫到」的自检是通过的。同一套 AST 脚本在基线上报 `WAIT_FOR_CALLS 2`，行号相同。
- 只把 I2 新函数追加进基线的 `tests/test_sdk_client.py`（追加前该文件没有这个函数；追加后定义在第 1148 行）。`timeout -k 5 15` 结束时 pytest 退出码 124，没有 passed。同一函数在 H1 上 0.01 秒通过。15 秒大于断言上限 5 秒。

被点名的两个文件在 3.11.15、`websockets==17.2` 上一起跑：4 passed，2.08 秒，退出码 0，没有 skip。数量对得上：e2e 1 条，文件结果契约 3 条。

## 工具标注对照

P1 门槛按 internal：数据丢失、静默出错、崩溃、越权、损坏他人数据。两问都成立才是 P1。

| 条目 | 工具标注 | 本仓判定 | 真实使用会触发吗 | 后果能否接受 |
| --- | --- | --- | --- | --- |
| glob 未包含 `tests/test_e2e_sdk_server.py` 与 `tests/test_file_result_contract_e2e.py` | 卡面写明 OCR 对 H0..H1 的 status=reviewed。卡面没有附 major/minor 字面量 | 不构成 P1，也不记 P2 | 会触发的是「3.11 这条 CI 不跑这两个文件」。bash 展开的 5 个名字里确实没有它们。文件结果契约不导入 SDK。e2e 会调用 SDK，但传了 `deadline_total=240`；在 3.11 上实测 4 passed / 2.08s | 能接受。I1、I2、I3、I6 的锁都在已经跑过的 55 条里。3.12 维的目标仍是整个 `tests/`。当前没有一条被藏起来的红 |

`ci.yml` 注释写的是「全部 `tests/test_sdk_*.py`」，并点了这 5 个词干。进度档写了「全部 SDK 测试」。以 workflow 里真正执行的那一格为准，范围就是这 5 个文件。

## 本轮没有当成结论的东西

全范围 `ocr-review`（`b0818dc..a09e960`）跑了约 12 分钟：进程停在 poll，stdout 一直是 0 字节，stderr 只有 `OCR failover progress: leg=primary event=start`。没有形成 envelope，随后有界中止。这不是 reviewed，也不是 clean，不写入上面的 `failure-visibility`。表里的那条用的是卡面已经给出的 finding，严重度按本轮在 3.11 上的运行重新定。

3.12 全量 `tests/` 本轮没有重跑。冻结 diff 是 8 个文件、335 行增、14 行删，高于目标 250、低于硬限 600；本卡不改实现，不因此升降级。
