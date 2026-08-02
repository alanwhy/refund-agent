# 自定义订单、模型审计与客户售后入口设计

## 1. 背景与目标

当前演示环境已经支持管理员创建受控测试订单，并能验证自动退款、金额审批、风险审批和支付异常
四条路径。本次增强解决四个使用问题：

1. 管理员创建订单时可自行输入订单金额，金额规则真实参与退款决策；
2. 审计台将模型调用独立分类，并保留可审计的完整逻辑输入和输出；
3. 客户可从“我的订单”直接申请或查看售后，每笔订单只显示一个最终业务状态；
4. 实施、测试和验收完成后清除当前运行数据，并恢复干净的初始演示环境。

本次不接入真实订单、支付或客户系统，不改变“模型无资金权限”的安全边界。

## 2. 总体方案

采用现有架构上的增量增强：

- 订单金额继续写入现有 `Order.amount`，不新增金额表；
- 演示场景只控制订单特征，金额是否触发审批由现有确定性规则决定；
- 模型输入输出继续写入现有不可变 `AuditEvent`，不新增重复审计表；
- 订单唯一展示状态由后端计算，前端只消费 `lifecycle_status`；
- 客户订单页复用现有聊天和工单接口，不新增另一套售后流程。

因此本次不需要业务表迁移。API Schema、审计内容和前端交互会发生兼容性增强。

## 3. 管理员自定义订单金额

### 3.1 表单

“新建测试订单”表单包含：

- 订单所属客户；
- 商品名称；
- 订单金额；
- 订单特征。

金额范围为 `0.01–999999.99`，最多两位小数。前端使用数字输入提供即时提示，服务端使用
`Decimal` 进行最终校验，不使用浮点数参与金额判断。

订单特征调整为：

| 页面选项 | 内部场景 | fraud_flag | payment_behavior |
| --- | --- | --- | --- |
| 正常订单 | `AUTO_REFUND` | false | success |
| 风控订单 | `RISK_APPROVAL` | true | success |
| 支付异常订单 | `PAYMENT_UNKNOWN` | false | unknown |

新页面不再展示“金额审批”场景。后端继续识别旧的 `AMOUNT_APPROVAL` 值，并将它视为正常支付、
无风控标记，以兼容已有客户端和历史幂等请求。

### 3.2 决策规则

金额与订单特征独立生效：

- 正常订单金额不超过 ¥500：自动退款；
- 正常订单金额超过 ¥500：进入金额审批；
- 风控订单：进入风险审批；金额同时超过 ¥500 时保留金额与风控两条审批原因；
- 支付异常订单：先通过订单、政策、风险和必要审批，再在退款执行阶段得到 UNKNOWN，进入技术
  异常队列，且不自动重试支付。

场景服务不再提供固定金额。`DemoOrderCreateRequest` 必须包含 `amount`，服务端场景映射只生成
`fraud_flag` 和 `payment_behavior`。审计事件 `demo_order.created` 增加金额，但不记录原始请求体。

### 3.3 幂等与错误

- 首次 request ID 创建订单并返回 201；
- 相同 request ID 重放返回首次订单和 200；
- 重放时不使用新请求覆盖首次金额、商品、客户或特征；
- 金额为空、非数字、非正数、超过上限或精度超过两位时返回 422；
- 校验失败不写入 `Order`、`DemoOrderCreation` 或审计事件。

## 4. 模型调用审计

### 4.1 审计事件

每次逻辑模型调用继续记录：

- `model.requested`；
- `model.completed`；
- `model.failed`（仅失败时）。

`model.requested.details` 包含：

- model；
- prompt_version；
- logical_step；
- input.messages：按顺序序列化的 System、Human、AI、Tool 消息；
- input.tools：当前允许的工具名称。

消息保留 `type`、`content`、`tool_calls`、`tool_call_id` 等实际存在的结构化字段。这里保存的是
LangChain 交给模型的逻辑请求，不保存代理网关 HTTP Headers。

`model.completed.details` 包含：

- model；
- prompt_version；
- logical_step；
- output：完整模型消息、文本与 Tool Calls；
- duration_ms；
- usage；
- tool_count。

`model.failed` 保存模型、轮次、异常类型和受控错误摘要。对应输入仍由同一轮的 requested 事件
提供。

### 4.2 脱敏与降级

审计写入前对任意字典和数组递归处理。键名匹配以下类别时用 `[REDACTED]` 替换值：

- api key / token / authorization；
- password / secret；
- cookie / session credential。

用户输入的订单号、退款原因、工具 observation 和模型回复属于本演示的业务审计内容，按原文
保留。模型配置密钥、JWT、HTTP Authorization 和代理请求头不得进入审计。

序列化器只输出 JSON 安全类型；未知对象转换为受控字符串。若某个字段无法序列化，模型调用仍
继续执行，审计降级保存字段类型与序列化错误，不能因为可观测性故障阻断退款主流程。

### 4.3 审计页面

审计页面提供三个一级分类：

- 全部记录；
- 模型调用；
- 业务事件。

API 增加受控 `category` 查询参数：`model` 按 `entity_type=model` 筛选，`business` 排除模型事件。
现有 ticket ID 和 action 筛选继续可用。

