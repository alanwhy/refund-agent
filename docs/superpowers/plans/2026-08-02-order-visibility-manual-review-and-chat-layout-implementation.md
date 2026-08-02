# 订单可见性、异常处理与客户对话布局实施计划

> 对应设计：`docs/superpowers/specs/2026-08-02-order-visibility-manual-review-and-chat-layout-design.md`

## 1. 目标

本计划修复真实网关演示中发现的多轮消息协议缺陷，并补齐退款审批之外的技术异常处理、按角色
授权的订单页面和桌面端单屏对话布局。

完成后系统必须满足：

- `RequestUserInput` 中断恢复后生成匹配 tool call ID 的 `ToolMessage`，第二轮模型调用不再因
  消息协议返回 HTTP 400；
- 不存在或非本人订单由确定性服务端逻辑拒绝，并向客户显示明确、安全的提示；
- 退款审批和技术异常分别进入 `ApprovalTask` 与 `ManualReviewTask`；
- 审核员和管理员可以处理技术异常，但异常页面不能批准退款或调用支付；
- 用户、审核员和管理员只能读取其角色范围内的订单；
- 桌面端输入框始终位于当前视口，页面根节点不随消息增长产生纵向滚动；
- 历史 `MANUAL_REVIEW` 工单可以进入异常处理队列；
- 自动化测试、真实模型 smoke 和三角色浏览器路径全部通过。

## 2. 执行原则

1. 每项行为先增加失败测试，再实现最小修正。
2. 业务事实只从 PostgreSQL 读取；checkpoint 不作为权限、金额或订单归属依据。
3. API 的角色过滤必须在后端查询层完成，不能依赖前端隐藏。
4. 异常处理服务不得依赖审批服务，也不得调用支付适配器。
5. 所有新增副作用使用唯一约束、稳定去重键或乐观锁，允许节点重放。
6. 自动化测试使用 `ScriptedModel`；真实网关只通过显式 smoke 或浏览器演示调用。
7. 不修改或提交用户的 `.env`；日志和测试输出不得显示 API Key。
8. 每阶段形成可单独审查和回滚的提交，最终推送 `main`。

## 3. 目标文件结构

```text
backend/
  migrations/versions/
    0004_manual_review_tasks_and_submitted_order.py
  src/refund_agent/
    agent/nodes/
      conversation.py
      execution.py
    api/routes/
      orders.py
      manual_reviews.py
    domain/
      enums.py
    manual_review/
      __init__.py
      service.py
    models.py
    api/schemas.py
  tests/
    test_agent_graph.py
    test_agent_security.py
    test_agent_replay.py
    test_api_orders.py
    test_api_manual_reviews.py
    test_migrations.py

frontend/src/
  components/
    AppShell.tsx
    StatusPill.tsx
  pages/
    OrdersPage.tsx
    ManualReviewPage.tsx
    CustomerChatPage.tsx
  test/
    OrdersPage.test.tsx
    ManualReviewPage.test.tsx
    CustomerChatPage.test.tsx
    AppShell.test.tsx
  App.tsx
  styles.css
  types.ts
```

若实现过程中页面文件过大，只允许提取与本需求直接相关的展示组件，不进行无关重构。

## 4. 阶段零：冻结当前运行基线

### 任务 0.1：记录当前状态

**不修改代码。**

1. 确认工作树除已提交设计和计划外无用户修改。
2. 记录当前服务状态和真实故障工单 `a346ff81-54b3-4d56-849a-89c2c47c9bba`：
   - 状态 `MANUAL_REVIEW`；
   - 没有 `ApprovalTask`；
   - 审计原因 `MODEL_UNAVAILABLE`；
   - 实际网关错误为第二轮 HTTP 400。
3. 运行基线：

   ```bash
   docker compose exec -T api sh -lc \
     "ruff check src tests migrations && mypy src && pytest -q"
   docker compose exec -T web sh -lc \
     "npm run typecheck && npm run lint && npm test -- --run && npm run build"
   ```

