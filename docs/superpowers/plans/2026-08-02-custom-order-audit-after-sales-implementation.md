# 自定义订单、模型审计与客户售后入口实施计划

## 1. 目标与交付顺序

按已批准设计完成四项交付：自定义订单金额、模型调用审计、客户订单售后入口、唯一订单状态。
全部代码和验收完成并推送后，重置本地 PostgreSQL 与 Redis，只恢复初始演示数据。

实施顺序遵循“后端契约 → 前端消费 → 全链路验证 → 数据重置”，避免前端先依赖不存在的字段。

## 2. 阶段一：自定义金额

### 修改

- `backend/src/refund_agent/api/schemas.py`
- `backend/src/refund_agent/api/routes/demo.py`
- `backend/src/refund_agent/demo_orders/service.py`
- `backend/tests/test_demo_order_service.py`
- `backend/tests/test_api_demo_orders.py`
- `backend/tests/test_demo_order_e2e.py`

### 实现

1. `DemoOrderCreateRequest` 增加 Decimal 金额，范围 0.01–999999.99，最多两位小数；
2. `ScenarioSpec` 只保留 fraud 和 payment 特征；
3. `create_demo_order` 显式接收 amount，幂等命中返回首次订单；
4. 创建审计增加规范化金额字符串；
5. 保留 `AMOUNT_APPROVAL` 的兼容处理，但前端不再提供该选项。

### 测试

- 合法边界与非法金额；
- 三种特征映射；
- request ID 重放不覆盖金额；
- ¥399 自动退款、¥699 金额审批、¥699 风控双原因、支付未知路径。

## 3. 阶段二：订单唯一生命周期状态

### 修改

- `backend/src/refund_agent/api/schemas.py`
- `backend/src/refund_agent/api/routes/orders.py`
- `backend/tests/test_api_orders.py`

### 实现

1. `OrderView` 增加 `lifecycle_status`；
2. 订单视图构建时读取最新 Ticket、RefundRequest、ApprovalTask 和 ManualReviewTask；
3. 按设计优先级集中计算状态；
4. 客户仍看不到内部审批、风险和异常字段；
5. `ticket_id` 指向最新关联工单，供“查看售后”跳转。

### 测试

- 已签收、处理中、等待审批、人工处理、已退款、拒绝、失败；
- 多工单时只使用最新工单；
- 客户权限和管理员摘要不回归。

## 4. 阶段三：模型输入输出审计

### 修改

- `backend/src/refund_agent/adapters/llm.py`
- 可新增 `backend/src/refund_agent/audit/serialization.py`
- `backend/src/refund_agent/api/routes/audit.py`
- `backend/tests/test_agent_graph.py` 或新增模型审计测试
- `backend/tests/test_api_audit.py`

### 实现

1. 新增 JSON 安全的 LangChain Message 序列化器；
2. 对任意嵌套结构递归脱敏；
3. requested 保存消息输入和工具名称；
4. completed 保存完整响应、Tool Calls、用量和耗时；
5. failed 保存受控错误摘要；
6. 序列化异常降级但不阻断模型调用；
7. 审计 API 支持 `category=model|business`。

### 测试

- System/Human/AI/Tool 顺序与结构；
- 输出文本和 Tool Calls；
- 嵌套 key/token/password/cookie 脱敏；
- 不可序列化对象降级；
- 分类查询和管理员权限。

## 5. 阶段四：前端功能

### 修改

- `frontend/src/components/DemoOrderForm.tsx`
- `frontend/src/pages/OrdersPage.tsx`
- `frontend/src/pages/CustomerChatPage.tsx`
- `frontend/src/pages/AuditPage.tsx`
- `frontend/src/components/StatusPill.tsx`
- `frontend/src/types.ts`
- `frontend/src/styles.css`
- 相关 Vitest 测试

### 实现

1. 建单表单增加金额，场景卡改为正常、风控、支付异常；
2. 订单页只渲染 `lifecycle_status`；
3. 客户订单行增加“申请售后/查看售后”；
4. 聊天页读取 order_number 预填消息，读取 ticket_id 选中工单；
5. 审计页增加全部、模型调用、业务事件分类；
6. 模型事件用输入、输出、Tool Calls、用量和耗时专用布局展示。

### 测试

- 金额请求体和错误保留；
- 三个特征选项；
- 单一状态标签；
- 售后导航参数与聊天预填/选中；
- 模型审计分类与结构化内容。

## 6. 阶段五：质量门禁与真实验收

### 后端

```bash
docker compose run --rm migrate
docker compose exec -T api sh -lc \
  "ruff check src tests migrations && mypy src && pytest -q && python -m pip check"
```

### 前端

```bash
docker compose exec -T web sh -lc \
  "npm run typecheck && npm run lint && npm test -- --run && npm run build"
npm --prefix frontend audit --omit=dev --registry=https://registry.npmjs.org
```

### 真实流程

1. 运行真实模型网关 smoke；
2. 使用隔离浏览器验证 ¥399 自动退款和 ¥699 金额审批；
3. 验证客户订单发起/查看售后与唯一状态；
4. 验证模型审计输入、输出与 Tool Calls；
5. 验证 ¥699 风控双原因和支付未知异常；
6. 检查 1280×720 与 390px 宽布局。

## 7. 阶段六：提交、推送与最终数据重置

建议提交：

1. `feat: support custom demo order amounts and lifecycle status`
2. `feat: retain structured model audit input and output`
3. `feat: add order-based customer after-sales entry`
4. `docs: update custom demo flow and audit guidance`

推送 `main` 后执行：

```bash
docker compose down -v
docker compose up -d
```

只读验证初始账号 4、固定订单 5，其余业务表和 checkpoint 业务线程均为 0。最终只做健康检查，
不再运行会写入数据的 smoke 或浏览器流程，并保持服务运行。
