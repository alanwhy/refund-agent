# 智能退换货 Agent 全栈 MVP 设计

## 1. 目标

在空仓库中实现一个可通过 Docker Compose 本地运行的智能退换货 Agent MVP。系统完整支持退货退款闭环，能够在低风险场景自动退款，在金额大于 500 元或命中其他风险规则时暂停工作流并等待人工审批。换货和异常工单只负责识别、摘要、建单和转人工。

系统必须同时提供：

- 客户对话页面；
- 审批工作台；
- 审计记录页面；
- FastAPI 服务与异步 Worker；
- LangGraph 可暂停、可恢复工作流；
- PostgreSQL 持久化与 Redis 队列、缓存和锁；
- 可替换的订单、物流、支付、知识库和 LLM 适配器；
- 一组能够演示成功、失败、超时和审批恢复的 Mock 外部服务。

## 2. 范围

### 2.1 本期范围

- 使用内置演示账号登录，角色为 CUSTOMER、APPROVER 和 ADMIN；
- 从自然语言识别退款、换货、异常或咨询意图；
- 查询并验证 Mock 订单及其客户归属；
- 按确定性政策规则校验退款资格和计算退款金额；
- 按可配置风险规则决定自动执行或人工审批；
- 通过 Mock 支付服务幂等地执行退款；
- 生成退货物流指引；
- 保存工作流检查点并在审批后恢复；
- 记录状态变化、规则判断、模型调用、工具调用和审批操作；
- 使用 PostgreSQL 全文检索预置政策文档；
- 通过 OpenAI 兼容接口调用模型，允许配置 Base URL、API Key 和模型名称；
- 在未配置模型接口时，测试可使用确定性 Fake 模型。

### 2.2 不在本期范围

- 真实电商、物流和支付系统接入；
- 换货和异常工单的自动执行；
- 企业 OAuth、短信、邮件和推送集成；
- Kubernetes、跨区域高可用和生产级密钥管理；
- 多人会签审批；
- 向量数据库和知识库在线导入后台；
- 使用模型直接裁决退款资格、金额或审批条件。

## 3. 技术选型

| 模块 | 选型 |
| --- | --- |
| 后端 | Python 3.12、FastAPI、Pydantic、SQLAlchemy、Alembic |
| Agent 工作流 | LangGraph |
| 异步任务 | Celery + Redis |
| 数据库 | PostgreSQL |
| 前端 | React、TypeScript、Vite |
| 测试 | pytest、Playwright、前端组件测试 |
| 本地运行 | Docker Compose |
| 模型接口 | OpenAI 兼容 Chat Completions 接口；本地开发可切换 Fake 模式 |

选择模块化单体而不是微服务。Agent 是同一后端中的领域模块和 LangGraph 节点，不是独立网络服务。API 与 Worker 使用相同的领域代码，但分别运行。

## 4. 总体架构

~~~mermaid
flowchart LR
    U["客户 / 审批员 / 管理员"] --> WEB["React Web"]
    WEB --> API["FastAPI API"]
    API --> DB["PostgreSQL"]
    API --> Q["Redis 队列与锁"]
    Q --> W["Celery Worker"]
    W --> LG["LangGraph 工作流"]
    LG --> A["领域 Agent 节点"]
    A --> R["确定性规则引擎"]
    A --> K["知识库适配器"]
    A --> T["订单 / 物流 / 支付 Mock"]
    LG --> DB
~~~

运行组件：

- web：提供客户、审批与审计界面；
- api：负责鉴权、查询、提交消息和审批决定；
- worker：异步运行或恢复 LangGraph；
- postgres：保存业务状态、检查点和审计事件；
- redis：保存 Celery 队列、短期缓存与分布式锁。

## 5. 模块边界

### 5.1 API 层

处理 HTTP、JWT 鉴权、角色授权、请求校验和响应序列化。API 层不能直接执行退款，只能调用应用服务并投递任务。

### 5.2 应用服务层

负责创建工单、提交用户消息、记录审批决定、调度工作流，以及执行资源归属检查。它定义事务边界，但不包含模型提示词或外部接口细节。

### 5.3 工作流层

定义 LangGraph 状态、节点、条件边和暂停点。工作流只通过领域服务和端口接口访问规则、知识库和外部系统。

### 5.4 Agent 节点

