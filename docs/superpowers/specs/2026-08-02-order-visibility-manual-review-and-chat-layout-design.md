# 订单可见性、异常处理与客户对话布局修正设计

## 1. 背景

Refund Agent v2 已支持真实模型、只读工具、多轮补问、确定性规则、人工审批和 PostgreSQL
checkpoint。实际演示暴露出三个相互关联的问题：

1. Agent 首轮调用 `RequestUserInput` 后，恢复节点直接追加 `HumanMessage`，没有为上一条模型
   tool call 生成对应 `ToolMessage`。OpenAI-compatible 网关因此拒绝第二次模型调用，工单错误进入
   `MANUAL_REVIEW`。
2. 审批页面只读取 `ApprovalTask`。技术异常没有审批任务，因此审核员和管理员无法在现有审批
   队列看到异常工单；这符合当前数据模型，但不满足后台处理需求。
3. 客户对话页面没有把工作区限制在桌面端可视高度。消息增长后，输入框被推到视口下方，用户
   必须滚动整个页面才能继续操作。

此外，系统缺少按角色授权的订单列表，用户、审核员和管理员无法从独立页面查看其权限范围内
的订单。

## 2. 已确认目标

- 修复 LangGraph 用户补问恢复时的工具消息协议。
- 不存在或不属于当前用户的订单由确定性代码明确拒绝，不转技术人工处理。
- 将“退款审批”和“技术异常处理”分为两类独立业务对象与后台队列。
- 审核员和管理员可以处理技术异常，但不能在异常页面直接批准退款。
- 增加按角色过滤的订单页面。
- 桌面端客户对话页在单个视口内完成核心操作，输入框始终可见。
- 保留现有安全边界：模型不能决定退款金额、审批条件、订单归属或支付执行。

## 3. 非目标

- 不实现换货自动化流程。
- 不接入真实订单、物流或支付系统。
- 不允许异常处理任务直接触发退款。
- 不向客户暴露模型错误、堆栈、网关响应或内部异常码。
- 不重做现有视觉品牌、导航体系或移动端整体信息架构。

## 4. 关键业务语义

### 4.1 退款审批

退款审批表示业务事实已经完整：

- 已找到属于当前客户的订单；
- 服务端已计算退款资格和金额上限；
- 服务端风险规则判定必须人工批准；
- 已创建唯一 `ApprovalTask`。

模型可以收集信息和查询证据，但是否需要审批只能由服务端风险规则决定。

### 4.2 技术异常处理

技术异常处理表示自动流程无法安全完成，例如：

- 模型或网关调用失败；
- 支付结果为 `UNKNOWN`；
- 工具、checkpoint 或业务数据出现无法自动恢复的一致性异常；
- 安全防护拦截了无法继续的模型控制调用。

技术异常不等同于业务审批。异常任务可以查看、认领、填写内部备注，并标记“已解决”或
“无法解决”，但不能直接批准或执行退款。

### 4.3 订单不存在或不属于当前用户

这是一项确定性业务拒绝，不是技术异常：

- 工单状态进入 `REJECTED`；
- 不创建 `ApprovalTask`；
- 不创建异常处理任务；
- 不调用支付；
- 客户收到：`未找到订单 ORD-400，或该订单不属于当前账号。请核对订单号后重试。`

由于系统刻意不区分“不存在”和“属于其他用户”，响应不会泄露其他客户的订单存在性。

## 5. Agent 补问恢复协议

### 5.1 当前问题

模型返回 `RequestUserInput` tool call 后，Graph 在 `ask_user` 节点调用 `interrupt()`。恢复时当前
实现只追加用户答案。消息序列因此成为：

1. `AIMessage(tool_calls=[RequestUserInput])`
2. `HumanMessage(用户补充内容)`

OpenAI-compatible Chat Completions 要求每个 assistant tool call 后都有相同 `tool_call_id` 的
tool response。缺少该消息会导致下一次模型调用返回 HTTP 400。

### 5.2 修正后的消息序列

`ask_user` 恢复后同时返回：

1. `ToolMessage`：绑定原始 `RequestUserInput` 的 `tool_call_id`，内容为结构化的“用户已提供
   补充信息”结果；
2. `HumanMessage`：保存客户原始回答。

Graph 随后回到 `reason_and_route`。模型可以继续调用 `get_order` 或提交退款上下文。

控制调用的 ToolMessage 只描述控制动作已经完成，不将用户 ID、审批状态或金额写入 observation。

## 6. 数据模型

### 6.1 Ticket 补充字段

