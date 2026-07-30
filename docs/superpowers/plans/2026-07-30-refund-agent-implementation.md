# 智能退换货 Agent MVP 实施计划

## 1. 交付目标

按照已批准的设计，实现一个能够通过 Docker Compose 本地运行的全栈 MVP：

- 客户可登录并通过对话发起退款；
- 399 元合规订单自动退款；
- 699 元或命中风险规则的订单暂停并等待人工审批；
- 审批后从 LangGraph 检查点恢复；
- 支付结果未知时转人工且不会重复退款；
- 管理员可查看脱敏后的全链路审计；
- 换货和异常工单可识别、建单并转人工；
- 默认 Fake LLM 可离线演示，配置后可切换 OpenAI 兼容接口。

实施以小步提交和自动化测试为约束。每一阶段必须通过本阶段验证后再进入下一阶段。

## 2. 实施原则

1. 先写会失败的测试，再实现最小代码使其通过；
2. 资金相关行为只由确定性代码执行；
3. API 不直接调用支付，只投递工作流任务；
4. 外部系统只能通过端口接口访问；
5. 所有资源访问同时校验角色和资源归属；
6. 支付幂等、审批并发和工作流恢复在早期实现，不留到收尾；
7. 默认开发配置不需要真实模型密钥；
8. 每个阶段结束执行格式化、静态检查和相关测试。

## 3. 阶段一：仓库骨架与质量门禁

### 任务 1.1：建立目录和基础配置

创建：

- .gitignore
- .env.example
- README.md
- Makefile
- docker-compose.yml
- backend/pyproject.toml
- backend/src/refund_agent/__init__.py
- backend/src/refund_agent/config.py
- backend/tests/
- frontend/package.json
- frontend/tsconfig.json
- frontend/vite.config.ts
- frontend/src/
- config/rules/

要求：

- Python 固定为 3.12；
- 后端使用可编辑安装和 src 布局；
- 前端使用 React、TypeScript、Vite；
- 环境变量由 Pydantic Settings 统一校验；
- LLM_MODE 默认 fake；
- .env.example 只包含占位值，不包含凭据。

验证：

- 后端包可导入；
- 前端 TypeScript 配置可解析；
- git secrets 基础扫描无敏感值。

建议提交：

- chore: scaffold backend and frontend

### 任务 1.2：配置代码质量工具

后端配置：

- Ruff；
- mypy；
- pytest；
- pytest-asyncio；
- coverage。

前端配置：

- ESLint；
- Prettier；
- Vitest；
- React Testing Library。

创建统一命令：

- make lint
- make test
- make typecheck
- make format

验证：

- 空骨架的 lint、typecheck 和 test 命令成功。

建议提交：

- chore: add quality gates

## 4. 阶段二：本地基础设施

### 任务 2.1：Docker Compose 服务

创建：

- backend/Dockerfile
- frontend/Dockerfile
- frontend/nginx.conf
- scripts/wait-for-services.sh

Docker Compose 服务：

- postgres；
- redis；
- api；
- worker；
- web。

要求：

- PostgreSQL 和 Redis 配置健康检查；
- api 和 worker 等待依赖服务就绪；
- 数据通过命名卷持久化；
- web 通过反向代理访问 /api；
- 不把本地 .env 打包进镜像。

验证：

- docker compose config 成功；
- PostgreSQL 与 Redis 健康检查成功；
- api 和 worker 容器可以启动到空应用状态。

建议提交：

- build: add local docker compose stack

### 任务 2.2：应用健康检查

创建：

- backend/src/refund_agent/api/app.py
- backend/src/refund_agent/api/routes/health.py
- backend/src/refund_agent/infrastructure/database.py
- backend/src/refund_agent/infrastructure/redis.py
- backend/tests/api/test_health.py

行为：

- GET /health 只检查进程存活；
- GET /ready 检查 PostgreSQL、Redis 和运行模式所需配置；
- fake 模式不要求模型 API Key；
- compatible 模式缺少配置时 ready 返回失败。

验证：

- 单元与集成测试覆盖依赖正常和依赖失败；
- docker compose 中两个健康端点结果正确。

建议提交：

- feat: add health and readiness checks

## 5. 阶段三：领域模型、数据库与演示数据

### 任务 3.1：定义领域枚举和值对象

