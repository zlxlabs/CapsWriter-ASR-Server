# M7 剩余输入上下文

**结果：failed（输入有部分落实，Windows 推理环境仍缺 `cache` 与 `env` 目录）。** 本记录补充确定性输入，不代表 M7 三平台验收，也不替换 Task10 的 partial 记录。基线为 `492fe191e3f9568ea178b61970c732c9d37c4e29`。

## Windows 既有目标

- 从既有平台目标元数据取得原生目标，仅执行一次只读连接；回包确认操作系统为 Windows，且卡面指定的准备根目录存在。
- 同一根下 `cache`、`env` 子目录均不存在，因此当前没有可交给续测 actor 的推理环境目录。连接当时可达；不推断后续开机状态，不启动服务或模型，不读取模型内容。
- 原生目标标识和读取证据仅保存在派发私有上下文：`dispatch-local:private-context.json`。该文件权限为 `0600`，派发目录权限为 `0700`。

## 231.552 秒既有素材

- 原授权 Linux 素材目录中的 `full.wav`、`full_x3.wav` 和 `000_video.mp4` 均存在；仅读 WAV 头元数据，`full_x3.wav` 时长为 **231.552 秒**，与既有短素材记录相符。
- 私有上下文保留三个文件的本机消费路径和文件元数据；未读音频内容、未计算音频哈希、未重建 fixture。续测 actor 可直接消费 `full_x3.wav`。
- 既有风险记录：[PR64 canonical risk verdict](reviews/pr64-canonical-risk-verdict.md)（固定对象 `2b5afec637af00da9524534743d6a34002e8afb4`）。

## WeNet / AISHELL 可信音文绑定

- 在 WeNet 官方仓库修订 [`d17059667d6afe0680d19b3a4948ab825ef25105`](https://github.com/wenet-e2e/wenet/tree/d17059667d6afe0680d19b3a4948ab825ef25105/test/resources/dataset) 的小型测试资源中，`data.list`、`wav.scp`、`text` 为同一条 `BAC009S0724W0121` 记录；manifest 音频 basename 指向 `aishell-BAC009S0724W0121.wav`，两处参考文本字段逐字相同。官方音频资源小于 5 MiB；本次只取大小元数据，未下载音频字节。
- WeNet 的 [AISHELL recipe](https://github.com/wenet-e2e/wenet/blob/d17059667d6afe0680d19b3a4948ab825ef25105/examples/aishell/s0/run.sh) 指向 OpenSLR/33 的 AISHELL 音频与 transcript prep。官方 [OpenSLR SLR33 页面](https://www.openslr.org/33/) 标注 Apache 2.0、学术用途免费，并说明文本由专业人员人工转写、准确率超过 95%。此绑定来自官方 reference 文件，不使用本机模型识别结果；全文只留在私有上下文，不进入本文或 Git。
- 私有上下文保存精确 manifest/reference 行的编码字节、官方 URI、修订、许可与 provenance 类别，供原续测 actor 复用。未下载 15 GB 语料包或新开其他候选。

## 续测边界

续测 actor 可复用私有上下文指向的现有 Windows 目标、231.552 秒素材和 WeNet/AISHELL fixture。Windows 准备根下缺少 `cache` 与 `env`，须将其作为现存输入缺口处理；此记录不构成平台测量结果或 M7 验收通过。