4. 显式运行真实模型工具调用 smoke，确认当前网关可用：

   ```bash
   docker compose exec -T -e RUN_REAL_MODEL_SMOKE=1 api \
     pytest -q tests/smoke/test_real_model_gateway.py
   ```

**完成条件**

- 基线失败与本需求变更分开记录；
- 本阶段不提交代码。

## 5. 阶段一：修复 LangGraph 补问恢复协议

### 任务 1.1：为控制调用生成 ToolMessage

**修改文件**

- `backend/src/refund_agent/agent/nodes/conversation.py`
- `backend/tests/test_agent_graph.py`
- `backend/tests/test_checkpoint_resume.py`

**先写测试**

1. 首轮 `RequestUserInput` 后进入 `WAITING_USER`。
2. `Command(resume=...)` 后传给模型的消息顺序为：
   - 原始 `AIMessage` tool call；
   - 相同 `tool_call_id` 的 `ToolMessage`；
   - 用户原始 `HumanMessage`。
3. ToolMessage 内容是固定结构化结果，不包含 customer ID、金额或审批状态。
4. checkpoint Runtime 重建后恢复仍生成一次且只生成一次 ToolMessage。
5. 节点重放不重复写入业务 Message 或审计事件。

**实现**

1. 从最后一条 AIMessage 提取唯一 `RequestUserInput` call 及 ID。
2. `ask_user` 从 interrupt 恢复后返回两个 Graph 消息：
   - `ToolMessage(name="RequestUserInput", tool_call_id=..., content=...)`；
   - `HumanMessage(content=resumed["message"])`。
3. ToolMessage 的 JSON 仅包含 `status=user_input_received` 和用户回答了哪些缺失字段。
4. 保持业务消息表只有真实客户消息与客户可见助手消息；内部 ToolMessage 只进入 checkpoint。

**验证**

```bash
docker compose exec -T api pytest -q \
  tests/test_agent_graph.py tests/test_checkpoint_resume.py -k user
```

**提交**

```text
fix: preserve tool protocol across user input resume
```

### 任务 1.2：用真实兼容消息约束做回归验证

**修改文件**

- `backend/tests/support/scripted_model.py`
- `backend/tests/test_agent_graph.py`
- 可选：`backend/tests/smoke/test_real_model_gateway.py`

**实现与测试**

1. 为 ScriptedModel 增加可选的消息捕获，不改变默认测试行为。
2. 回归测试检查第二轮输入中不存在“未响应 tool call”。
3. 显式 smoke 增加两轮场景：模型请求订单号，测试代码提供 ToolMessage 和用户答案，模型能继续
   返回有效工具调用。
4. smoke 不创建业务工单、不调用支付，仅验证消息协议和工具调用能力。

**验证**

```bash
docker compose exec -T -e RUN_REAL_MODEL_SMOKE=1 api \
  pytest -q tests/smoke/test_real_model_gateway.py
```

**提交**

```text
test: cover multi-turn compatible model protocol
```

## 6. 阶段二：确定性订单拒绝与提交订单号留存

### 任务 2.1：保存 submitted_order_number

**修改文件**

- `backend/src/refund_agent/models.py`
- `backend/src/refund_agent/api/schemas.py`
- `backend/src/refund_agent/api/routes/tickets.py`
- `backend/src/refund_agent/agent/nodes/conversation.py`
- `backend/migrations/versions/0004_manual_review_tasks_and_submitted_order.py`
- `backend/tests/test_agent_graph.py`
- `backend/tests/test_api.py`

**先写测试**

1. `SubmitRefundContext(order_number="ORD-400")` 即使找不到 Order，也保存
   `ticket.submitted_order_number == "ORD-400"`。
2. 已验证订单同时保留 `submitted_order_number` 和可信 `order_id`。
3. TicketSummary 在没有 `order_id` 时使用 submitted_order_number 展示订单号。
4. submitted_order_number 不能被支付节点作为可信订单关联使用。

**实现**