创建：

- backend/src/refund_agent/domain/enums.py
- backend/src/refund_agent/domain/money.py
- backend/src/refund_agent/domain/errors.py
- backend/tests/domain/test_money.py
- backend/tests/domain/test_state_enums.py

覆盖：

- UserRole；
- TicketIntent；
- TicketStatus；
- RefundStatus；
- ApprovalStatus；
- ApprovalDecision；
- Money 的 Decimal 精度、币种和非负约束。

验证：

- 金额不使用 float；
- 非法状态和金额被拒绝。

建议提交：

- feat: add core domain types

### 任务 3.2：建立 ORM 模型和迁移

创建：

- backend/src/refund_agent/models/
- backend/alembic.ini
- backend/migrations/
- backend/tests/integration/test_schema.py

表：

- users；
- orders；
- conversations；
- messages；
- tickets；
- refund_requests；
- approval_tasks；
- workflow_checkpoints；
- audit_events；
- knowledge_documents。

关键约束：

- refund_requests.idempotency_key 唯一；
- ticket 和 approval_task 带 version 字段；
- 金额使用 NUMERIC；
- 外键和必要索引完整；
- audit_events 无业务更新入口；
- knowledge_documents 包含 search_tokens。

验证：

- 空数据库可升级到最新版本；
- 可完整降级后再次升级；
- 唯一约束和外键测试通过。

建议提交：

- feat: add database schema and migrations

### 任务 3.3：演示数据与可重复初始化

创建：

- backend/src/refund_agent/seed.py
- scripts/seed-demo.sh
- backend/tests/integration/test_seed.py

演示数据：

- 客户、审批员、管理员账号；
- 399 元自动退款订单；
- 699 元审批订单；
- 低金额但带欺诈信号订单；
- 支付结果未知订单；
- 不属于当前客户的订单；
- 退款政策文档。

验证：

- 初始化脚本重复执行不会产生重复数据；
- 密码仅保存哈希；
- README 不展示真实密钥。

建议提交：

- feat: add idempotent demo data

## 6. 阶段四：身份、权限与审计基础

### 任务 4.1：JWT 登录

创建：

- backend/src/refund_agent/security/passwords.py
- backend/src/refund_agent/security/jwt.py
- backend/src/refund_agent/api/dependencies/auth.py
- backend/src/refund_agent/api/routes/auth.py
- backend/src/refund_agent/api/schemas/auth.py
- backend/tests/api/test_auth.py

行为：

- Argon2 密码哈希；
- POST /api/auth/login 返回短期 JWT；
- 禁用账号和错误密码返回统一错误；
- 日志不记录密码和 Token。

验证：

- 正确与错误登录路径；
- 过期、篡改和角色非法的 Token 被拒绝。

建议提交：

- feat: add JWT authentication

### 任务 4.2：角色与资源归属

创建：

- backend/src/refund_agent/security/authorization.py
- backend/tests/security/test_authorization.py

行为：

- CUSTOMER 只能访问自己的 conversation、ticket 和 message；
- APPROVER 只能访问可认领或已分配给自己的审批；
- ADMIN 可读取全部审计和升级任务；
- 每个查询在数据库过滤层限制范围，不在返回后过滤。

验证：

- 覆盖跨客户 ID 猜测、审批越权和管理员端点越权。

建议提交：

- feat: enforce role and ownership policies

### 任务 4.3：只追加审计服务与脱敏

创建：

- backend/src/refund_agent/audit/service.py
- backend/src/refund_agent/audit/redaction.py
- backend/tests/audit/test_redaction.py
- backend/tests/audit/test_audit_service.py

行为：

- 事件包含 actor、action、entity、trace_id 和时间；
- 字段级屏蔽密码、Token、API Key 和支付敏感信息；
- 应用服务只暴露 append，不暴露 update/delete。

验证：

- 嵌套对象和异常文本中的敏感字段被脱敏；
- 鉴权失败也生成安全审计事件。

建议提交：

- feat: add append-only audit events

## 7. 阶段五：规则、知识库和外部系统适配器

### 任务 5.1：退款政策规则

创建：

- config/rules/refund_policy.yaml
- backend/src/refund_agent/rules/loader.py
- backend/src/refund_agent/rules/policy.py
- backend/tests/rules/test_policy.py

