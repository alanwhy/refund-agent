# 归舟 · 智能退换货 Agent

一个可本地运行、可审计、支持人工审批暂停与恢复的退货退款 Agent MVP。

系统使用 FastAPI、LangGraph、Celery、PostgreSQL、Redis 和 React。订单、物流与支付接口为可控 Mock；默认使用确定性 Fake LLM，因此无需 API Key 即可完成演示。

> 这是架构与流程演示项目，不得直接接入真实资金系统。

## 核心能力

- 低风险退款自动处理；
- 金额大于 500 元或命中欺诈规则时暂停并等待人工审批；
- 审批通过后从持久化检查点恢复；
- 支付结果未知时冻结自动重试并转人工；
- JWT 三角色权限：客户、审批员、管理员；
- 客户对话、审批工作台和审计记录三个页面；
- 订单归属、退款上限、幂等与审批并发均由确定性代码校验；
- OpenAI 兼容模型接口可配置，测试与默认演示无需联网。

## 架构

~~~mermaid
flowchart LR
    WEB["React Web"] --> API["FastAPI"]
    API --> PG["PostgreSQL"]
    API --> REDIS["Redis"]
    REDIS --> WORKER["Celery Worker"]
    WORKER --> GRAPH["LangGraph"]
    GRAPH --> RULES["政策与风险规则"]
    GRAPH --> MOCKS["订单 / 支付 / 知识库适配器"]
    GRAPH --> PG
~~~

Agent 负责理解和组织流程，规则引擎负责最终业务判断。模型不能直接调用支付接口。

## 快速启动

要求：

- Docker Desktop；
- Docker Compose。

启动全部服务：

~~~bash
docker compose up --build
~~~

打开：

- Web：[http://localhost:5173](http://localhost:5173)
- API 文档：[http://localhost:8000/docs](http://localhost:8000/docs)
- 健康检查：[http://localhost:8000/ready](http://localhost:8000/ready)

首次启动会自动创建数据库表和演示数据。停止服务：

~~~bash
docker compose down
~~~

清空演示数据并重新开始：

~~~bash
docker compose down -v
docker compose up --build
~~~

## 演示账号

所有账号的密码都是 **Demo123!**。

| 角色 | 邮箱 | 页面 |
| --- | --- | --- |
| 客户 | customer@example.com | 发起退款、查看处理轨迹 |
| 审批员 | approver@example.com | 处理高风险退款 |
| 管理员 | admin@example.com | 查看审批和审计事件 |

密码仅用于本地演示，数据库中保存的是 Argon2 哈希。

## 演示订单

| 订单号 | 金额 | 预期行为 |
| --- | ---: | --- |
| ORD-399 | ¥399 | 自动退款 |
| ORD-699 | ¥699 | 暂停并等待审批，批准后恢复 |
| ORD-199-FRAUD | ¥199 | 命中欺诈信号，等待审批 |
| ORD-299-UNKNOWN | ¥299 | 支付结果未知，转人工且不重复退款 |
| ORD-500-OTHER | ¥500 | 属于其他客户，拒绝访问 |

在客户页面输入：

~~~text
我想退货，订单号 ORD-399
~~~

## 配置真实兼容模型

默认配置为 LLM_MODE=fake。如需使用 OpenAI 或兼容服务，复制示例环境变量：

~~~bash
cp .env.example .env
~~~

设置：

~~~dotenv
LLM_MODE=compatible
OPENAI_BASE_URL=https://your-compatible-endpoint/v1
OPENAI_API_KEY=your-key
OPENAI_MODEL=your-model
~~~

然后重新启动 Compose。API Key 不应提交到 Git。

## 业务规则

规则文件位于：

- config/rules/refund_policy.yaml
- config/rules/risk_rules.yaml

工作流记录每次实际使用的规则内容摘要。默认规则：

- 金额不大于 ¥500 且没有其他风险信号：自动退款；
- 金额大于 ¥500、欺诈标记、数据冲突或低置信度：人工审批；
- 审批金额不得高于服务端核算的可退金额；
- 审批超时进入管理员升级队列，不自动放款。

## 测试与质量检查

启动 PostgreSQL 和 Redis：

~~~bash
docker compose up -d postgres redis
~~~

运行后端：

~~~bash
docker compose run --rm api sh -lc "ruff check src tests && mypy src && pytest -q"
~~~

运行前端：

~~~bash
cd frontend
npm install
npm run typecheck
npm run lint
npm test -- --run
npm run build
~~~

当前自动化测试覆盖：

- 500 元审批边界；
- 敏感信息脱敏；
- 自动退款幂等；
- 高金额审批暂停与恢复；
- 未知支付结果不自动重试；
- 登录与管理员接口越权。

## 目录

~~~text
backend/
  src/refund_agent/
    adapters/       外部系统与模型适配器
    api/            FastAPI 路由与 Schema
    audit/          只追加审计与脱敏
    domain/         状态与角色枚举
    rules/          确定性政策和风险规则
    workflows/      LangGraph 工作流
    worker/         Celery 任务和审批升级
  prompts/          独立管理的提示词
  tests/            后端测试
frontend/
  src/              React 页面、组件和样式
config/rules/       可配置业务规则
docs/superpowers/   设计规格与实施计划
~~~

## 安全边界

- 用户文本始终视为不可信数据；
- 模型输出必须转换为结构化类型；
- 支付前重新校验订单归属、退款上限、审批状态和幂等键；
- 客户只能读取自己的工单；
- 审批员只能处理未分配或分配给自己的任务；
- 只有管理员可以读取全链路审计；
- 密码、Token 和 API Key 在审计写入前脱敏。

完整设计见 [设计规格](docs/superpowers/specs/2026-07-30-refund-agent-design.md)，实施分解见 [实施计划](docs/superpowers/plans/2026-07-30-refund-agent-implementation.md)。
