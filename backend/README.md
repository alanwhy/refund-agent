# Refund Agent backend

服务端由 FastAPI、Celery、LangGraph、PostgreSQL 和 Redis 组成。业务表由 Alembic 管理，
LangGraph checkpoint 由 `PostgresSaver` 单独管理。

## 运行职责

- `migrate`：执行 Alembic、初始化 LangGraph checkpoint 表并幂等写入演示数据；
- `api`：鉴权、工单查询、消息提交和审批接口；
- `worker`：运行或恢复 Refund Agent；
- `scheduler`：升级超时审批；
- PostgreSQL：业务事实与 Graph checkpoint；
- Redis：Celery broker 和同工单互斥锁。

生产运行路径必须配置 `LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL`。自动化测试通过依赖
注入使用 `tests/support/ScriptedModel`，不会请求外部模型。

## 本地检查

```bash
docker compose up -d postgres redis
docker compose run --rm migrate
docker compose run --rm --no-deps api sh -lc \
  "ruff check src tests migrations && mypy src && pytest -q"
```

显式验证真实模型网关：

```bash
make smoke-model
```

完整运行机制见 [`../docs/agent-runtime.md`](../docs/agent-runtime.md)。