1. Ticket 增加可空、带索引的 `submitted_order_number`。
2. `validate_context` 在查询 Order 之前写入规范化订单号。
3. API Summary 的订单号优先使用已验证 Order，否则使用 submitted_order_number。
4. 不从任意自由文本直接写该字段；只接受通过 `SubmitRefundContext` Schema 的订单号。

### 任务 2.2：订单不存在时使用确定性终态回复

**修改文件**

- `backend/src/refund_agent/agent/nodes/conversation.py`
- `backend/tests/test_agent_graph.py`
- `backend/tests/test_agent_security.py`

**先写测试**

1. `ORD-400` 进入 `REJECTED/order_rejected`。
2. 客户消息为：
   `未找到订单 ORD-400，或该订单不属于当前账号。请核对订单号后重试。`
3. 不创建 ApprovalTask、ManualReviewTask 或 RefundRequest。
4. `ORD-500-OTHER` 返回相同类别提示，不能暴露订单属于其他人。
5. 模型生成回复失败也不改变确定性拒绝文本。

**实现**

1. `validate_context` 返回稳定错误码 `ORDER_NOT_FOUND_OR_NOT_OWNED`。
2. `response_node` 对该错误码直接使用服务端模板，不调用模型润色。
3. 追加 `order.rejected` 审计，details 只记录提交订单号和受控原因码。

**验证**

```bash
docker compose exec -T api pytest -q \
  tests/test_agent_graph.py tests/test_agent_security.py -k "not_found or ownership"
```

**提交**

```text
fix: reject unavailable customer orders deterministically
```

## 7. 阶段三：异常任务数据模型与迁移

### 任务 3.1：增加异常枚举与模型

**修改文件**

- `backend/src/refund_agent/domain/enums.py`
- `backend/src/refund_agent/models.py`
- `backend/migrations/versions/0004_manual_review_tasks_and_submitted_order.py`
- `backend/tests/test_migrations.py`
- 新增 `backend/tests/test_manual_review_service.py`

**数据定义**

- `ManualReviewStatus`: `PENDING`、`RESOLVED`、`UNRESOLVABLE`；
- `ManualReviewCategory`: `MODEL_FAILURE`、`PAYMENT_UNKNOWN`、
  `DATA_INCONSISTENCY`、`SECURITY_REJECTION`；
- ManualReviewTask 按设计规格实现，`ticket_id` 唯一并索引 status、assigned_to、created_at；
- technical_summary 限定长度，服务层只接受受控文本。

**先写测试**

1. 同一 ticket 不能创建两个异常任务。
2. 状态、版本和时间字段有正确默认值。
3. assigned_to/resolved_by 只能关联有效用户。
4. 0004 upgrade 后增加 Ticket 字段和异常表。
5. 0004 downgrade 能按依赖顺序回滚。

### 任务 3.2：迁移历史 MANUAL_REVIEW 工单

**修改文件**

- `backend/migrations/versions/0004_manual_review_tasks_and_submitted_order.py`
- `backend/tests/test_migrations.py`

**先写测试**

1. 截图中的历史故障型工单迁移为 `MODEL_FAILURE/PENDING`。
2. RefundRequest 为 UNKNOWN 的历史工单迁移为 `PAYMENT_UNKNOWN/PENDING`。
3. 无法推断的 MANUAL_REVIEW 迁移为 `DATA_INCONSISTENCY/PENDING`。
4. 迁移不为 REJECTED、COMPLETED 或 WAITING_APPROVAL 创建异常任务。
5. 重复执行迁移逻辑不会创建重复任务。

**实现注意**

- 先增加 submitted_order_number，再从受约束的订单号格式中回填；
- 技术摘要只保存受控中文说明，不复制完整审计 details；
- 生成 ID、created_at 和版本时兼容 PostgreSQL；
- migration 完成后实际查询确认历史工单进入异常队列。

**验证**

```bash
docker compose run --rm migrate
docker compose exec -T postgres psql -U refund -d refund -c \
  "select status, category, count(*) from manual_review_tasks group by status, category;"
```

