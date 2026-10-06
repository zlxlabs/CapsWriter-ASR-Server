# M7 生产样本与 HTTP/WS 对比工具

素材、manifest、脚本和 Python 3.12 虚拟环境仅在开发机私有目录 `~/.cache/caps-m7-samples-261006/`，不入仓。录音与 VTA 旧转写从 n305 只读复制；manifest 为 `manifest.json`，记录每个已复制文件的远端源路径、字节数和 SHA-256。short 没有对应的 VTA JSON，因此未复制。

| 样本 | 音频时长 | 音频字节数 | 音频 SHA-256 | VTA 旧转写字符数* |
|---|---:|---:|---|---:|
| short | 38.762667 秒 | 650,577 | `e332ddc68011fb27a5aef03ef161816c07b24e04c646d18af7d0520bbbb63f4f` | 186 |
| mid | 1,220.437146 秒 | 37,355,469 | `178b89aa58875f51be0cb4196a638a3d9e6d7ec31ae28ed16e3b1a9200a307fa` | 4,047 |
| long | 3,675.071979 秒 | 61,840,523 | `6789d4ee88fcd5f1af1702e82a237840f54032b0ca48fc89eddbfdffa29cf05f` | 16,777 |

\* Python Unicode 字符数，计数前不剥除空白或标点；不展示或转述转写正文。mid、long 的 VTA JSON 也已复制。

## 用法

从仓库根目录以虚拟环境 Python 运行（参数依次为 WS URL、HTTP URL、样本名、输出目录）：

```sh
~/.cache/caps-m7-samples-261006/venv/bin/python ~/.cache/caps-m7-samples-261006/compare.py 'ws://HOST:6016' 'http://HOST:6017' short ~/.cache/caps-m7-samples-261006/results
```

脚本默认执行 SDK WS 编码；HTTP 依次运行 `python -m capswriter_asr http submit`、每 15 秒 `status` 轮询至 `DONE`、`result`。每条路径记录墙钟秒数、`text_accu` 字符数、末段结束时间估值及其与 `ffprobe` 音频时长之差。SDK 只提供 token 起点，所以末段结束时间按 `timestamps[-1] + 0.5`（SDK SRT 收尾规则）估算；空时间戳时记为 `null`。识别文本分别写入 `<样本>.ws.txt`、`<样本>.http.txt`，汇总写入 `<样本>.json`。

## 差异率与本地自检

统一将文本转小写并去掉空白及 Unicode 标点；用精确字符级 Levenshtein 编辑距离除以**参照文本**规范化后的字符数。参照方向固定为：HTTP 对 WS（WS 为参照）、HTTP 对 VTA（VTA 为参照）、WS 对 VTA（VTA 为参照）；空参照的差异率为 `null`。脚本 `--self-test` 只执行纯函数、不连接服务：

```text
short_vta_vs_itself=0.000000
short_vta_vs_first_half=0.502994
```

第二项将规范化后的 short VTA 文本截为前半段，距离率约为 0.5。生产实例未连接或测试。
