import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { StatusPill } from "../components/StatusPill";
import type { Ticket } from "../types";

const terminalStates = new Set(["COMPLETED", "REJECTED", "FAILED", "MANUAL_REVIEW"]);
const steps = [
  ["created", "申请已受理"],
  ["order_validation", "订单已核验"],
  ["policy_check", "政策已校验"],
  ["risk_check", "风险已评估"],
  ["refund_execution", "退款执行"],
  ["completed", "处理完成"]
] as const;

export function CustomerChatPage() {
  const { token } = useAuth();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [active, setActive] = useState<Ticket | null>(null);
  const [message, setMessage] = useState("我想退货，订单号 ORD-399");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(
    async (preferredId?: string) => {
      if (!token) return;
      const list = await api<Ticket[]>("/tickets", {}, token);
      setTickets(list);
      const targetId = preferredId ?? active?.id ?? list[0]?.id;
      if (targetId) {
        const detail = await api<Ticket>("/tickets/" + targetId, {}, token);
        setActive(detail);
      }
    },
    [token, active?.id]
  );

  useEffect(() => {
    void refresh().catch((reason) =>
      setError(reason instanceof Error ? reason.message : "工单加载失败")
    );
  }, [refresh]);

  useEffect(() => {
    if (!active || terminalStates.has(active.status) || active.status === "WAITING_APPROVAL") return;
    const timer = window.setInterval(() => void refresh(active.id), 1800);
    return () => window.clearInterval(timer);
  }, [active, refresh]);

  async function send() {
    if (!token || !message.trim()) return;
    setSending(true);
    setError("");
    try {
      const accepted = await api<{ ticket_id: string }>("/chat/messages", {
        method: "POST",
        body: JSON.stringify({ content: message })
      }, token);
      setMessage("");
      await refresh(accepted.ticket_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "申请未发送");
    } finally {
      setSending(false);
    }
  }

  const activeStep = useMemo(() => {
    if (!active) return -1;
    if (active.status === "COMPLETED") return steps.length;
    if (active.current_step.includes("refund")) return 4;
    if (active.current_step.includes("risk") || active.current_step.includes("approval")) return 3;
    if (active.current_step.includes("policy")) return 2;
    if (active.current_step.includes("order")) return 1;
    return 0;
  }, [active]);

  return (
    <div className="workspace customer-workspace">
      <aside className="ticket-rail">
        <div className="section-heading compact">
          <p className="eyebrow">我的售后</p>
          <h2>退款工单</h2>
        </div>
        <div className="ticket-list">
          {tickets.length === 0 && (
            <div className="empty-state small">
              <strong>还没有工单</strong>
              <span>在右侧描述你的退款需求。</span>
            </div>
          )}
          {tickets.map((ticket) => (
            <button
              key={ticket.id}
              className={active?.id === ticket.id ? "ticket-row active" : "ticket-row"}
              onClick={() => void refresh(ticket.id)}
            >
              <span>
                <strong>{ticket.order_number ?? "待识别订单"}</strong>
                <small>{ticket.product_name ?? "售后申请"}</small>
              </span>
              <StatusPill status={ticket.status} />
            </button>
          ))}
        </div>
      </aside>

      <section className="conversation-panel">
        <div className="conversation-header">
          <div>
            <p className="eyebrow">售后对话</p>
            <h1>{active?.product_name ?? "描述你的退款需求"}</h1>
          </div>
          {active && <StatusPill status={active.status} />}
        </div>

        <div className="messages" aria-live="polite">
          {!active && (
            <div className="welcome-note">
              <span className="brand-mark">归</span>
              <div>
                <strong>你好，我是归舟售后助手。</strong>
                <p>请告诉我订单号和退款原因。我会核验订单、政策与风险，再给你明确结果。</p>
                <div className="quick-orders">
                  {["ORD-399 自动退款", "ORD-699 需审批", "ORD-299-UNKNOWN 异常"].map(
                    (item) => (
                      <button
                        key={item}
                        onClick={() => setMessage("我想退货，订单号 " + item.split(" ")[0])}
                      >
                        {item}
                      </button>
                    )
                  )}
                </div>
              </div>
            </div>
          )}
          {active?.messages?.map((item) => (
            <div
              key={item.id}
              className={item.sender === "USER" ? "message message--user" : "message message--agent"}
            >
              <small>{item.sender === "USER" ? "你" : "归舟助手"}</small>
              <p>{item.content}</p>
            </div>
          ))}
          {active && !terminalStates.has(active.status) && active.status !== "WAITING_APPROVAL" && (
            <div className="processing-note">
              <i />
              正在核验订单与退款规则…
            </div>
          )}
        </div>

        {error && <p className="error-banner">{error}</p>}
        <div className="composer">
          <label htmlFor="refund-message">退款需求</label>
          <div>
            <textarea
              id="refund-message"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="例如：我想退货，订单号 ORD-399"
              rows={2}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            <button className="primary-button" onClick={send} disabled={sending || !message.trim()}>
              {sending ? "发送中…" : "提交申请"}
            </button>
          </div>
          <small>Enter 发送，Shift + Enter 换行</small>
        </div>
      </section>

      <aside className="evidence-panel">
        <div className="section-heading compact">
          <p className="eyebrow">处理轨迹</p>
          <h2>每一步都有依据</h2>
        </div>
        <ol className="process-track">
          {steps.map(([key, label], index) => (
            <li
              key={key}
              className={index < activeStep ? "done" : index === activeStep ? "current" : ""}
            >
              <i>{index < activeStep ? "✓" : index + 1}</i>
              <span>
                <strong>{label}</strong>
                {index === activeStep && <small>{active?.current_step ?? "等待开始"}</small>}
              </span>
            </li>
          ))}
        </ol>
        {active?.calculated_amount && (
          <div className="amount-slip">
            <small>核算退款金额</small>
            <strong>¥{active.approved_amount ?? active.calculated_amount}</strong>
            <span>{active.order_number}</span>
          </div>
        )}
        {active?.risk_reasons && active.risk_reasons.length > 0 && (
          <div className="risk-note">
            <strong>需要审批的原因</strong>
            <ul>
              {active.risk_reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}