**提交**

```text
feat: persist technical manual review tasks
```

## 8. 阶段四：统一异常创建服务

### 任务 4.1：实现幂等异常服务

**新增/修改文件**

- 新增 `backend/src/refund_agent/manual_review/__init__.py`
- 新增 `backend/src/refund_agent/manual_review/service.py`
- `backend/src/refund_agent/agent/nodes/conversation.py`
- `backend/src/refund_agent/agent/nodes/execution.py`
- `backend/tests/test_manual_review_service.py`
- `backend/tests/test_agent_replay.py`

**服务接口**

实现单一入口，例如：

```python
ensure_manual_review(
    db,
    *,
    ticket,
    category,
    technical_summary,
    run_id,
    node_name,
) -> ManualReviewTask
```

**先写测试**

1. 模型不可用创建 `MODEL_FAILURE`。
2. 支付 UNKNOWN 创建 `PAYMENT_UNKNOWN`。
3. 未知工具、过量工具或非法控制调用创建 `SECURITY_REJECTION`。
4. 业务状态不完整的不可恢复异常创建 `DATA_INCONSISTENCY`。
5. 同一节点重放不重复任务、客户消息或审计事件。
6. technical_summary 不包含 Bearer token、API Key 或原始请求体。

**实现**

1. 替换当前 `manual_review` 节点中的散落写逻辑。
2. payment UNKNOWN 分支调用统一服务，而不是只修改 Ticket。
3. 对客户统一写入：`当前申请暂时无法自动完成，已转交售后专员处理。`
4. category 由受控错误码映射，不接受模型自由文本。
5. 保留 Ticket `MANUAL_REVIEW`，但后台处理状态由 ManualReviewTask 管理。

**验证**

```bash
docker compose exec -T api pytest -q \
  tests/test_manual_review_service.py tests/test_agent_replay.py tests/test_agent_security.py
```

**提交**

```text
refactor: centralize replay-safe manual review creation
```

## 9. 阶段五：异常处理 API

### 任务 5.1：增加异常查询接口

**新增/修改文件**

- 新增 `backend/src/refund_agent/api/routes/manual_reviews.py`
- `backend/src/refund_agent/api/schemas.py`
- `backend/src/refund_agent/api/app.py`
- 新增 `backend/tests/test_api_manual_reviews.py`

**先写测试**

1. 客户访问列表或详情返回 403。
2. 审核员和管理员可以读取异常列表。
3. 列表包括提交订单号、验证后的订单摘要、客户、分类、状态、处理人和版本。
4. 不返回原始堆栈、秘密、Prompt 或模型完整响应。
5. 不存在或无权访问的详情返回 404。

**实现**

- `GET /api/manual-review-tasks`
- `GET /api/manual-review-tasks/{task_id}`
- 默认按 PENDING 优先、创建时间倒序；
- 支持 status/category 查询参数，限制分页上限；
- 审核员和管理员都能看到异常任务；客户不可访问。

### 任务 5.2：增加认领和处理接口

**新增/修改文件**

- `backend/src/refund_agent/api/routes/manual_reviews.py`
- `backend/src/refund_agent/api/schemas.py`
- `backend/tests/test_api_manual_reviews.py`

**先写测试**

1. 审核员认领未分配任务成功并增加 version。
2. 管理员可重新分配给有效审核员。
3. 两人用同一旧 version 操作时只有一次成功，另一方返回 409。
4. resolution_note 为空或超长返回 422。
5. RESOLVED/UNRESOLVABLE 后不能再次终结。
6. 操作不修改 ApprovalTask、RefundRequest，也不投递退款 Worker 任务。
7. 写入 `manual_review.assigned/resolved/unresolvable` 审计。

**接口**

- `POST /api/manual-review-tasks/{task_id}/assign`
- `POST /api/manual-review-tasks/{task_id}/resolution`

**验证**