行为：

- 校验订单状态、商品属性和退货时效；
- 使用订单事实计算可退金额；
- 对规则文件计算 SHA-256 rule_version；
- 拒绝格式不合法或缺字段的规则文件。

验证：

- 边界日期、已退款订单和特殊商品用例；
- 500 元边界使用 Decimal 精确判断。

建议提交：

- feat: add deterministic refund policy rules

### 任务 5.2：风险与审批规则

创建：

- config/rules/risk_rules.yaml
- backend/src/refund_agent/rules/risk.py
- backend/tests/rules/test_risk.py

默认规则：

- 金额大于 500 元；
- 高频退款；
- 欺诈标记；
- 数据冲突；
- 模型置信度低于阈值。

输出：

- risk_level；
- matched_rule_ids；
- reasons；
- requires_approval；
- rule_version。

验证：

- 500 元不因金额规则审批，500.01 元审批；
- 多条规则同时命中时证据完整；
- LLM 不能覆盖 requires_approval。

建议提交：

- feat: add configurable risk rules

### 任务 5.3：端口与 Mock 适配器

创建：

- backend/src/refund_agent/ports/order.py
- backend/src/refund_agent/ports/logistics.py
- backend/src/refund_agent/ports/payment.py
- backend/src/refund_agent/ports/knowledge.py
- backend/src/refund_agent/ports/llm.py
- backend/src/refund_agent/adapters/mock/
- backend/tests/contracts/

Mock 支持：

- 成功；
- 明确失败；
- 暂时超时；
- 支付结果未知；
- 使用同一幂等键返回同一支付结果。

验证：

- 每个端口有契约测试；
- 后续 HTTP 适配器必须复用同一测试套件。

建议提交：

- feat: add integration ports and mock adapters

### 任务 5.4：知识库全文检索

创建：

- backend/src/refund_agent/adapters/postgres/knowledge.py
- backend/src/refund_agent/knowledge/tokenizer.py
- backend/tests/integration/test_knowledge_search.py

行为：

- 使用 jieba 生成 search_tokens；
- PostgreSQL simple 配置完成文本查询；
- 仅返回当前有效版本；
- 结果包含文档 ID、版本、片段和有效期。

验证：

- “七天无理由”“退款时效”等中文查询可命中预置文档；
- 失效文档不参与决策。

建议提交：

- feat: add versioned policy knowledge search

## 8. 阶段六：LLM 边界与 Agent 节点

### 任务 6.1：Fake 与兼容模型客户端

创建：

- backend/src/refund_agent/adapters/llm/fake.py
- backend/src/refund_agent/adapters/llm/openai_compatible.py
- backend/src/refund_agent/adapters/llm/schemas.py
- backend/tests/adapters/test_llm_clients.py

行为：

- fake 模式根据固定演示输入生成确定性结构化结果；
- compatible 模式支持 Base URL、API Key、模型、超时和有限重试；
- 所有输出经过 Pydantic 校验；
- 无效、低置信度或耗尽重试返回可分类错误。

验证：

- 测试不访问真实网络；
- 模型返回恶意工具名或自由文本时被拒绝；
- API Key 不出现在异常和日志中。

建议提交：

- feat: add bounded LLM clients

### 任务 6.2：提示词文件

创建：

- backend/prompts/classifier.md
- backend/prompts/policy_summary.md
- backend/prompts/notification.md
- backend/src/refund_agent/prompts/loader.py
- backend/tests/prompts/test_prompt_loader.py

要求：

- 用户输入放在明确的不可信数据边界；
- 提示词要求结构化输出；
- 不让模型计算金额或决定审批；
- 提示词缺失或版本不合法时启动失败。

验证：

- Prompt 注入样例不会变成工具或支付指令。

建议提交：

- feat: add versioned agent prompts

### 任务 6.3：实现独立 Agent 节点

创建：

- backend/src/refund_agent/agents/classifier.py
- backend/src/refund_agent/agents/order.py
- backend/src/refund_agent/agents/policy.py
- backend/src/refund_agent/agents/risk.py
- backend/src/refund_agent/agents/refund.py
- backend/src/refund_agent/agents/notify.py
- backend/tests/agents/

每个节点：

