# 261006 #87 decode-failure 进度存档

## 里程碑 1：前置设计纳入

- 阶段：repairing
- 本段结论：从 `DESIGN_SOURCE_SHA` `8e93f7e49b07c8a25d199d0942dd7145b48f339b` 精确复制
  `docs/sessions/261006-issue-root-fixes/design.md` 与
  `progress/design-preflight-progress.md`（blob 与源提交一致），不改 Base。
- 下一步唯一动作：接口 TDD。

## 里程碑 2：公共迭代接口 TDD

- 阶段：repairing
- 本段结论：
  - 基线红（本树修前）：`pcm_chunks` 遇 `_END` 正常 return，新用例
    `DID NOT RAISE AudioDecodeError`。
  - 修法：`pcm_chunks()` 在 `_END` 且 `_reader_error` 非空时抛
    `AudioDecodeError(code=decode_failed)`；`CancelledError` 仍取消。
  - 合法 EOF returncode 0、stderr 警告 + 0、取消、finish 复抛均锁在
    `tests/test_audio_decoder.py`。
- 否决：把 stderr 非空当失败；垃圾输入冒充中途死亡。
- 下一步唯一动作：WS 整链。

## 里程碑 3：WS 整链

- 阶段：repairing
- 本段结论：
  - `ws_recv._receive_compressed_frame`：消费协程与末帧同时完成时先
    `consumer.result()`，已知失败压过末帧。不读解码器私有字段。
  - 真实 WS + 真 ffmpeg：等下一帧时 SIGKILL、正在 feed 时 SIGKILL、末帧同时到达
    均收到 `decode_failed`（不是 internal/connection_lost/decode_stalled）；
    正常 flac 仍拿 final。
  - 隔离树只拷新测试、base 实现不变：解码器用例 `DID NOT RAISE`；WS 等下一帧
    收到 `internal` / `RuntimeError: 压缩音频消费协程在末帧前结束`。
  - WS 故障文件连续 5 轮退出码：0/0/0/0/0。
- 下一步唯一动作：draft PR Refs #87。