```bash
docker compose exec -T api pytest -q tests/test_api_manual_reviews.py
```

**提交**

```text
feat: add role-protected manual review APIs
```

## 10. 阶段六：按角色授权的订单 API

### 任务 6.1：实现订单查询范围

**新增/修改文件**

- 新增 `backend/src/refund_agent/api/routes/orders.py`
- `backend/src/refund_agent/api/schemas.py`
- `backend/src/refund_agent/api/app.py`
- 新增 `backend/tests/test_api_orders.py`

**先写测试**

1. 客户列表只返回自己的订单，详情不能读取 `ORD-500-OTHER`。
2. 审核员只看到有 ApprovalTask，且未分配或分配给自己的订单。
3. 审核员看不到普通客户订单和仅有 ManualReviewTask 的订单。
4. 管理员看到所有订单及客户摘要。
5. 所有角色的详情使用与列表相同的权限 predicate，不能通过猜 ID 绕过。
6. 客户响应不含 fraud_flag、payment_behavior 或其他客户字段。
7. 审核员响应含审批状态和关联工单，不含资金模拟内部字段。
8. 管理员响应含所属客户、关联工单/审批/异常引用，但不提供退款执行动作。

**实现**

- `GET /api/orders`
- `GET /api/orders/{order_id}`
- 查询 predicate 提取为可复用函数，列表与详情共同使用；
- 支持安全的 status 过滤和有限分页；
- 不接受 customer_id 参数来扩大普通角色权限。

**验证**

```bash
docker compose exec -T api pytest -q tests/test_api_orders.py
```

**提交**

```text
feat: expose role-scoped order APIs
```

## 11. 阶段七：前端导航和订单页面

本阶段使用既有“归舟”视觉系统，不引入新设计语言。订单页面强调业务对象、状态和关联工单，
不做通用后台模板式重构。

### 任务 7.1：按角色显示导航

**修改文件**

- `frontend/src/components/AppShell.tsx`
- `frontend/src/App.tsx`
- 新增 `frontend/src/test/AppShell.test.tsx`

**先写测试**

1. 客户看到“售后对话、我的订单”。
2. 审核员看到“退款审批、审批订单、异常处理”。
3. 管理员看到“退款审批、全部订单、异常处理、审计记录”。
4. 手动输入无权路由仍被 Protected route 重定向，不能只靠隐藏导航。

### 任务 7.2：实现订单列表与详情

**新增/修改文件**

- 新增 `frontend/src/pages/OrdersPage.tsx`
- `frontend/src/types.ts`
- `frontend/src/styles.css`
- 新增 `frontend/src/test/OrdersPage.test.tsx`

**页面行为**

- 客户标题为“我的订单”，展示商品、订单号、金额、状态、签收时间和退款工单状态；
- 审核员标题为“审批订单”，展示审批状态、风险原因和负责关系；
- 管理员标题为“全部订单”，额外展示客户并提供关联记录入口；
- 不同角色共用 API 类型的公共字段，通过角色安全字段有条件渲染；
- 提供加载、空列表、403/404 和网络失败状态。

**测试**

1. 三种角色文案与字段正确。
2. 客户页面不渲染内部风险/客户字段。
3. 审核员只渲染 API 返回的审批订单。
4. 管理员展示客户和关联记录。

**验证**

```bash
docker compose exec -T web sh -lc \
  "npm run typecheck && npm run lint && npm test -- --run"
```

**提交**

```text
feat: add role-scoped order pages
```

## 12. 阶段八：异常处理页面

### 任务 8.1：实现队列与详情

**新增/修改文件**

- 新增 `frontend/src/pages/ManualReviewPage.tsx`
- `frontend/src/App.tsx`
- `frontend/src/types.ts`
- `frontend/src/components/StatusPill.tsx`
- `frontend/src/styles.css`
- 新增 `frontend/src/test/ManualReviewPage.test.tsx`

**页面结构**