为工单增加可空的 `submitted_order_number`，保存用户或模型提交的规范化订单号。即使服务端未
找到对应 `Order`，客户工单列表和异常任务仍能显示用户实际提交的订单号。

该字段不是可信订单关联；资金与权限校验仍只使用验证后的 `ticket.order_id`。

### 6.2 ManualReviewTask

新增独立 `manual_review_tasks` 表：

| 字段 | 语义 |
| --- | --- |
| `id` | 异常任务 ID |
| `ticket_id` | 唯一关联工单 |
| `status` | `PENDING`、`RESOLVED`、`UNRESOLVABLE` |
| `category` | `MODEL_FAILURE`、`PAYMENT_UNKNOWN`、`DATA_INCONSISTENCY`、`SECURITY_REJECTION` 等受控分类 |
| `submitted_order_number` | 用户提交的订单号快照，可空 |
| `technical_summary` | 对客户隐藏的脱敏技术摘要 |
| `assigned_to` | 当前处理人，可空 |
| `resolution_note` | 内部处理备注，可空 |
| `resolved_by` | 最终处理人，可空 |
| `version` | 乐观锁版本 |
| `created_at`、`updated_at`、`resolved_at` | 生命周期时间 |

`ticket_id` 唯一，保证节点重放不会创建重复异常任务。

### 6.3 历史数据迁移

迁移为现有 `MANUAL_REVIEW` 工单幂等创建异常任务：

- 能从最后一次 `agent.manual_review` 审计推断分类时使用对应分类；
- 支付状态为 `UNKNOWN` 时使用 `PAYMENT_UNKNOWN`；
- 无法可靠推断时使用 `DATA_INCONSISTENCY`；
- 用户提交订单号可从 Ticket 新字段或已有用户消息中安全提取，提取不到则为空。

迁移不创建虚假的 `Order` 关联，也不创建审批任务。

## 7. 异常任务创建规则

统一的异常服务负责：

- 将工单设为 `MANUAL_REVIEW`；
- 幂等创建或读取对应 `ManualReviewTask`；
- 写入对客户安全的助手消息；
- 追加带稳定 `event_key` 的审计事件。

错误分类只保存受控枚举和脱敏摘要，不保存 API Key、Authorization header、完整模型响应或堆栈。

处理异常任务时使用 `id + version` 乐观锁。审核员和管理员均可：

- 查看异常详情；
- 认领或重新认领；
- 保存内部备注；
- 标记 `RESOLVED` 或 `UNRESOLVABLE`。

任何异常操作都不得写入 `ApprovalTask`、`RefundRequest` 或调用支付适配器。

## 8. 订单页面与权限

新增 `/orders` 页面和 `GET /api/orders`、`GET /api/orders/{order_id}` 接口。所有过滤由后端完成，
前端传入的 customer ID 或订单号不能扩大权限。

### 8.1 客户

- 只能查看 `Order.customer_id == current_user.id` 的订单；
- 可查看订单号、商品、金额、状态、签收时间和是否已有退款工单；
- 不能看到欺诈标记、支付模拟行为或其他客户信息。

### 8.2 审核员

- 只能查看曾产生 `ApprovalTask` 的关联订单；
- 包括待处理、已批准、已拒绝和已升级的审批历史；
- 只能查看未分配或分配给自己的审批关联订单；管理员转派给其他审核员后不再可见；
- 不能用订单详情接口绕过列表限制查询普通订单或技术异常订单；
- 技术异常的关联订单从“异常处理”详情进入，不混入审核员订单列表。

### 8.3 管理员

- 可以查看全部订单；
- 列表显示所属客户；
- 可以从订单进入关联工单、审批、异常任务和审计记录；
- 管理员查看权限不授予直接退款能力。

## 9. 后台页面结构

主导航按角色显示：

- 客户：`售后对话`、`我的订单`；
- 审核员：`退款审批`、`审批订单`、`异常处理`；
- 管理员：`退款审批`、`全部订单`、`异常处理`、`审计记录`。

现有审批页面只展示 ApprovalTask。新增异常处理页面展示 ManualReviewTask，两者的状态、操作和
文案保持明确区分。

异常详情优先展示：客户、用户提交订单号、已验证订单（若存在）、异常分类、客户可见状态、
时间线、内部备注和处理操作。技术摘要使用中文可理解标签，不直接展示 Python 异常栈。

## 10. 客户端错误反馈

### 10.1 确定性订单拒绝