模型分类使用专用卡片展示：

- 请求输入消息；
- 模型输出；
- Tool Calls；
- Token 用量；
- 耗时、节点、轮次与追踪号。

普通业务事件维持当前审计账本展示，不把大段模型输入输出混入业务摘要。

## 5. 客户订单售后入口

### 5.1 订单页动作

客户“我的订单”中每笔订单提供一个明确动作：

- 没有关联工单：显示“申请售后”；
- 存在关联工单：显示“查看售后”。

“申请售后”导航至 `/chat?order_number=<订单号>`。聊天页读取订单号并预填
`我想退款，订单号 <订单号>，原因是`，由客户补充原因后确认提交。导航本身不创建工单，避免
误触产生空工单。

“查看售后”导航至 `/chat?ticket_id=<最新工单 ID>`，聊天页选中并读取该工单。客户只能读取
自己的订单与工单；后端权限条件仍是最终边界。

如果页面数据过期，客户点击申请后服务端发现已有未结束工单，则返回 409，前端刷新并引导查看
最新工单，不创建重复申请。

### 5.2 唯一订单状态

`OrderView` 增加 `lifecycle_status`。订单列表只展示这一项，不再同时展示订单、工单和审批多个
状态标签。后端按最新关联工单及其退款、审批、异常记录计算：

| 条件 | lifecycle_status | 客户文案 |
| --- | --- | --- |
| RefundRequest.status = SUCCEEDED | REFUNDED | 已退款 |
| Ticket.status = MANUAL_REVIEW | MANUAL_REVIEW | 人工处理中 |
| Ticket.status = WAITING_APPROVAL | WAITING_APPROVAL | 等待审批 |
| Ticket.status = CREATED / RUNNING / WAITING_USER | AFTER_SALES_PROCESSING | 售后处理中 |
| Ticket.status = REJECTED | REFUND_REJECTED | 退款未通过 |
| Ticket.status = FAILED 或退款 FAILED | AFTER_SALES_FAILED | 处理失败 |
| 无售后终态覆盖 | Order.status | 已签收等订单状态 |

已解决技术异常不会被自动解释为退款成功；只有支付退款记录明确为 SUCCEEDED 才显示“已退款”。
管理员和审批员仍可在订单详情区域查看审批原因与技术异常信息，但订单主状态同样只显示一个。

## 6. 接口与组件改动

### 后端

- `DemoOrderCreateRequest.amount: Decimal`；
- 演示订单服务由请求金额创建 `Order`；
- `OrderView.lifecycle_status`；
- 订单视图构建器集中计算最新售后状态；
- 模型审计序列化与递归脱敏工具；
- `/api/audit-events?category=model|business`。

### 前端

- `DemoOrderForm` 增加金额输入并将场景卡调整为三项；
- `OrdersPage` 只显示 `lifecycle_status`，客户行增加售后动作；
- `CustomerChatPage` 消费 `order_number` 和 `ticket_id` 查询参数；
- `AuditPage` 增加分类切换和模型调用专用展示；
- `StatusPill` 增加 REFUNDED、AFTER_SALES_PROCESSING、REFUND_REJECTED、
  AFTER_SALES_FAILED 文案。

## 7. 测试与验收

### 自动化测试

- 金额边界、Decimal 精度、非法金额和额外内部字段；
- request ID 重放保留首次金额；
- 正常 ¥399 自动退款、正常 ¥699 金额审批；
- ¥699 风控订单同时产生金额和风险原因；
- 支付未知在必要审批完成后进入异常且不重试；
- 模型输入包含 System/Human/Tool，输出包含文本与 Tool Calls；
- 嵌套密钥字段被脱敏，模型调用不因审计序列化失败而中断；
- 模型与业务审计分类查询；
- lifecycle_status 所有映射和客户数据隔离；
- 客户申请售后预填订单号、查看已有工单和过期页面冲突处理；
- 每笔订单只渲染一个主状态标签。

### 浏览器验收

1. 管理员分别以自定义 ¥399、¥699 创建正常订单；
2. 客户从“我的订单”发起售后并确认订单号已预填；
3. 验证自动退款和金额审批结果；
4. 验证订单从“已签收”最终变为“已退款”，且只显示一个状态；
5. 审计页面切换“模型调用”，查看完整输入、输出与 Tool Calls；
6. 验证风控叠加金额原因和支付异常路径；
7. 检查桌面与移动布局无横向溢出或操作遮挡。

## 8. 数据清理与交付状态

代码、自动化测试、真实模型烟测、浏览器验收、提交和推送全部完成后，执行一次明确的数据重置：

```bash
docker compose down -v
docker compose up -d
```

这会删除当前 PostgreSQL 数据卷和 Redis 容器状态。重新启动后迁移并幂等写入初始数据。最终验证：

- 4 个初始账号；
- 5 个固定订单；
- 初始政策文档；
- 0 个测试订单创建记录；
- 0 个工单、退款、审批、技术异常和审计事件；
- 0 个 LangGraph checkpoint 业务线程。

最终保持 API、Worker、Scheduler 和 Web 服务运行。数据重置后不再执行会写入业务数据的浏览器
流程或真实 Agent 流程，只做健康检查与只读计数。
