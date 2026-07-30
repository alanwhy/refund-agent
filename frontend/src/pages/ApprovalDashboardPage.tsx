import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { StatusPill } from "../components/StatusPill";
import type { Approval } from "../types";

export function ApprovalDashboardPage() {
  const { token } = useAuth();
  const [items, setItems] = useState<Approval[]>([]);
  const [selected, setSelected] = useState<Approval | null>(null);
  const [amount, setAmount] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    const approvals = await api<Approval[]>("/approvals", {}, token);
    setItems(approvals);
    setSelected((current) => {
      const next = approvals.find((item) => item.id === current?.id) ?? approvals[0] ?? null;
      if (next) setAmount(next.approved_amount ?? next.suggested_amount);
      return next;
    });
  }, [token]);

  useEffect(() => {
    void load().catch((reason) =>
      setError(reason instanceof Error ? reason.message : "审批列表加载失败")
    );
  }, [load]);

  async function decide(decision: "APPROVE" | "MODIFY_APPROVE" | "REJECT") {
    if (!token || !selected) return;
    setBusy(true);
    setError("");
    try {
      await api<Approval>("/approvals/" + selected.id + "/decision", {
        method: "POST",
        body: JSON.stringify({
          decision,
          version: selected.version,
          approved_amount: decision === "REJECT" ? null : amount,
          comment
        })
      }, token);
      setComment("");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "审批决定未保存");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace approval-workspace">
      <aside className="approval-queue">
        <div className="section-heading">
          <p className="eyebrow">HUMAN IN THE LOOP</p>
          <h1>审批队列</h1>
          <p className="muted">只处理证据完整、规则明确的退款申请。</p>
        </div>
        <div className="queue-count">
          <strong>{items.filter((item) => ["PENDING", "ESCALATED"].includes(item.status)).length}</strong>
          <span>笔待处理</span>
        </div>
        <div className="ticket-list">
          {items.length === 0 && (
            <div className="empty-state small">
              <strong>队列已清空</strong>
              <span>新的高风险退款会出现在这里。</span>
            </div>
          )}
          {items.map((item) => (
            <button
              key={item.id}
              className={selected?.id === item.id ? "approval-row active" : "approval-row"}
              onClick={() => {
                setSelected(item);
                setAmount(item.approved_amount ?? item.suggested_amount);
              }}
            >
              <span className="row-top">
                <strong>{item.order_number ?? "未知订单"}</strong>
                <StatusPill status={item.status} />
              </span>
              <span>{item.product_name ?? "退款申请"}</span>
              <small>
                ¥{item.suggested_amount} · {item.customer_name}
              </small>
            </button>
          ))}
        </div>
      </aside>

      <section className="approval-detail">
        {!selected ? (
          <div className="empty-state">
            <span className="empty-symbol">✓</span>
            <strong>没有待审核申请</strong>
            <span>队列中的退款申请会按照创建时间排列。</span>
          </div>
        ) : (
          <>
            <div className="detail-header">
              <div>
                <p className="eyebrow">审批单 {selected.id.slice(0, 8)}</p>
                <h1>{selected.product_name}</h1>
                <p className="muted">{selected.order_number} · {selected.customer_name}</p>
              </div>
              <StatusPill status={selected.status} />
            </div>

            <div className="evidence-grid">
              <article className="evidence-card amount-card">
                <span>建议退款</span>
                <strong>¥{selected.suggested_amount}</strong>
                <small>服务端按订单实付金额核算</small>
              </article>
              <article className="evidence-card">
                <span>审批时限</span>
                <strong>{new Date(selected.expires_at).toLocaleTimeString("zh-CN", {
                  hour: "2-digit",
                  minute: "2-digit"
                })}</strong>
                <small>{selected.status === "ESCALATED" ? "已超时升级" : "超时后进入管理员队列"}</small>
              </article>
            </div>

            <section className="proof-section">
              <div className="section-heading compact">
                <p className="eyebrow">风险证据</p>
                <h2>为什么需要人工确认</h2>
              </div>
              <ol className="proof-list">
                {selected.risk_reasons.map((reason, index) => (
                  <li key={reason}>
                    <i>{String(index + 1).padStart(2, "0")}</i>
                    <span>{reason}</span>
                    <b>规则命中</b>
                  </li>
                ))}
              </ol>
            </section>

            <section className="decision-panel">
              <div className="section-heading compact">
                <p className="eyebrow">审批决定</p>
                <h2>确认可执行金额</h2>
              </div>
              <label>
                批准退款金额
                <div className="money-input">
                  <span>¥</span>
                  <input
                    type="number"
                    min="0.01"
                    max={selected.suggested_amount}
                    step="0.01"
                    value={amount}
                    onChange={(event) => setAmount(event.target.value)}
                    disabled={selected.status === "APPROVED" || selected.status === "REJECTED"}
                  />
                </div>
              </label>
              <label>
                审批备注
                <textarea
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  rows={3}
                  placeholder="记录判断依据，方便后续审计"
                  disabled={selected.status === "APPROVED" || selected.status === "REJECTED"}
                />
              </label>
              {error && <p className="error-banner">{error}</p>}
              <div className="decision-actions">
                <button
                  className="danger-button"
                  onClick={() => void decide("REJECT")}
                  disabled={busy || !["PENDING", "ESCALATED"].includes(selected.status)}
                >
                  拒绝退款
                </button>
                <button
                  className="primary-button"
                  onClick={() =>
                    void decide(amount === selected.suggested_amount ? "APPROVE" : "MODIFY_APPROVE")
                  }
                  disabled={busy || !["PENDING", "ESCALATED"].includes(selected.status)}
                >
                  {busy ? "正在保存…" : "批准并继续执行"}
                </button>
              </div>
            </section>
          </>
        )}
      </section>
    </div>
  );
}