`validate_context` 先写入 `submitted_order_number`，再按订单号和可信 customer ID 查询订单。查询
失败时返回稳定错误码 `ORDER_NOT_FOUND_OR_NOT_OWNED`，终态回复使用确定性模板，不依赖模型：

`未找到订单 {order_number}，或该订单不属于当前账号。请核对订单号后重试。`

### 10.2 技术异常

客户统一看到：

`当前申请暂时无法自动完成，已转交售后专员处理。`

客户 API 不返回 `technical_summary`、异常分类或内部错误码。后台异常接口和管理员审计接口按
角色返回受控技术信息。

## 11. 桌面端客户对话布局

采用已确认的 A 方案“视口内三段式”：

- `app-shell` 在桌面端占满 `100dvh`；
- 顶栏保持固定高度；
- `.customer-workspace` 高度为 `calc(100dvh - 顶栏高度)`，设置 `min-height: 0` 和
  `overflow: hidden`；
- 对话栏使用 `grid-template-rows: auto minmax(0, 1fr) auto`；
- 只有 `.messages` 内部纵向滚动，Composer 始终在对话栏底部；
- 左侧工单列表和右侧依据栏分别使用内部滚动；
- 页面根节点在常见桌面分辨率不产生纵向滚动条；
- 移动端保留自然文档流，避免强制视口高度造成软键盘遮挡。

页面不会采用遮挡消息的悬浮 Composer。

## 12. API

新增接口：

- `GET /api/orders`
- `GET /api/orders/{order_id}`
- `GET /api/manual-review-tasks`
- `GET /api/manual-review-tasks/{task_id}`
- `POST /api/manual-review-tasks/{task_id}/assign`
- `POST /api/manual-review-tasks/{task_id}/resolution`

异常 resolution payload 包含：

- `version`；
- `status`：仅允许 `RESOLVED` 或 `UNRESOLVABLE`；
- `resolution_note`：必填、有长度上限。

版本冲突返回 HTTP 409；越权资源返回 404，避免泄露资源存在性。

## 13. 审计

新增语义事件：

- `manual_review.created`
- `manual_review.assigned`
- `manual_review.resolved`
- `manual_review.unresolvable`
- `order.rejected`

审计记录包含工单、异常任务、处理人、分类、版本和受控备注，不包含秘密或原始异常堆栈。

## 14. 测试与验收

### 14.1 后端

- `RequestUserInput` interrupt/resume 后消息序列包含匹配 tool call ID 的 `ToolMessage`；
- 使用真实 OpenAI-compatible 消息约束的回归测试证明第二轮不再 400；
- `ORD-400` 返回 `REJECTED` 和确定性订单提示，无 ApprovalTask、ManualReviewTask 或 RefundRequest；
- 模型故障、支付未知和数据异常分别创建唯一异常任务；
- 异常任务节点重放不重复；
- 异常备注和终态使用版本锁，冲突返回 409；
- 客户、审核员和管理员的订单列表及详情越权测试；
- 审核员不能通过订单详情读取未进入自己审批范围的订单；
- 异常接口不能调用支付或修改审批状态；
- 历史 `MANUAL_REVIEW` 数据迁移测试。

### 14.2 前端

- 不同角色看到正确导航；
- 订单页面展示正确范围与空状态；
- 审批和异常队列分离；
- 异常任务可认领、填写备注、标记结果；
- 客户看到订单不存在的明确提示；
- 桌面端 Composer 位于视口内，只有消息区滚动；
- 移动端保持可输入且不被软键盘布局规则锁死。

### 14.3 浏览器验收路径

1. 客户提交“我想退货”，回答 `ORD-400，不想要了`，看到确定性拒绝。
2. 客户订单页只能看到自己的演示订单。
3. `ORD-699` 进入风险审批，审核员在退款审批和审批订单页可见。
4. 人为注入模型故障后，审核员和管理员在异常处理页可见，客户只看到友好状态。
5. 管理员订单页能看到全部客户订单并进入关联记录。
6. 在常见 PC 视口验证页面根节点无纵向滚动，Composer 始终可见。

## 15. 完成条件

- 补问恢复不再因工具消息协议产生 HTTP 400；
- 不存在/非本人订单得到明确、非泄露式拒绝；
- 审批与技术异常有独立数据模型、页面和操作权限；
- 三种角色的订单可见范围由后端测试证明；
- 历史和新建技术异常均可在后台处理；
- 桌面端客户对话无需滚动整个页面即可使用输入框；
- 全量后端与前端检查通过，并完成真实浏览器角色路径验收。
