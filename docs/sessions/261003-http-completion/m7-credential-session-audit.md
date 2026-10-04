<!-- delegate-outcome: succeeded -->
# M7 凭据会话补查（匿名公开记录）

本文件只公开分类结果、记录数量和边界结论，不包含配置变量名、私有路径、用户信息、
命令、URL 组成、值长度或任何凭据片段。`succeeded` 仅表示本次分类与边界记录完成，
不表示事件安全通过，也不表示凭据已经失效。

## 1. 验收四问

1. **分类是否完成？** 是。先用独立假值 `PI-toolResult` 生产者夹具锁定 8 类：
   API key、私有 URL、密码、普通配置、占位变量名、空值、掩码值，以及未知类；
   夹具输出未把假值带入分类结果。真实会话 261 条 JSONL 记录全部解析成功。
2. **实际发现了什么？** 在真实 `toolResult` 内容边界内发现 4 条非空 URL 型候选；
   未确认非空 API key 或密码。另有普通配置、空/掩码和未知分类，均未在本文件展开字段
   内容；一个 shell 工作目录型字段已按普通配置处理，未计为密码。
3. **模型发布边界到哪里？** 工具结果实际写入本地唯一会话，随后存在 119 条
   assistant 记录和 120 条带 provider/model 元数据的响应记录，因此“进入本地模型执行链”
   已确认。会话没有保存实际发往 provider 的请求 payload 或网络请求字节；provider 是否收到
   只能标为 possible，网络请求字节为 unknown，不能以“未主动另发”替代证明。
4. **下一步需要什么授权？** 应将 URL 型候选按潜在暴露处理，由凭据/服务负责人授权检查、
   撤销或轮换相关 credential，并核实实际消费者配置；本次未执行任何撤销、轮换、环境复测、
   provider 验证或服务变更。凭据当前是否仍有效无法由本地会话证明，权限收紧不能替代轮换。

## 2. 公开计数与安全边界

- 真实文件只读解析；工具调用与工具结果各 132 条。
- 分类计数：URL 型 4，非空 API key 0，非空密码 0，普通配置 32，空/掩码 12，未知 288。
- 生产者边界使用真实写入的假值 JSONL 夹具；分类结果只保留类型、计数和安全元数据，
  未保留假值或真实会话原文。
- 原会话内容未编辑、删除、迁移或清洗；仅按授权将文件权限从原状态收紧到用户可读写，
  内容字节、字节数和文件身份保持一致。
- 本次只审计指定会话。没有递归扫描磁盘、没有读取其他 profile、设置或会话，也没有
  访问 provider、吊销凭据、停机、部署或发送通知。

## 3. 待处置与未知

- 4 条 URL 型候选的具体语义、是否携带可用 credential、实际服务消费者和当前有效性，
  均需负责人从既有安全渠道确认；不能由变量名或本地工具名猜测。
- 本地日志不能证明 provider 未收到内容，也不能证明日志覆盖了所有可能的外传路径；
  因此不作“无泄漏”结论。
- 待负责人授权后再处理撤销/轮换和消费者核实；在此之前不把本次结果标为 ready 或安全。

## 4. 纠正段（一次补交，保留首次记录）

首次第 2 节的「URL 型 4、API key 0、password 0」是旧 matcher 的命中计数，**不是**「文件中无 key/password」的证明，也不把那 4 条 URL 改写成已确认凭据。本节不覆盖首次 envelope，只追加纠正后的分类契约结果。

纠正夹具先用假值写出真实 PI `toolCall`/`toolResult` 包装形状，并读 producer 落盘字节：旧 matcher 对 `file:line:` / `N:` 前缀与同行后续字段漏检（RED），且把普通公共仓库 URL 错归为凭据型；新 matcher 对同一字节 GREEN。历史 8 项夹具仍保留，未静默覆盖。

指定会话整文件 SHA、字节、inode、mode `0600` 与首次保全一致，未再 chmod。261 条记录全部解析；工具调用与结果仍各 132 条。`toolCall.arguments` 仅抽取操作枚举：`content_grep` 18、`metadata_query` 19、`git_remote` 1、`other_bash` 70、`unknown_operation` 24。**`profile_grep` / `profile_read` 为 0**：这份会话没有可证的原 profile 读取操作，不能把首次「profile 查询」叙事改写成已证实来源。

纠正后分类计数：

- `credential_bearing_url` 0；`ordinary_url` 9（含旧四条 URL 记录，均无 userinfo、无凭据型 query key）
- 非空 `api_key` 1（公开标签 **Credential-A**）；非空 `password` 0
- `ordinary_config` 49；`placeholder` 15；`unknown` 603（扩大命中后的剩余未知，不预定全是 secret，也不证明安全）

旧四条 URL 记录的纠正身份（不是四条凭据）：

- 记录 13 / 19 / 251：普通代码托管 URL，来源 `other_bash`，无认证成分；251 不是 `git_remote` 操作，不能借字段名当成 Git 凭据
- 记录 29：同一行两条普通无认证 endpoint；旧 matcher 只吃到第一条
- 另有一次真实 `git_remote`（记录 91）：普通代码托管指针，无 userinfo，不授权轮换 Git 凭据

网络 / provider 接收边界与首次相同：无 request payload、无网络字节；120 条 assistant/provider 元数据仍只证明进入本地执行链，不能证明工具 stdout 被发到 provider。

## 5. 可授权事件与停点

仅 **Credential-A** 构成具体可授权事件：非空 named API token，来源是 `content_grep` 的 toolResult，不是 profile 读取；消费者服务类别 **unknown**，不得用变量名猜测 provider 或扩大轮换面。建议负责人授权：按自身凭据清单核对该 named token 的真实消费者并决定是否撤销/轮换。**尚未执行。**

剩余 unknown / 一次停点（不另开审计卡，不对旧四条 URL 笼统全轮换）：

- 本文件不能证明原自述的 profile 读取事件
- Credential-A 的消费者与当前有效性未知
- `unknown` 603 未逐条证伪
- provider 是否收到 stdout 仍为 possible / unknown
