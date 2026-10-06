# M7 可信短素材来源与状态

## 当前结论

- 状态：`blocked`，本卡没有交付可消费的音频、参考稿或六格式派生物。
- 任务边界：只准备独立素材，不启动识别模型、不做 HTTP/WS 基线、不宣称 M7 完成。
- 旧私有素材和旧字幕仍是 `unverified` 背景，未被本卡复用。

## 来源候选与失败点

- 候选来源：Mozilla Common Voice 中文（中国大陆），`cv-corpus-21.0-2025-03-14`；
  数据行约定包含 `path`、`sentence`、`locale`、投票校验字段，音频为真人录音。
- 选择理由：可按单条短 MP3 绑定音频 ID 与官方数据行；AISHELL-1 的公开音频按
  超过 5 MB 的整包提供，不符合本卡单次小素材预算。
- 实际获取：私缓存脚本只请求一条 `test` 行，30 秒超时；TLS 在响应前报
  `UNEXPECTED_EOF_WHILE_READING`，退出码 1。
- 因未收到数据行和音频字节，音频 ID、原始 label bytes、label ID 绑定均未核实，
  不能把搜索摘要或数据集说明当作 ground truth。

## 资产状态

| 资产 | 状态 | 说明 |
| --- | --- | --- |
| 原始真人音频 | 缺失 | 未下载到字节，未生成替代物 |
| UTF-8 reference/raw label | 缺失 | 未取得官方数据行 |
| WAV / MP4 / MP3 / AAC / M4A / Opus | 未生成 | 没有可合法派生的同源输入 |
| manifest / 转换收据 / ffprobe 收据 | 未生成 | 避免产生恒真或伪成功证据 |

## 后续边界

- 最短解阻输入：提供一条可访问的公开音频 URL 及其官方数据行（固定版本、音频
  ID、人工标签），或确认允许在来源网络恢复后重新执行一次获取。
- 解阻后仍需保存原始 label bytes 与规范 reference，再由同一原 WAV 一次 pipeline
  生成六格式并逐一 probe；格式转换不等于 PCM bit-identical。
- 本状态不构成模型加载、质量数字、性能数字或 M7 完成结论。
