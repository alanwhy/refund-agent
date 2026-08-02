# 管理员演示订单工厂实施计划

> 对应设计：`docs/superpowers/specs/2026-08-02-admin-demo-order-factory-design.md`

## 1. 目标

补齐本地演示的完整起点：管理员为现有客户创建受控测试订单，客户使用订单号发起退款，随后
沿既有 Agent、审批和技术异常流程完成验证。

完成后必须满足：

- 只有管理员能读取演示客户列表和创建测试订单；
- 四个预设场景由服务端映射为确定性订单字段；
- 创建订单不产生工单、审批、异常或退款；
- 相同 request ID 重试不会重复创建订单；
- 客户登录入口允许填写已有客户邮箱；
- 管理员可在“全部订单”页完成创建并看到明确订单号；
- 四种订单能分别走通自动退款、金额审批、风控审批和支付未知流程；
- 数据迁移、静态检查、自动化测试、真实模型 smoke 和浏览器验收全部通过。

## 2. 执行原则

1. 每项服务端行为先写失败测试，再实现。
2. 场景只存在于演示订单创建记录，Agent 不读取 `scenario`。
3. 前端不能提交金额、风控标记、支付行为或签收时间。
4. 订单和幂等记录必须在同一个数据库事务内提交。
5. 列表与创建权限都由后端强制执行，不能依赖前端隐藏按钮。
6. 不修改或提交 `.env`，不输出真实网关密钥。
7. 不增加订单删除、客户创建或身份模拟功能。
8. 实施完成后推送当前 `main` 分支。

## 3. 目标文件

```text
backend/
  migrations/versions/
    0005_demo_order_creations.py
  src/refund_agent/
    api/routes/demo.py
    api/schemas.py
    api/app.py
    demo_orders/
      __init__.py
      service.py
    domain/enums.py
    models.py
  tests/
    test_api_demo_orders.py
    test_demo_order_service.py
    test_demo_order_e2e.py
    test_migrations.py

frontend/src/
  components/
    DemoOrderForm.tsx
  pages/
    OrdersPage.tsx
    LoginPage.tsx
  test/
    OrdersPage.test.tsx
    LoginPage.test.tsx
  styles.css
  types.ts

README.md
docs/agent-runtime.md
```

`DemoOrderForm.tsx` 独立负责表单状态与提交，`OrdersPage.tsx` 负责角色判断、订单列表和创建成功
后的列表合并；不进行无关页面重构。

## 4. 阶段一：场景模型与迁移

### 任务 1.1：增加场景枚举和幂等记录模型

**修改文件**

- `backend/src/refund_agent/domain/enums.py`
- `backend/src/refund_agent/models.py`
- 新增 `backend/migrations/versions/0005_demo_order_creations.py`
- `backend/tests/test_migrations.py`

**数据定义**

`DemoOrderScenario`：

- `AUTO_REFUND`
- `AMOUNT_APPROVAL`
- `RISK_APPROVAL`
- `PAYMENT_UNKNOWN`

`DemoOrderCreation`：

- `id: String(36)` 主键；
- `request_id: String(100)` 全局唯一；
- `order_id: ForeignKey(orders.id)` 唯一；
- `created_by: ForeignKey(users.id)`；
- `scenario: String(32)`；
- `created_at: DateTime(timezone=True)`。

为 `request_id`、`order_id`、`created_by` 和 `created_at` 建立适用索引。迁移只建表，不回填
固定 seed 订单，因为固定订单不是通过新接口创建的演示资源。

**先写测试**

1. 0005 upgrade 创建表、唯一约束与外键；
2. 0005 downgrade 按依赖顺序删除；
3. 重复 request ID 和重复 order ID 被数据库拒绝；
4. created_by 必须指向有效用户。

**验证**

```bash
docker compose run --rm migrate
docker compose exec -T postgres psql -U refund -d refund -c '\d demo_order_creations'
```

**提交**

```text
feat: persist idempotent demo order creation
```

## 5. 阶段二：演示订单领域服务

### 任务 2.1：集中定义场景映射

**新增/修改文件**

- 新增 `backend/src/refund_agent/demo_orders/__init__.py`
- 新增 `backend/src/refund_agent/demo_orders/service.py`
- 新增 `backend/tests/test_demo_order_service.py`

**服务接口**

实现以下单一入口：

```python
create_demo_order(
    db,
    *,
    customer: User,
    product_name: str,
    scenario: DemoOrderScenario,
    request_id: str,
    created_by: User,
) -> tuple[Order, bool]
```

第二个返回值表示是否为幂等重放。

场景映射集中在只读常量中：

