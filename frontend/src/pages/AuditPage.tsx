import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import type { AuditEvent } from "../types";

export function AuditPage() {
  const { token } = useAuth();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [ticketId, setTicketId] = useState("");
  const [action, setAction] = useState("");
  const [category, setCategory] = useState<"" | "model" | "business">("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    const params = new URLSearchParams();
    if (ticketId) params.set("ticket_id", ticketId);
    if (action) params.set("action", action);
    if (category) params.set("category", category);
    const query = params.toString() ? "?" + params.toString() : "";
    setEvents(await api<AuditEvent[]>("/audit-events" + query, {}, token));
  }, [token, ticketId, action, category]);

  useEffect(() => {
    void load().catch((reason) =>
      setError(reason instanceof Error ? reason.message : "审计记录加载失败")
    );
  }, [load]);

  const modelCalls = useMemo(() => {
    const calls = new Map<
      string,
      { key: string; requested?: AuditEvent; result?: AuditEvent }
    >();
    for (const event of events) {
      const step = String(event.details.logical_step ?? "—");
      const key = [event.ticket_id, event.run_id, event.node_name, step].join(":");
      const call = calls.get(key) ?? { key };
      if (event.action === "model.requested") call.requested = event;
      if (event.action === "model.completed" || event.action === "model.failed") {
        call.result = event;
      }
      calls.set(key, call);
    }
    return [...calls.values()];
  }, [events]);

  return (
    <div className="audit-page">
      <header className="page-title">
        <div>
          <p className="eyebrow">IMMUTABLE TRAIL</p>
          <h1>审计记录</h1>
          <p className="muted">还原每一步规则判断、审批决定与工具执行结果。</p>
        </div>
        <div className="audit-summary">
          <strong>{events.length}</strong>
          <span>条当前记录</span>
        </div>
      </header>

      <section className="filter-bar" aria-label="审计筛选">
        <label>
          工单 ID
          <input value={ticketId} onChange={(event) => setTicketId(event.target.value)} placeholder="输入完整工单 ID" />
        </label>
        <label>
          事件类型
          <select value={action} onChange={(event) => setAction(event.target.value)}>
            <option value="">全部事件</option>
            <option value="ticket.created">工单创建</option>
            <option value="risk.evaluated">风险判断</option>
            <option value="approval.requested">请求审批</option>
            <option value="refund.executed">退款执行</option>
          </select>
        </label>
        <button className="secondary-button" onClick={() => void load()}>
          刷新记录
        </button>
      </section>

      <nav className="audit-categories" aria-label="审计记录分类">
        {[
          ["", "全部记录"],
          ["model", "模型调用"],
          ["business", "业务事件"],
        ].map(([value, label]) => (
          <button
            key={value || "all"}
            className={category === value ? "selected" : ""}
            onClick={() => setCategory(value as "" | "model" | "business")}
            aria-pressed={category === value}
          >
            {label}
          </button>
        ))}
      </nav>

      {error && <p className="error-banner">{error}</p>}
      {category === "model" ? (
        <section className="model-call-ledger" aria-label="模型调用记录">
          {modelCalls.length === 0 && (
            <div className="empty-state">
              <strong>没有匹配的模型调用</strong>
              <span>调整工单筛选，或先运行一笔 Agent 工单。</span>
            </div>
          )}
          {modelCalls.map((call) => {
            const requested = call.requested;
            const result = call.result;
            const input = requested?.details.input as Record<string, unknown> | undefined;
            const output = result?.details.output;
            const toolCalls =
              output && typeof output === "object" && "tool_calls" in output
                ? (output as Record<string, unknown>).tool_calls
                : undefined;
            const usage = result?.details.usage;
            return (
              <article className="model-call" key={call.key}>
                <header>
                  <div>
                    <span>MODEL CALL</span>
                    <strong>{String(requested?.details.model ?? result?.details.model ?? "—")}</strong>
                  </div>
                  <dl>
                    <div><dt>节点</dt><dd>{requested?.node_name ?? result?.node_name ?? "—"}</dd></div>
                    <div><dt>轮次</dt><dd>{String(requested?.details.logical_step ?? result?.details.logical_step ?? "—")}</dd></div>
                    <div><dt>耗时</dt><dd>{result?.details.duration_ms ? `${String(result.details.duration_ms)} ms` : "—"}</dd></div>
                  </dl>
                </header>
                <div className="model-call__exchange">
                  <section>
                    <h2><i>IN</i> 模型输入</h2>
                    <pre>{JSON.stringify(input ?? { message: "旧记录未保存输入" }, null, 2)}</pre>
                  </section>
                  <section>
                    <h2><i>OUT</i> 模型输出</h2>
                    <pre>{JSON.stringify(output ?? { error: result?.details.error ?? "等待或无输出" }, null, 2)}</pre>
                  </section>
                </div>
                <section className="model-call__tools">
                  <h2><i>TOOL</i> Tool Calls</h2>
                  <pre>{JSON.stringify(toolCalls ?? [], null, 2)}</pre>
                </section>
                <footer>
                  <span>Token：{usage ? JSON.stringify(usage) : "—"}</span>
                  <code>{(requested?.trace_id ?? result?.trace_id ?? "").slice(0, 12)}</code>
                </footer>
              </article>
            );
          })}
        </section>
      ) : (
      <section className="audit-ledger">
        <div className="ledger-head">
          <span>时间 / 事件</span>
          <span>对象</span>
          <span>证据摘要</span>
          <span>追踪号</span>
        </div>
        {events.length === 0 && (
          <div className="empty-state">
            <strong>没有匹配的审计记录</strong>
            <span>调整筛选条件，或先完成一笔退款演示。</span>
          </div>
        )}
        {events.map((event) => (
          <article className="ledger-row" key={event.id}>
            <div>
              <time>{new Date(event.created_at).toLocaleString("zh-CN")}</time>
              <strong>{event.action}</strong>
            </div>
            <div>
              <span>{event.entity_type}</span>
              <small>{event.entity_id?.slice(0, 12) ?? "—"}</small>
            </div>
            <pre>{JSON.stringify(event.details, null, 2)}</pre>
            <code>{event.trace_id.slice(0, 12)}</code>
          </article>
        ))}
      </section>
      )}
    </div>
  );
}
