import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { StatusPill } from "../components/StatusPill";
import type { ManualReviewTask } from "../types";

const categoryLabels: Record<ManualReviewTask["category"], string> = {
  MODEL_FAILURE: "智能助手异常",
  PAYMENT_UNKNOWN: "支付结果未知",
  DATA_INCONSISTENCY: "数据不一致",
  SECURITY_REJECTION: "安全校验拦截",
};

export function ManualReviewPage() {
  const { token } = useAuth();
  const [tasks, setTasks] = useState<ManualReviewTask[]>([]);
  const [selected, setSelected] = useState<ManualReviewTask | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    const result = await api<ManualReviewTask[]>("/manual-review-tasks", {}, token);
    setTasks(result);
    setSelected((current) => result.find((item) => item.id === current?.id) ?? result[0] ?? null);
  }, [token]);

  useEffect(() => {
    void load().catch((reason) => setError(reason instanceof Error ? reason.message : "异常队列加载失败"));
  }, [load]);

  async function claim() {
    if (!token || !selected) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api<ManualReviewTask>(
        `/manual-review-tasks/${selected.id}/assign`,
        { method: "POST", body: JSON.stringify({ version: selected.version }) },
        token,
      );
      setSelected(updated);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "认领失败");
    } finally {
      setBusy(false);
    }
  }

  async function resolve(status: "RESOLVED" | "UNRESOLVABLE") {
    if (!token || !selected || !note.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api<ManualReviewTask>(
        `/manual-review-tasks/${selected.id}/resolution`,
        {
          method: "POST",
          body: JSON.stringify({ version: selected.version, status, resolution_note: note.trim() }),
        },
        token,
      );
      setNote("");
      await load();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        setError("任务已被其他处理人更新，已为你刷新最新状态。");
        await load();
      } else {
        setError(reason instanceof Error ? reason.message : "处理结果未保存");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace manual-review-workspace">
      <aside className="manual-review-queue">
        <div className="section-heading">
          <p className="eyebrow">EXCEPTION DESK</p>
          <h1>异常处理</h1>
          <p className="muted">处理系统异常，不在这里批准退款。</p>
        </div>
        <div className="queue-count"><strong>{tasks.filter((task) => task.status === "PENDING").length}</strong><span>项待处理</span></div>
        <div className="ticket-list">
          {tasks.map((task) => (
            <button
              key={task.id}
              className={selected?.id === task.id ? "exception-row active" : "exception-row"}
              onClick={() => { setSelected(task); setNote(task.resolution_note ?? ""); }}
            >
              <span><strong>{task.submitted_order_number ?? task.order_number ?? "未识别订单"}</strong><small>{task.customer_name} · {categoryLabels[task.category]}</small></span>
              <StatusPill status={task.status} label={task.status === "PENDING" ? "待处理" : undefined} />
            </button>
          ))}
          {tasks.length === 0 && <div className="empty-state small"><strong>异常队列为空</strong><span>技术异常会自动进入这里。</span></div>}
        </div>
      </aside>
      <section className="manual-review-detail">
        {!selected ? <div className="empty-state"><span className="empty-symbol">检</span><strong>没有需要核查的异常</strong></div> : <>
          <div className="detail-header">
            <div><p className="eyebrow">异常任务 {selected.id.slice(0, 8)}</p><h1>{categoryLabels[selected.category]}</h1><p className="muted">{selected.customer_name} · {selected.submitted_order_number ?? selected.order_number ?? "未识别订单"}</p></div>
            <StatusPill status={selected.status} label={selected.status === "PENDING" ? "待处理" : undefined} />
          </div>
          <div className="exception-facts">
            <article><small>客户可见状态</small><strong>{selected.ticket_status}</strong></article>
            <article><small>已验证订单</small><strong>{selected.product_name ?? "未找到可验证订单"}</strong><span>{selected.order_number ?? "仅保留用户提交的订单号"}</span></article>
            <article><small>当前处理人</small><strong>{selected.assigned_name ?? "尚未认领"}</strong></article>
          </div>
          <section className="technical-note"><p className="eyebrow">受控技术摘要</p><p>{selected.technical_summary}</p></section>
          <section className="resolution-panel">
            <label htmlFor="resolution-note">内部处理备注</label>
            <textarea id="resolution-note" rows={4} value={note} onChange={(event) => setNote(event.target.value)} placeholder="记录核查结果，不会发送给客户" disabled={selected.status !== "PENDING"} />
            {error && <p className="error-banner">{error}</p>}
            <div className="decision-actions">
              {!selected.assigned_to && <button className="secondary-button" onClick={() => void claim()} disabled={busy || selected.status !== "PENDING"}>认领任务</button>}
              <button className="danger-button" onClick={() => void resolve("UNRESOLVABLE")} disabled={busy || selected.status !== "PENDING" || !note.trim()}>标记无法解决</button>
              <button className="primary-button" onClick={() => void resolve("RESOLVED")} disabled={busy || selected.status !== "PENDING" || !note.trim()}>标记已解决</button>
            </div>
          </section>
        </>}
      </section>
    </div>
  );
}
