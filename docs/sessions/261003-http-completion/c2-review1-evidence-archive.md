# C2 review1 证据归档（仅保全）

采集日期：2026-10-04。本文只记录当时仍存在的归档对象，不构成新审查或因果判断。

## 匿名清单

| 匿名指纹 | 对象 | 条目数 | 字节数 |
| --- | --- | ---: | ---: |
| `103e83f0ef7e` | 剩余临时证据快照：194 个普通文件、79 个目录、0 个符号链接 | 273 | 3,230,678 |
| `bbf0db66923d` | 父报告与原子状态 envelope 快照 | 2 | 126,082 |

完整逐文件 SHA-256 与 JSON 编码相对路径保存在私有归档清单中；上表指纹只是清单哈希前缀。

## 历史摘要字段计数

只汇总现存摘要中已有字段：`error_type` 共 42 条，类别计数为 PermissionError 20、SystemExit 8、ValueError 5、AssertionError 2、NameError 2；AttributeError、CancelledError、HttpServerError、ReadError、RuntimeError 各 1 条。`HTTP 409 / decode_failed` 结果 4 条，与上述 `error_type` 记录不重叠。

父报告快照为 12,557 字节。历史摘要声称的 SHA-256 与当前快照不一致；谁在何时造成变化仍未知，留待只读顾问核对时间线与契约。此归档不恢复或解释该差异。

## 保全边界

- 归档只包含采集时实际存在的字节；原目录已移入私有归档，副本与移动后的原件均逐条匹配快照清单。
- 归档完整仅表示相对于本次快照逐字节保存，不证明更早历史从未变化。
- 不改原报告、envelope、任务卡、verdict、进度记录或历史摘要；不重写原结论。
- 不执行新审查、不增加 review round，也不据此宣称 No-P1-floor 达标。