- 输入和输出使用明确 Schema；
- 只依赖所需端口；
- 写入结构化审计事件；
- 不自行控制全局工作流；
- 可独立单元测试。

验证：

- 每个节点的成功、拒绝和依赖失败路径；
- RefundAgent 在缺少授权审批时无法调用支付。

建议提交：

- feat: implement isolated agent nodes

## 9. 阶段七：LangGraph、队列与恢复

### 任务 7.1：工作流状态与拓扑

创建：

- backend/src/refund_agent/workflows/state.py
- backend/src/refund_agent/workflows/refund_graph.py
- backend/tests/workflows/test_graph_routes.py

路径：

- 退款 → 订单 → 政策 → 风险 → 自动退款或审批；
- 换货、异常、低置信度 → MANUAL_REVIEW；
- 政策拒绝 → REJECTED；
- 成功退款 → 物流指引 → COMPLETED。

验证：

- 路由测试不依赖数据库或网络；
- 每个终态都可达且没有无出口状态。

建议提交：

- feat: define refund workflow graph

### 任务 7.2：PostgreSQL checkpoint 与审批中断

创建：

- backend/src/refund_agent/workflows/checkpoint.py
- backend/src/refund_agent/workflows/interrupts.py
- backend/tests/integration/test_workflow_checkpoint.py

行为：

- 创建审批任务和 WAITING_APPROVAL 状态后保存 checkpoint；
- 审批前没有支付调用；
- 批准后从 checkpoint 恢复；
- 拒绝后进入 REJECTED；
- 修改金额不得超过可退上限。

验证：

- 模拟 Worker 重启后仍能恢复；
- 已完成节点不重复产生副作用。

建议提交：

- feat: persist workflow interrupts and resume state

### 任务 7.3：Celery 任务、锁和幂等支付

创建：

- backend/src/refund_agent/worker/celery_app.py
- backend/src/refund_agent/worker/tasks.py
- backend/src/refund_agent/infrastructure/locks.py
- backend/src/refund_agent/application/refunds.py
- backend/tests/integration/test_worker_idempotency.py

行为：

- API 只投递 start_workflow 或 resume_workflow；
- 以 ticket_id 获取带过期时间的 Redis 锁；
- refund_requests 唯一键防止重复支付；
- 支付结果 UNKNOWN 进入 MANUAL_REVIEW 且不自动重试；
- 明确的临时查询失败使用有限退避重试。

验证：

- 并发运行同一工单只产生一次支付；
- 重放 Celery 消息不会重复退款；
- 进程在支付后、推进状态前崩溃仍可安全恢复。

建议提交：

- feat: add durable workflow worker and idempotency

## 10. 阶段八：业务 API

### 任务 8.1：对话与工单 API

创建：

- backend/src/refund_agent/api/routes/chat.py
- backend/src/refund_agent/api/routes/tickets.py
- backend/src/refund_agent/api/schemas/chat.py
- backend/src/refund_agent/api/schemas/tickets.py
- backend/src/refund_agent/application/tickets.py
- backend/tests/api/test_chat.py
- backend/tests/api/test_tickets.py

行为：

- POST /api/chat/messages 创建或继续工单；
- GET /api/tickets 只返回有权访问的数据；
- GET /api/tickets/{id} 返回消息、业务步骤和状态；
- 客户不能伪造 customer_id；
- API 返回 202 后由 Worker 处理。

验证：

- 自动退款、人工转派和归属越权 API 路径。

建议提交：

- feat: add chat and ticket APIs

### 任务 8.2：审批 API

创建：

- backend/src/refund_agent/api/routes/approvals.py
- backend/src/refund_agent/api/schemas/approvals.py
- backend/src/refund_agent/application/approvals.py
- backend/tests/api/test_approvals.py

行为：

- 查询待处理、已认领和升级审批；
- 原子认领审批；
- 批准、拒绝、修改后批准或转派；
- version 字段实现乐观锁；
- 决定成功后投递恢复任务。

验证：

- 两名审批员并发决定时只有一个成功；
- 客户和未授权审批员被拒绝；
- 超上限金额被拒绝；
- 重复决定返回冲突。

建议提交：

- feat: add approval APIs and optimistic locking

### 任务 8.3：审计 API 与统一错误

创建：

