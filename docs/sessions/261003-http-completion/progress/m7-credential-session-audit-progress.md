<!-- delegate-outcome: succeeded -->
# M7 凭据会话补查进度

状态：**已完成指定会话的有限解析；事件处置仍待授权。**

## 已完成

1. 先用独立假值生产者夹具验证 `PI-toolResult` 序列化到分类器的边界，覆盖 API key、
   私有 URL、密码、普通配置、占位变量名、空值和掩码值；夹具通过且结果不含假值。
2. 只读解析指定 JSONL 会话：261 条记录、0 条解析错误；工具调用与工具结果各 132 条。
3. 真实工具结果中分类出 4 条非空 URL 型候选；未确认非空 API key 或密码。普通配置、
   空/掩码和未知分类已保留在私有报告，公开文档不展开字段内容。
4. 确认工具结果进入本地会话，并在同一序列后出现 assistant/provider/model 记录；实际
   provider 请求 payload 与网络请求字节未记录，因此 provider 接收和网络外传均保持 unknown/
   possible 边界。
5. 原会话内容未变更；仅按授权收紧文件读取权限。没有环境复测、凭据轮换、provider
   验证、服务操作或部署。

## 待办

- 由负责人授权后，按潜在暴露处理 URL 型候选，检查并撤销/轮换相关 credential。
- 由负责人确认实际服务消费者及消费者配置；本卡不根据字段名或工具名推断消费者。
- 在处置完成前，不把本结果解释为“无泄漏”、ready 或凭据已失效。

完整字段定位、匿名角色/工具名、时间、长度、匹配次数和文件保全元数据仅在私有报告中。

## 纠正补交（保留首次进度，不洗旧计数）

首次「URL 型 4 / API key 0 / password 0」只记录旧 matcher；本次不把它改写成「已证无 secret」。

已完成：

1. 假值 PI 实际包装形状夹具：旧 parser RED（前缀漏检 + 普通 URL 错归凭据），新 parser GREEN；v1 八项夹具历史保留。
2. 内存关联 `toolCall.arguments` → callRef → 完整 stdout。操作枚举：`content_grep` 18、`metadata_query` 19、`git_remote` 1、`other_bash` 70、`unknown_operation` 24；**无 profile 读取操作**。
3. 分类契约改为 `ordinary_url` / `credential_bearing_url` / `api_key` / `password` 等。旧四条 URL 记录均为普通 URL；公开标签 **Credential-A** 为 1 条非空 named API token（`content_grep`，消费者 unknown）。
4. 整文件 SHA / 525422 bytes / inode / mode `0600` 未变；未再 chmod；未网络验证、未轮换。

待负责人最小核查：只针对 Credential-A 的真实消费者与是否轮换。不对旧四条 URL 授权全轮换。一次补交后停止。