| 场景 | amount | fraud_flag | payment_behavior |
| --- | ---: | --- | --- |
| AUTO_REFUND | 399.00 | false | success |
| AMOUNT_APPROVAL | 699.00 | false | success |
| RISK_APPROVAL | 199.00 | true | success |
| PAYMENT_UNKNOWN | 299.00 | false | unknown |

所有订单状态为 `DELIVERED`，`delivered_at` 为当前 UTC 时间前两天，`product_tags` 为空数组。

**订单号生成**

- 格式：`ORD-DEMO-YYYYMMDD-XXXXXX`；
- 后缀从大写字母和数字生成；
- 最多尝试 3 次；
- 每次创建前查询冲突，数据库唯一约束仍为最终防线；
- 3 次失败抛出受控领域异常，由 API 转换为 503。

**先写测试**

1. 四个场景字段严格匹配映射；
2. 签收时间在创建时间前约两天；
3. 订单号匹配 Agent Schema `^ORD-[A-Z0-9-]+$`；
4. 同 request ID 返回同一个订单并标记 replayed；
5. 幂等重放不修改第一次创建的商品、客户或场景；
6. 模拟两次冲突后第三次成功；
7. 连续三次冲突后返回受控异常；
8. 一次创建只写一条 `demo_order.created` 审计；
9. 审计不包含密码、令牌或底层请求体；
10. 创建后 Ticket、ApprovalTask、ManualReviewTask 和 RefundRequest 数量不变。

**实现注意**

- 服务层只接受已验证的 CUSTOMER 用户和 ADMIN 创建人；
- product_name 在 API Schema 规范化后传入；
- 幂等命中必须先返回既有订单，不重新校验本次 payload 是否与首次一致；
- 若需要标识 payload 冲突，只在审计中记录受控原因，不覆盖既有资源。

**提交**

```text
feat: add deterministic demo order scenarios
```

## 6. 阶段三：管理员 API

### 任务 3.1：增加演示客户列表

**新增/修改文件**

- 新增 `backend/src/refund_agent/api/routes/demo.py`
- `backend/src/refund_agent/api/schemas.py`
- `backend/src/refund_agent/api/app.py`
- 新增 `backend/tests/test_api_demo_orders.py`

**接口**

```http
GET /api/demo/customers
```

响应项仅包含：

- `id`
- `display_name`
- `email`

按 `display_name`、`email` 稳定排序，只查询 `role=CUSTOMER AND active=true`。

**先写测试**

1. 管理员收到所有有效客户；
2. 响应不含 password_hash、active 或订单信息；
3. 客户和审核员返回 403；
4. 未登录返回 401；
5. 停用客户不返回。

### 任务 3.2：增加创建接口

**接口**

```http
POST /api/demo/orders
```

请求 Schema：

- `customer_id: str`
- `product_name: str`，去除首尾空格后 2–100 字符；
- `scenario: DemoOrderScenario`
- `request_id: str`，8–100 字符。

Pydantic 设置 `extra="forbid"`，拒绝金额、风控等额外字段。

响应：

```json
{
  "order": { "...": "管理员 OrderView" },
  "replayed": false
}
```

首次创建返回 201；重放返回 200。因为 FastAPI 装饰器不能静态表达两种状态，handler 接收
`Response` 并在 replay 时设置 `status_code=200`。

管理员 `OrderView` 增加 `customer_email`，用于创建成功提示和账号切换指引。客户与审核员订单
响应中该字段保持 null，既有角色范围不变。

**先写测试**

1. 管理员创建四种场景成功；
2. 返回订单包含客户姓名和邮箱提示所需字段；
3. 客户和审核员返回 403；
4. customer_id 指向管理员、审核员、停用或不存在用户时返回 422；
5. 无效场景、空白商品、过长商品和短 request ID 返回 422；
6. 提交 amount、fraud_flag 或 payment_behavior 返回 422；
7. 相同 request ID 首次 201、重放 200，order ID 相同；
8. 创建后客户订单列表立即可见；
9. 创建后审核员订单列表不可见；
10. 管理员订单列表显示新订单与客户摘要。

**验证**

```bash
docker compose exec -T api pytest -q \
  tests/test_demo_order_service.py tests/test_api_demo_orders.py
```

**提交**

```text
feat: expose administrator demo order APIs
```

## 7. 阶段四：客户邮箱登录

### 任务 4.1：允许客户入口填写邮箱

**修改文件**

- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/styles.css`
- 新增 `frontend/src/test/LoginPage.test.tsx`

**行为**

1. 选择客户入口时，在入口卡片与主按钮之间显示“客户邮箱”输入框；
2. 默认值为 `customer@example.com`；
3. 切换到审批或管理入口时隐藏输入框，使用既有固定邮箱；
4. 切回客户入口时保留用户此前填写的客户邮箱；
5. 登录仍使用演示密码 `Demo123!`；
6. 空白或明显无效邮箱时禁用登录并给出前端提示；
7. 服务端 401 继续显示既有错误，不暴露账号是否存在。

**先写测试**

1. 客户入口显示默认邮箱；
2. 可填写 `other@example.com` 并用该邮箱调用 login；
3. 审核/管理入口隐藏输入并使用固定邮箱；
4. 来回切换保留客户邮箱；
5. 无效邮箱不会调用 API。

**验证**

```bash
docker compose exec -T web npm test -- --run src/test/LoginPage.test.tsx
```

**提交**

```text
feat: allow selecting existing customer login
```

## 8. 阶段五：管理员创建订单表单

本阶段使用既有“归舟”订单账簿视觉语言。创建入口作为账簿的受控附加动作，不改造成通用后台
CRUD 页面。

### 任务 5.1：扩展前端类型与数据加载

**修改文件**

- `frontend/src/types.ts`
- `frontend/src/pages/OrdersPage.tsx`
- `frontend/src/test/OrdersPage.test.tsx`

**新增类型**

- `DemoCustomer`
- `DemoOrderScenario`
- `DemoOrderCreateRequest`
- `DemoOrderCreateResponse`

管理员首次打开“新建测试订单”面板时加载 `/demo/customers`，本次页面生命周期内复用结果；客户
和审核员不得发出此请求。

**先写测试**

1. ADMIN 请求客户列表；
2. CUSTOMER/APPROVER 不请求客户列表；
3. 客户列表失败不影响既有订单列表展示，只禁用创建入口并显示局部错误。

### 任务 5.2：实现创建面板

**修改文件**

- `frontend/src/pages/OrdersPage.tsx`
- 新增 `frontend/src/components/DemoOrderForm.tsx`
- `frontend/src/styles.css`
- `frontend/src/test/OrdersPage.test.tsx`

**页面结构**

- 页头数量旁显示“新建测试订单”；
- 展开后在页头下方显示表单面板，不遮挡订单列表；
- 客户下拉项为“姓名 · 邮箱”；
- 商品名称输入默认空；
- 四个场景使用单选卡片；
- 卡片显示金额、触发条件和预期结果；
- 操作为“取消”和“创建订单”。

**前端状态**

- 打开表单时生成 request ID；
- 网络失败或 5xx 后重试沿用 request ID；
- 成功或取消时清除 request ID；
- 成功响应中的 order 立即合并到列表，再请求 `/orders` 校准；
- 刷新失败时保留成功提示和本地新订单行；
- 新订单 ID 在状态中保留，用 CSS 强调其行；用户再次创建或离开页面时取消强调。

**先写测试**

1. 只有管理员看到按钮；
2. 表单客户选项正确；
3. 四个场景文案正确；
4. 请求体仅包含四个允许字段；
5. 创建成功显示订单号、客户邮箱并刷新列表；
6. 创建失败保留选择和 request ID；
7. 取消后再次打开使用新 request ID；
8. 提交期间按钮禁用；
9. 列表刷新失败时仍保留已创建订单；
10. 客户和审核员原页面快照行为不变。

**可访问性与响应式**

- 所有字段使用可见 label；
- 场景卡片使用真实 radio 控件；
- 成功和错误提示分别使用 `role=status` 与 `role=alert`；
- 键盘可完成完整创建；
- 760px 以下表单字段与场景卡片单列排列。

**验证**

```bash
docker compose exec -T web sh -lc \
  "npm run typecheck && npm run lint && npm test -- --run && npm run build"