- backend/src/refund_agent/api/routes/audit.py
- backend/src/refund_agent/api/errors.py
- backend/src/refund_agent/api/middleware/trace.py
- backend/tests/api/test_audit.py
- backend/tests/api/test_errors.py

行为：

- 仅 ADMIN 可筛选审计事件；
- 支持 ticket_id、event_type 和时间范围；
- 所有错误包含 code、message 和 trace_id；
- 生产响应不暴露堆栈、提示词或凭据。

验证：

- 脱敏、权限、分页和异常响应结构。

建议提交：

- feat: add audit API and safe errors

## 11. 阶段九：前端基础与客户体验

### 任务 9.1：设计系统和应用壳

创建：

- frontend/src/styles/
- frontend/src/components/layout/
- frontend/src/router.tsx
- frontend/src/api/client.ts
- frontend/src/auth/
- frontend/src/pages/LoginPage.tsx
- frontend/src/tests/

要求：

- 响应式布局；
- 清晰的加载、空、错误和禁用状态；
- 键盘可操作；
- 可见焦点；
- 颜色对比满足 WCAG AA；
- Token 仅保存在会话级存储。

验证：

- 登录与按角色跳转的组件测试；
- 未登录访问受保护页面时跳转登录。

建议提交：

- feat: add frontend shell and authentication

### 任务 9.2：客户对话页

创建：

- frontend/src/pages/CustomerChatPage.tsx
- frontend/src/features/chat/
- frontend/src/features/tickets/
- frontend/src/tests/CustomerChatPage.test.tsx

行为：

- 发送消息后显示已接受状态；
- 轮询工单直到终态或等待审批；
- 展示订单确认、政策结果、审批等待、退款结果和退货指引；
- 不展示内部 Agent 名称和推理过程；
- 网络错误可安全重试，不重复创建工单。

验证：

- 自动退款、等待审批、拒绝和转人工 UI 状态。

建议提交：

- feat: add customer refund conversation

## 12. 阶段十：审批与审计前端

### 任务 10.1：审批工作台

创建：

- frontend/src/pages/ApprovalDashboardPage.tsx
- frontend/src/features/approvals/
- frontend/src/tests/ApprovalDashboardPage.test.tsx

展示：

- 订单快照；
- 政策证据；
- 可退与申请金额；
- 风险规则和原因；
- AI 建议；
- 审计时间线。

操作：

- 认领；
- 批准；
- 拒绝；
- 修改后批准；
- 转派。

验证：

- 表单金额上限；
- 提交中禁用；
- 并发冲突提示；
- 决定后列表与详情刷新。

建议提交：

- feat: add human approval dashboard

### 任务 10.2：审计记录页

创建：

- frontend/src/pages/AuditPage.tsx
- frontend/src/features/audit/
- frontend/src/tests/AuditPage.test.tsx

行为：

- 按工单、类型和时间过滤；
- 分页查看脱敏事件；
- 明确显示 actor、action、结果和 trace_id；
- 非管理员无法导航或调用页面 API。

验证：

- 过滤、分页、空状态和权限状态。

建议提交：

- feat: add audit event explorer

## 13. 阶段十一：超时升级、可观测性与安全加固

### 任务 11.1：审批超时升级

创建：

- backend/src/refund_agent/worker/schedules.py
- backend/src/refund_agent/application/escalations.py
- backend/tests/integration/test_approval_escalation.py
- 更新 docker-compose.yml，增加 scheduler 服务

行为：

- scheduler 通过 Celery Beat 周期扫描过期审批；
- 原子地改为 ESCALATED；
- 写入审计事件；
- 管理员可查询；
- 不自动执行退款。

验证：

- 多次扫描不会重复升级或重复审计。

建议提交：

- feat: escalate expired approvals

### 任务 11.2：结构化日志和指标

创建：

- backend/src/refund_agent/observability/logging.py
- backend/src/refund_agent/observability/metrics.py
- backend/tests/observability/

要求：

- API 和 Worker 日志关联 trace_id、ticket_id、workflow_run_id；
- 记录工单量、自动完成率、转人工率、审批等待和适配器失败；
- 敏感字段在格式化前脱敏。

验证：

- 测试捕获日志并确认无密码、Token 或 API Key。

建议提交：

- feat: add structured observability