- 左侧异常队列：提交订单号、客户、类别、状态、处理人；
- 右侧详情：客户可见状态、验证订单（若存在）、受控技术摘要、时间线；
- 操作区：认领、内部备注、已解决、无法解决；
- 不出现“批准退款”按钮，不提供金额编辑；
- 版本冲突时提示“任务已被其他处理人更新”并刷新。

**先写测试**

1. PENDING 异常可认领和填写备注。
2. RESOLVED/UNRESOLVABLE 禁用终结操作。
3. 409 会刷新并显示冲突提示。
4. 页面不含批准退款按钮或支付动作。
5. 无验证订单时显示用户提交订单号，不伪造商品信息。

**验证**

```bash
docker compose exec -T web npm test -- --run src/test/ManualReviewPage.test.tsx
```

**提交**

```text
feat: add technical exception handling workspace
```

## 13. 阶段九：客户对话单屏布局

### 任务 9.1：实现 A 方案视口布局

**修改文件**

- `frontend/src/pages/CustomerChatPage.tsx`
- `frontend/src/styles.css`
- `frontend/src/test/CustomerChatPage.test.tsx`

**布局实现**

桌面断点下：

1. AppShell 和 main workspace 使用 `height: 100dvh` / `min-height: 0`。
2. 客户工作区高度为 `calc(100dvh - 4.6rem)`，根层 `overflow: hidden`。
3. conversation-panel 改为三行 Grid：header、`minmax(0, 1fr)` messages、composer。
4. messages 独立滚动，新增消息后滚动到最新内容但尊重减少动画设置。
5. ticket-list 和 evidence-panel 独立滚动。
6. Composer 不使用 fixed/absolute，不遮挡消息。
7. 在 `max-width: 760px` 恢复自然高度和文档流，兼容软键盘。

**先写测试**

1. Composer DOM 始终位于 conversation-panel 的固定第三分区。
2. 只有 RUNNING/WAITING_APPROVAL 定时刷新，不影响输入可用性。
3. 等待用户时输入框仍可见且提交同 ticket。
4. 增加 CSS/DOM 回归断言或浏览器尺寸断言，验证桌面页面
   `document.documentElement.scrollHeight <= window.innerHeight`。
5. 验证 `.messages.scrollHeight` 可大于 clientHeight，说明滚动发生在消息区内部。

### 任务 9.2：改善确定性拒绝展示

**修改文件**

- `frontend/src/pages/CustomerChatPage.tsx`
- `frontend/src/components/StatusPill.tsx`
- `frontend/src/styles.css`

**实现**

- REJECTED 工单左侧显示 submitted_order_number；
- 消息中展示确定性订单提示；
- 处理轨迹停在“查询并核验订单”，后续步骤不误显示已完成；
- 用户可以在终态工单后用同一输入区域发起新工单。

**验证**

```bash
docker compose exec -T web sh -lc \
  "npm run typecheck && npm run lint && npm test -- --run && npm run build"
```

**提交**

```text
fix: keep customer chat composer within desktop viewport
```

## 14. 阶段十：全链路集成与浏览器验收

### 任务 10.1：后端集成路径

**新增/修改文件**

- 按需新增 `backend/tests/test_agent_e2e.py`
- 只修改与失败路径直接相关的现有测试

**场景**

1. 缺订单号 → WAITING_USER → 恢复 → ORD-400 → REJECTED，且无审批/异常/退款。
2. ORD-699 → WAITING_APPROVAL → 审核员可见关联订单 → 批准 → 完成退款。
3. 模型故障 → ManualReviewTask → 审核员认领 → RESOLVED，不触发退款。
4. 支付 UNKNOWN → ManualReviewTask/PAYMENT_UNKNOWN，节点重放不再次支付。
5. 三角色订单列表和详情按权限过滤。

### 任务 10.2：真实浏览器验收

使用浏览器自动化在独立任务空间验证当前本地服务：