```

**提交**

```text
feat: add administrator demo order form
```

## 9. 阶段六：四场景全链路测试

### 任务 6.1：服务端集成测试

**新增/修改文件**

- 新增 `backend/tests/test_demo_order_e2e.py`
- 修改 `backend/tests/test_agent_graph.py` 中的 `create_ticket` 辅助方法，允许显式传入 customer ID，
  默认行为保持现有演示客户不变

测试使用 `ScriptedModel`，不调用真实网关。对每个新创建订单模拟模型提交
`SubmitRefundContext`：

1. `AUTO_REFUND`：Ticket 到 `COMPLETED`，一条 SUCCEEDED RefundRequest，无审批/异常；
2. `AMOUNT_APPROVAL`：Ticket 到 `WAITING_APPROVAL`，审批原因为金额上限；批准并恢复后完成退款；
3. `RISK_APPROVAL`：Ticket 到 `WAITING_APPROVAL`，审批原因为风险信号；批准并恢复后完成退款；
4. `PAYMENT_UNKNOWN`：Ticket 到 `MANUAL_REVIEW`，生成 PAYMENT_UNKNOWN 异常；节点重放不再次支付；
5. 四条路径的订单归属都来自新订单 customer_id；
6. 其他客户提交新订单号时确定性拒绝，不泄露归属。

**验证**

```bash
docker compose exec -T api pytest -q tests/test_demo_order_e2e.py
```

**提交**

```text
test: cover generated demo order refund paths
```

## 10. 阶段七：文档与真实浏览器验收

### 任务 7.1：更新运行说明

**修改文件**

- `README.md`
- `docs/agent-runtime.md`

说明：

- 管理员创建测试订单的步骤；
- 四种场景与预期结果；
- 如何使用客户邮箱切换账号；
- 订单创建与退款工单的边界；
- request ID 幂等语义；
- 测试订单的清理方式仍为 `docker compose down -v`。

### 任务 7.2：浏览器验收

必须使用 `ego-browser` 独立任务空间，在当前本地服务验证：

1. 管理员打开全部订单并创建 `AUTO_REFUND` 订单；
2. 成功提示包含订单号与客户邮箱，列表突出新订单；
3. 管理员退出，客户入口填写该邮箱登录；
4. 客户“我的订单”能看到新订单；
5. 客户在售后对话申请退款并到达 COMPLETED；
6. 重复上述步骤验证 AMOUNT_APPROVAL，审核员审批后完成；
7. 验证 RISK_APPROVAL 出现正确风险原因；
8. 验证 PAYMENT_UNKNOWN 进入异常处理且无审批动作；
9. 客户/审核员直接调用创建 API 返回 403；
10. 1280×720 和移动视口下表单可用，无遮挡或水平溢出。

浏览器验收只操作本地 Mock 数据，不访问真实外部系统。

**提交**

```text
docs: explain demo order full-flow validation
```

## 11. 最终质量门禁

### 11.1 后端

```bash
docker compose run --rm migrate
docker compose exec -T api sh -lc \
  "ruff check src tests migrations && mypy src && pytest -q && python -m pip check"
```

### 11.2 前端

```bash
docker compose exec -T web sh -lc \
  "npm run typecheck && npm run lint && npm test -- --run && npm run build"
npm --prefix frontend audit --omit=dev --registry=https://registry.npmjs.org
```

### 11.3 真实模型与服务

```bash
docker compose up -d --force-recreate api worker scheduler web
curl -fsS http://localhost:8000/ready
docker compose exec -T -e RUN_REAL_MODEL_SMOKE=1 api \
  pytest -q tests/smoke/test_real_model_gateway.py
docker compose ps
```

### 11.4 静态安全检查

```bash
rg -n "password_hash|LLM_API_KEY|Authorization|Bearer" \
  backend/src/refund_agent/api/routes/demo.py backend/src/refund_agent/demo_orders backend/tests
rg -n "amount|fraud_flag|payment_behavior|delivered_at" frontend/src/pages/OrdersPage.tsx \
  frontend/src/components/DemoOrderForm.tsx 2>/dev/null || true
```

第一项只允许安全测试和配置名称；第二项允许场景说明的展示文字与响应类型读取，但创建请求体
测试必须证明没有底层字段。

## 12. 提交顺序

1. `feat: persist idempotent demo order creation`
2. `feat: add deterministic demo order scenarios`
3. `feat: expose administrator demo order APIs`
4. `feat: allow selecting existing customer login`
5. `feat: add administrator demo order form`
6. `test: cover generated demo order refund paths`
7. `docs: explain demo order full-flow validation`

最终通过质量门禁与浏览器验收后推送 `origin/main`。不得提交 `.env`、真实密钥、浏览器会话或
测试截图临时文件。

## 13. 完成检查表

- [ ] 0005 迁移可升级和回滚；
- [ ] 管理员能读取有效客户列表；
- [ ] 非管理员不能读取客户列表或创建订单；
- [ ] 四个场景字段由服务端固定映射；
- [ ] 订单号符合 Agent Schema 且保持唯一；
- [ ] request ID 重放不重复创建订单；
- [ ] 创建动作不产生任何售后副作用；
- [ ] 客户入口可输入已有客户邮箱；
- [ ] 管理员表单支持客户、商品和场景选择；
- [ ] 成功提示给出订单号与客户邮箱；
- [ ] 四条退款路径全部通过；
- [ ] 他人订单安全拒绝仍通过；
- [ ] 全量后端、前端、真实模型和依赖检查通过；
- [ ] 桌面和移动浏览器验收通过；
- [ ] 文档更新、提交并推送 GitHub。
