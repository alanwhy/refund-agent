import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { StatusPill } from "../components/StatusPill";
import type { ChatAccepted, Ticket } from "../types";
import { buildChatPayload, pollDelayForStatus } from "./customerChatState";

const terminalStates = new Set(["COMPLETED", "REJECTED", "FAILED", "MANUAL_REVIEW"]);
const steps = [
  ["collect", "收集退款信息"],
  ["order", "查询并核验订单"],
  ["policy", "检索适用政策"],
  ["risk", "评估退款风险"],
  ["approval", "确认是否需审批"],
  ["refund", "执行退款"],
] as const;

const stepDescriptions: Record<string, string> = {
  created: "准备开始处理",
  waiting_user: "等待你补充必要信息",
  user_input_submitted: "已收到补充信息",
  user_input_received: "正在理解补充信息",
  order_validation: "订单归属已核验",
  policy_check: "正在匹配退款政策",
  risk_check: "正在执行风险规则",
  waiting_approval: "等待售后专员审批",
  approval_escalated: "审批已升级处理",
  approval_approved: "审批通过，准备退款",
  approval_rejected: "审批未通过",
  completed: "退款处理完成",
  payment_unknown: "支付结果需人工核查",
  payment_failed: "退款执行失败",
  manual_review: "已转交人工核查",
};

function stepIndex(ticket: Ticket | null): number {
  if (!ticket) return -1;
  if (ticket.status === "COMPLETED") return steps.length;
  const current = ticket.current_step;
  if (current.includes("refund") || current.includes("payment")) return 5;
  if (current.includes("approval")) return 4;
  if (current.includes("risk")) return 3;
  if (current.includes("policy")) return 2;
  if (current.includes("order")) return 1;
  return 0;
}

export function CustomerChatPage() {
  const { token } = useAuth();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [active, setActive] = useState<Ticket | null>(null);
  const [selectedTicketId, setSelectedTicketId] = useState<string | undefined>();
  const [message, setMessage] = useState("我想退货，订单号 ORD-399");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(
    async (preferredId?: string) => {
      if (!token) return;
      const list = await api<Ticket[]>("/tickets", {}, token);
      setTickets(list);
      const targetId = preferredId ?? selectedTicketId ?? list[0]?.id;
      if (!targetId) {
        setActive(null);
        return;
      }
      const detail = await api<Ticket>("/tickets/" + targetId, {}, token);
      setSelectedTicketId(targetId);
      setActive(detail);
    },
    [token, selectedTicketId],
  );

  useEffect(() => {
    void refresh().catch((reason) =>
      setError(reason instanceof Error ? reason.message : "工单加载失败"),
    );
  }, [refresh]);

  useEffect(() => {
    if (!active) return;
    const delay = pollDelayForStatus(active.status);
    if (delay === null) return;
    const timer = window.setTimeout(() => {
      void refresh(active.id).catch((reason) =>
        setError(reason instanceof Error ? reason.message : "工单刷新失败"),
      );
    }, delay);
    return () => window.clearTimeout(timer);
  }, [active, refresh]);

  const canSend =
    !active || terminalStates.has(active.status) || active.status === "WAITING_USER";

  async function send() {
    if (!token || !message.trim() || !canSend) return;
    setSending(true);
    setError("");
    try {
      const accepted = await api<ChatAccepted>(
        "/chat/messages",
        {
          method: "POST",
          body: JSON.stringify(buildChatPayload(message.trim(), active)),
        },
        token,
      );
      setMessage("");
      await refresh(accepted.ticket_id);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409 && active) {
        setError("工单状态已更新，正在为你刷新。请查看最新提示后再继续。 ");
        await refresh(active.id);
      } else {
        setError(reason instanceof Error ? reason.message : "申请未发送");
      }
    } finally {
      setSending(false);
    }
  }

  const activeStep = useMemo(() => stepIndex(active), [active]);
  const waitingForUser = active?.status === "WAITING_USER";
  const composerLabel = waitingForUser ? "补充信息" : "退款需求";
  const composerPlaceholder = waitingForUser
    ? active.current_question ?? "请补充订单号或退款原因"
    : "例如：我想退货，订单号 ORD-399";

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
                    ),
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
          {waitingForUser && active.current_question && (
            <div className="agent-question" role="status">
              <small>需要你补充</small>
              <strong>{active.current_question}</strong>
              <span>你的回答会继续当前工单，不会新建一张工单。</span>
            </div>
          )}
          {active?.status === "WAITING_APPROVAL" && (
            <div className="approval-wait-note">
              <strong>审批进行中</strong>
              <span>页面会低频检查结果，批准后自动继续退款，无需手动刷新。</span>
            </div>
          )}
          {active && pollDelayForStatus(active.status) === 1_800 && (
            <div className="processing-note">
              <i />
              正在核验订单、政策与风险…
            </div>
          )}
        </div>

        {error && <p className="error-banner">{error}</p>}
        <div className={waitingForUser ? "composer composer--waiting" : "composer"}>
          <label htmlFor="refund-message">{composerLabel}</label>
          <div>
            <textarea
              id="refund-message"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={composerPlaceholder}
              rows={2}
              disabled={!canSend || sending}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            <button
              className="primary-button"
              onClick={send}
              disabled={sending || !message.trim() || !canSend}
            >
              {sending ? "发送中…" : waitingForUser ? "继续处理" : "提交申请"}
            </button>
          </div>
          <small>
            {canSend ? "Enter 发送，Shift + Enter 换行" : "当前工单处理中，完成后可发起新申请"}
          </small>
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
                {index === activeStep && (
                  <small>{stepDescriptions[active?.current_step ?? ""] ?? "正在处理"}</small>
                )}
              </span>
            </li>
          ))}
        </ol>
        {active?.calculated_amount && (
          <div className="amount-slip">
            <small>规则核算退款金额</small>
            <strong>¥{active.approved_amount ?? active.calculated_amount}</strong>
            <span>{active.order_number}</span>
          </div>
        )}
        {active?.policy_evidence && active.policy_evidence.length > 0 && (
          <section className="policy-evidence" aria-label="适用政策">
            <strong>适用政策</strong>
            {active.policy_evidence.map((evidence) => (
              <article key={evidence.document_id + evidence.version}>
                <span>版本 {evidence.version}</span>
                <h3>{evidence.title}</h3>
                <p>{evidence.excerpt}</p>
              </article>
            ))}
          </section>
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