1. 客户登录并走 ORD-400 多轮路径；
2. 客户打开“我的订单”，确认看不到 ORD-500-OTHER；
3. 审核员登录，确认只在审批队列/审批订单看到规则要求审批的订单；
4. 审核员在异常处理看到历史模型故障，并完成认领与备注；
5. 管理员登录，确认全部订单、异常和审计可见；
6. 在至少 1440×900 和 1280×720 两种桌面视口测量根页面无纵向滚动且 Composer 可见；
7. 在移动视口检查布局恢复自然滚动和输入可用。

浏览器验收不得修改真实外部系统；本项目订单和支付均为本地 Mock。

### 任务 10.3：文档更新

**修改文件**

- `README.md`
- `docs/agent-runtime.md`

**内容**

- 审批与异常处理的区别；
- 三种角色的订单可见范围；
- ManualReviewTask 生命周期；
- 补问 ToolMessage 协议；
- 新页面和演示路径；
- 常见异常排查与恢复方式。

**提交**

```text
test: cover role-scoped orders and exception workflows
docs: explain order visibility and exception handling
```

## 15. 最终质量门禁

### 15.1 后端

```bash
docker compose exec -T api sh -lc \
  "ruff check src tests migrations && mypy src && pytest -q && python -m pip check"
```

### 15.2 前端

```bash
docker compose exec -T web sh -lc \
  "npm run typecheck && npm run lint && npm test -- --run && npm run build"
npm --prefix frontend audit --omit=dev --registry=https://registry.npmjs.org
```

### 15.3 真实模型与运行时

```bash
docker compose run --rm migrate
docker compose up -d --force-recreate api worker scheduler web
curl -fsS http://localhost:8000/ready
docker compose exec -T -e RUN_REAL_MODEL_SMOKE=1 api \
  pytest -q tests/smoke/test_real_model_gateway.py
docker compose ps
```

### 15.4 静态安全扫描

```bash
rg -n "LLM_API_KEY|Authorization|Bearer" backend/src backend/tests
rg -n "execute_refund|RefundRequest|payment" \
  backend/src/refund_agent/api/routes/manual_reviews.py \
  backend/src/refund_agent/manual_review
```

第一条只允许配置字段名和脱敏测试命中；第二条预期无异常处理业务调用命中。

## 16. 提交顺序

建议提交序列：

1. `fix: preserve tool protocol across user input resume`
2. `test: cover multi-turn compatible model protocol`
3. `fix: reject unavailable customer orders deterministically`
4. `feat: persist technical manual review tasks`
5. `refactor: centralize replay-safe manual review creation`
6. `feat: add role-protected manual review APIs`
7. `feat: expose role-scoped order APIs`
8. `feat: add role-scoped order pages`
9. `feat: add technical exception handling workspace`
10. `fix: keep customer chat composer within desktop viewport`
11. `test: cover role-scoped orders and exception workflows`
12. `docs: explain order visibility and exception handling`

每个提交前运行其相关测试，最终全量通过后推送 `origin/main`。不得提交 `.env`、浏览器会话数据、
`.superpowers/` 视觉草稿或包含真实密钥的日志。

## 17. 完成检查表

- [ ] 多轮补问恢复包含匹配的 ToolMessage；
- [ ] 真实兼容模型两轮 smoke 通过；
- [ ] ORD-400 确定性拒绝且提示正确；
- [ ] 不存在/他人订单不创建审批、异常或退款；
- [ ] submitted_order_number 可安全展示；
- [ ] 历史和新异常进入 ManualReviewTask；
- [ ] 异常任务支持认领、备注、解决和无法解决；
- [ ] 异常路径不能批准或执行退款；
- [ ] 客户只能看到自己的订单；
- [ ] 审核员只能看到自己审批范围内的订单；
- [ ] 管理员能看到所有订单；
- [ ] 审批队列和异常队列完全分离；
- [ ] 桌面端输入框始终在视口内；
- [ ] 移动端输入可用；
- [ ] 全量静态检查、单元测试、构建和依赖检查通过；
- [ ] 三角色浏览器验收通过；
- [ ] 文档更新并推送 GitHub。