- Classifier：识别意图、提取订单号并给出置信度；
- OrderAgent：通过订单端口取得结构化订单和物流事实；
- PolicyAgent：检索政策材料，并调用确定性规则引擎校验资格和金额；
- RiskAgent：收集风险信号，由规则引擎计算风险级别和审批需求；
- RefundAgent：在全部前置条件满足后调用幂等支付端口；
- NotifyAgent：根据结构化结果组织客户可读回复。

LLM 只用于意图理解、字段提取、政策材料摘要和回复生成。订单归属、时间窗口、金额计算、风险阈值、权限和支付执行全部由代码决定。

### 5.5 端口与适配器

定义 OrderGateway、LogisticsGateway、PaymentGateway、KnowledgeRepository 和 LLMClient 接口。MVP 提供数据库或进程内 Mock 实现，并允许后续替换为真实 HTTP 服务。

## 6. 工作流

~~~mermaid
flowchart TD
    S["创建工单"] --> C["Classifier：识别意图与提取订单号"]
    C -->|退款 / 退货| O["OrderAgent：查询订单与物流"]
    C -->|换货 / 异常 / 低置信度| M["创建人工工单"]
    O --> P["PolicyAgent：确定性规则校验"]
    P -->|不符合政策| N["生成解释并通知客户"]
    P -->|符合政策| R["RiskAgent：规则评分"]
    R -->|无需审批| X["RefundAgent：幂等执行退款"]
    R -->|需要审批| H["暂停并创建审批任务"]
    H -->|批准 / 修改后批准| X
    H -->|拒绝| N
    X --> L["创建退货物流指引"]
    L --> N
    N --> A["写入审计记录并结束"]
~~~

### 6.1 状态

工作流状态至少包含：

- ticket_id、customer_id 和 conversation_id；
- intent、intent_confidence 和 extracted_order_id；
- order_snapshot 和 policy_evidence；
- requested_amount、calculated_amount 和 approved_amount；
- risk_level、risk_reasons、matched_rule_ids 和 rule_version；
- approval_task_id 和 approval_decision；
- refund_status、payment_reference 和 return_instructions；
- customer_message、errors 和 current_step。

工单状态使用 CREATED、RUNNING、WAITING_APPROVAL、MANUAL_REVIEW、COMPLETED、REJECTED 和 FAILED。退款状态使用 NOT_STARTED、PROCESSING、SUCCEEDED、FAILED 和 UNKNOWN。

### 6.2 暂停与恢复

RiskAgent 判定需要审批时，在同一数据库事务中创建 approval_tasks 记录、写入审计事件，并将工单状态改为 WAITING_APPROVAL。LangGraph 在审批节点保存 PostgreSQL checkpoint 后暂停。

审批 API 接受批准、拒绝、修改后批准或转派。有效决定写入数据库后投递恢复任务。Worker 从 checkpoint 恢复，不重新运行已经成功完成的支付步骤。

### 6.3 幂等与并发

- 支付幂等键由 ticket_id 和 refund 动作类型组成，并在数据库中建立唯一约束；
- Worker 执行工单前获取以 ticket_id 为粒度的 Redis 锁；
- 审批决定使用版本号进行乐观锁校验，第二个并发决定返回冲突；
- 支付成功响应先落库再推进工作流；
- 支付结果未知时不得自动重试，工单进入 MANUAL_REVIEW。

## 7. 政策与风险规则

规则保存在 config/rules 下的 YAML 文件中。工作流启动时读取有效规则，计算内容摘要作为 rule_version，并把实际版本保存到工单和审计事件中。

默认行为：

- 退款金额不大于 500 元且未命中其他风险规则时允许自动退款；
- 退款金额大于 500 元时必须人工审批；
- 高频退款、订单信息冲突、可疑账户信号或模型低置信度触发人工审批；
- 订单不存在、订单不属于当前客户或不满足退货时效时拒绝自动退款；
- 审批修改后的金额不得超过规则引擎计算的可退上限；
- 审批超时后状态改为 ESCALATED 并进入管理员队列，不自动退款。

MVP 使用单人审批。approval_tasks 数据模型保留 required_approvals 字段，默认值为 1，但本期不实现多人会签。

## 8. 安全设计

### 8.1 身份与权限

- 密码使用 Argon2 哈希；
- 登录后签发短期 JWT；
- CUSTOMER 只能读取自己的工单和消息；
- APPROVER 只能处理分配给自己或未认领的审批任务；
- ADMIN 可以查看全部审计记录和升级任务；
- 所有资源访问先检查身份，再检查资源归属。