### 任务 11.3：安全回归

新增测试：

- Prompt 注入要求忽略规则并退款；
- 客户篡改订单 ID；
- 客户直接调用审批端点；
- 审批员将金额提高到上限以上；
- 伪造“已审批”工作流状态；
- 重复和并发退款请求；
- 模型返回任意工具名、URL 或 SQL；
- 日志和错误响应泄露敏感值。

修复范围只限于测试发现的问题。

验证：

- 全部安全回归测试通过。

建议提交：

- test: harden refund workflow security

## 14. 阶段十二：端到端验收与文档

### 任务 12.1：Playwright 端到端测试

创建：

- frontend/playwright.config.ts
- frontend/e2e/automatic-refund.spec.ts
- frontend/e2e/approval-resume.spec.ts
- frontend/e2e/fraud-review.spec.ts
- frontend/e2e/unknown-payment.spec.ts
- frontend/e2e/authorization.spec.ts

固定场景：

1. 399 元自动退款；
2. 699 元审批后恢复；
3. 低金额欺诈信号进入审批；
4. 支付结果未知且不重复退款；
5. 三种角色的越权访问被拒绝。

验证：

- 全新数据库上运行；
- 每个场景验证 UI、数据库最终状态和关键审计事件。

建议提交：

- test: add end-to-end refund scenarios

### 任务 12.2：运行手册与架构文档

更新：

- README.md
- docs/architecture.md
- docs/demo-guide.md
- docs/security.md

必须说明：

- 环境要求与一键启动；
- 数据迁移和演示数据；
- 演示账号；
- Fake 与兼容模型模式切换；
- 五条演示路径；
- 故障排查；
- 已知 MVP 限制；
- 不得用于真实资金系统的声明。

验证：

- 按 README 在干净环境中完成启动和五条演示；
- 文档命令可复制执行；
- 仓库无凭据。

建议提交：

- docs: add setup demo and security guides

### 任务 12.3：最终质量门禁

执行：

- 后端格式化与 lint；
- 后端 mypy；
- 后端完整 pytest 和覆盖率；
- 前端 lint 和 typecheck；
- 前端组件测试；
- Playwright E2E；
- docker compose config；
- docker compose 构建和健康检查；
- 迁移从空数据库执行；
- 敏感信息扫描。

完成条件：

- 所有命令成功；
- 五条验收场景通过；
- 没有高优先级已知缺陷；
- git status 干净；
- README 与实际行为一致。

建议提交：

- chore: complete MVP acceptance checks

## 15. 推荐执行顺序

严格按阶段一至十二执行。关键依赖关系如下：

~~~mermaid
flowchart LR
    A["骨架与门禁"] --> B["基础设施"]
    B --> C["领域与数据库"]
    C --> D["身份与审计"]
    C --> E["规则与适配器"]
    D --> F["Agent 与工作流"]
    E --> F
    F --> G["队列、恢复、幂等"]
    G --> H["业务 API"]
    H --> I["客户前端"]
    H --> J["审批与审计前端"]
    I --> K["安全与 E2E"]
    J --> K
    K --> L["文档与最终验收"]
~~~

前端可在业务 API 契约稳定后开始。不得在支付幂等、审批并发和权限测试完成前宣称退款闭环完成。

## 16. 里程碑

### 里程碑 M1：可启动骨架

阶段一至三完成。Docker Compose 可运行，数据库迁移和演示数据可重复执行。

### 里程碑 M2：后端退款闭环

阶段四至八完成。通过 API 和测试可完成自动退款、审批暂停与恢复、未知支付转人工。

### 里程碑 M3：可交互全栈演示

阶段九至十完成。三类角色能够通过页面完成各自任务。

### 里程碑 M4：验收完成

阶段十一至十二完成。安全回归、E2E、文档和全新环境启动均通过。

## 17. 实施过程中的变更规则

- 若需要改变已批准的业务范围、审批策略、数据安全边界或技术栈，先更新设计文档并请求确认；
- 小型实现细节可以在不改变接口和行为的前提下调整，并记录在提交信息中；
- 真实外部服务接入、多人审批、WebSocket、向量数据库和 Kubernetes 不得作为顺手扩展加入本期；
- 任何会造成真实资金或外部系统状态变化的配置不得加入演示环境。
