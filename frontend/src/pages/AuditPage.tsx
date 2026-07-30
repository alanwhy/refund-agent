import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import type { AuditEvent } from "../types";

export function AuditPage() {
  const { token } = useAuth();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [ticketId, setTicketId] = useState("");
  const [action, setAction] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    const params = new URLSearchParams();
    if (ticketId) params.set("ticket_id", ticketId);
    if (action) params.set("action", action);
    const query = params.toString() ? "?" + params.toString() : "";
    setEvents(await api<AuditEvent[]>("/audit-events" + query, {}, token));
  }, [token, ticketId, action]);

  useEffect(() => {
    void load().catch((reason) =>
      setError(reason instanceof Error ? reason.message : "审计记录加载失败")
    );
  }, [load]);

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

      {error && <p className="error-banner">{error}</p>}
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
    </div>
  );
}