### 8.2 LLM 隔离

- 用户文本作为不可信数据放入明确的数据边界；
- 系统指令、政策资料和用户输入分开构造消息；
- 模型输出必须通过 Pydantic Schema 校验；
- 工具名由服务端白名单选择，模型不能提供任意 URL、SQL 或代码；
- 低置信度、解析失败或疑似提示注入时转人工；
- 模型生成的金额和状态不会进入执行路径。

### 8.3 工具执行拦截

每次支付调用前重新校验：

1. 当前用户与订单归属；
2. 工单状态和审批状态；
3. 规则版本及可退金额；
4. 是否存在成功退款或进行中的相同幂等键；
5. 调用者是否是 Worker 内部服务身份。

即使有人绕过前端或篡改模型输出，也不能绕过这些服务端检查。

### 8.4 审计与脱敏

audit_events 在应用层只允许追加，不提供更新和删除接口。事件记录 actor、action、entity、规则版本、脱敏输入、结果、trace_id 和时间。密码、JWT、API Key、完整支付信息和其他密钥不得写入日志。模型与工具内容经过字段级脱敏后再保存。

MVP 的审计日志用于演示可追溯性，不宣称具备密码学防篡改能力。

## 9. 数据模型

核心表：

- users：账号、密码哈希、角色和启用状态；
- orders：Mock 订单、客户、商品、金额、支付和物流状态；
- conversations：对话归属和时间；
- messages：用户与系统消息；
- tickets：工单类型、状态、当前步骤、规则版本和版本号；
- refund_requests：请求金额、核算金额、批准金额、幂等键和支付状态；
- approval_tasks：风险原因、AI 建议、状态、处理人、决定和超时时间；
- workflow_checkpoints：LangGraph 持久化状态；
- audit_events：只追加的审计事件；
- knowledge_documents：政策正文、版本、生效时间和全文检索向量。

数据库迁移由 Alembic 管理。演示数据脚本创建三类账号、若干订单、政策材料和五条验收场景所需数据。

## 10. API 设计

主要端点：

- POST /api/auth/login：验证演示账号并返回 JWT；
- POST /api/chat/messages：创建或继续工单，返回 ticket_id 和已接受状态；
- GET /api/tickets：按当前角色过滤工单；
- GET /api/tickets/{ticket_id}：返回工单、消息、步骤和当前状态；
- GET /api/approvals：列出可处理审批；
- GET /api/approvals/{approval_id}：返回审批证据和风险原因；
- POST /api/approvals/{approval_id}/decision：批准、拒绝、修改后批准或转派；
- GET /api/audit-events：管理员按工单、事件类型和时间筛选；
- GET /health：进程存活检查；
- GET /ready：检查 PostgreSQL、Redis 和必要配置。

所有错误采用统一结构，包含 code、message、trace_id 和可选 details。服务端错误不向客户端暴露堆栈、提示词或凭据。

## 11. 前端体验

### 11.1 客户对话页

显示用户消息、系统回复、已确认订单、政策校验、审批等待、退款结果和退货指引。前端轮询工单状态；本期不实现 WebSocket。页面只展示业务步骤，不暴露内部 Agent 名称或推理过程。

### 11.2 审批工作台

展示订单快照、政策证据、退款金额、命中规则、风险原因、AI 建议和审计时间线。审批员可以批准、拒绝、在可退上限内调整金额或转派。提交后禁用重复操作，并对并发冲突给出明确提示。

### 11.3 审计记录页

仅管理员可访问。支持按工单、事件类型和时间筛选，查看脱敏后的决策、模型和工具事件。

### 11.4 登录页

提供客户、审批员和管理员演示账号提示，登录后按角色进入相应页面。

## 12. 知识库

MVP 将带版本的政策文档存储在 PostgreSQL。写入时使用 jieba 生成空格分隔的 search_tokens，查询时使用 PostgreSQL simple 文本搜索配置检索该字段。KnowledgeRepository 返回文档 ID、版本、相关片段和有效期。PolicyAgent 可以让 LLM 摘要检索结果，但最终资格判断使用结构化规则。

接口设计允许后续替换为 pgvector 或独立向量数据库，而不修改工作流节点。

## 13. 模型配置

模型客户端从环境变量读取兼容接口的 Base URL、API Key、模型名、超时和重试次数。LLM_MODE 支持 compatible 和 fake：Docker Compose 的开发默认值为 fake，配置兼容接口时显式切换为 compatible。API Key 只存在于运行环境。生产代码不把模型配置写死在仓库中。

模型调用使用结构化输出、较低温度、请求超时和有限重试。重试后仍失败、返回格式不合法或置信度不足时，工单转 MANUAL_REVIEW。测试使用确定性 FakeLLM，不依赖网络和真实额度。

## 14. 异常处理

- 订单不存在或归属不匹配：停止自动处理并给出不泄露他人订单的提示；
- 规则拒绝：保存原因并向客户提供可理解说明；
- LLM 超时或无效输出：有限重试后转人工；
- 外部查询暂时失败：按指数退避有限重试；
- 支付明确失败：保存 FAILED，允许授权人员在确认后重新发起；
- 支付结果未知：保存 UNKNOWN 并转人工，不自动重试；
- Worker 重启：从数据库 checkpoint 恢复；
- PostgreSQL 或 Redis 不可用：ready 检查失败，拒绝新资金操作；
- 未预期异常：记录 trace_id，工单进入 FAILED 或 MANUAL_REVIEW，客户只看到安全提示。

## 15. 可观测性

后端使用结构化 JSON 日志，并通过 trace_id、ticket_id 和 workflow_run_id 关联 API、Worker、模型与工具事件。健康端点支持 Docker Compose 依赖检查。

MVP 至少采集工单数量、自动完成率、转人工率、审批等待时间、退款成功率、模型失败次数和工具失败次数。指标先提供应用内采集与日志输出，不部署 Prometheus 和 Grafana。

## 16. 代码组织

~~~text
refund-agent/
├── backend/
│   ├── src/refund_agent/
│   │   ├── api/
│   │   ├── application/
│   │   ├── domain/
│   │   ├── workflows/
│   │   ├── agents/
│   │   ├── ports/
│   │   ├── adapters/
│   │   ├── security/
│   │   └── observability/
│   ├── prompts/
│   ├── migrations/
│   └── tests/
├── frontend/
│   ├── src/
│   └── tests/
├── config/rules/
├── scripts/
├── docs/
├── docker-compose.yml
└── README.md
~~~

Prompt 与 Python 代码分离，但 Prompt 变更仍通过 Git 评审和测试发布。规则文件同样纳入版本控制。

## 17. 测试策略

### 17.1 后端

- 单元测试覆盖政策、风险、金额、权限、状态转换和脱敏；
- 工作流测试覆盖自动退款、等待审批、拒绝、修改后批准、恢复和转人工；
- 适配器契约测试覆盖成功、失败、超时和未知支付状态；
- API 集成测试覆盖 JWT、资源归属、越权、重复请求和并发审批；
- 安全测试覆盖提示注入、参数篡改、阈值绕过和敏感字段日志。

### 17.2 前端

- 组件测试覆盖角色导航、状态呈现和审批表单；
- Playwright E2E 覆盖客户发起退款、审批员决策和管理员审计查询。

### 17.3 固定验收场景

1. 399 元合规订单自动退款并返回退货指引；
2. 699 元合规订单在审批前不调用支付，批准后从检查点恢复并退款；
3. 低金额但命中欺诈规则的订单进入审批；
4. 支付超时且结果未知时进入人工核查，重复任务不会产生第二笔退款；
5. 客户、审批员和管理员的越权请求均被拒绝并写入审计。

## 18. 完成标准

- Docker Compose 能在全新环境启动全部组件；
- 数据迁移和演示数据初始化可重复执行；
- 三类演示账号能够访问各自页面；
- 固定验收场景全部通过；
- 后端、前端和 E2E 测试通过；
- 未配置真实 LLM 时测试仍可离线运行；
- README 说明启动、配置、账号、架构和演示步骤；
- 审计页面能够重建每个验收工单的关键状态与决定；
- 仓库中不存在 API Key 或其他凭据。

## 19. 后续演进

完成 MVP 后，可按实际需求依次增加真实系统适配器、向量检索、多人审批、通知渠道、Prometheus 指标、Kubernetes 部署和企业身份系统。这些演进必须复用现有端口，不改变资金操作的确定性规则与服务端安全拦截。
