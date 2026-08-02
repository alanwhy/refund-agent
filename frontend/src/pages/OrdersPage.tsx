import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { StatusPill } from "../components/StatusPill";
import type { OrderView } from "../types";

const titles = {
  CUSTOMER: ["我的订单", "查看自己的订单与售后处理进度。"],
  APPROVER: ["审批订单", "这里只展示进入你审批范围的退款订单。"],
  ADMIN: ["全部订单", "查看订单与退款、审批和异常记录的关联。"],
} as const;

export function OrdersPage() {
  const { token, user } = useAuth();
  const [orders, setOrders] = useState<OrderView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    api<OrderView[]>("/orders", {}, token)
      .then(setOrders)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "订单加载失败"))
      .finally(() => setLoading(false));
  }, [token]);

  if (!user) return null;
  const [title, description] = titles[user.role];

  return (
    <div className="record-page orders-page">
      <header className="record-page__header">
        <div>
          <p className="eyebrow">ORDER LEDGER</p>
          <h1>{title}</h1>
          <p className="muted">{description}</p>
        </div>
        <span className="record-count">{orders.length} 笔</span>
      </header>
      {error && <p className="error-banner">{error}</p>}
      {loading ? (
        <div className="empty-state"><strong>正在读取订单…</strong></div>
      ) : orders.length === 0 ? (
        <div className="empty-state">
          <span className="empty-symbol">单</span>
          <strong>当前没有可查看的订单</strong>
          <span>{user.role === "APPROVER" ? "需要审批的订单会出现在这里。" : "订单生成后会显示在这里。"}</span>
        </div>
      ) : (
        <div className="order-ledger">
          {orders.map((order) => (
            <article className="order-entry" key={order.id}>
              <div className="order-entry__number">
                <small>订单号</small>
                <strong>{order.order_number}</strong>
              </div>
              <div className="order-entry__product">
                <strong>{order.product_name}</strong>
                <span>{new Date(order.delivered_at).toLocaleDateString("zh-CN")} 签收</span>
                {user.role === "ADMIN" && <span>客户 · {order.customer_name}</span>}
              </div>
              <div className="order-entry__amount">
                <small>实付金额</small>
                <strong>¥{order.amount}</strong>
              </div>
              <div className="order-entry__status">
                <StatusPill status={order.status} />
                {order.ticket_status && <StatusPill status={order.ticket_status} />}
              </div>
              {(user.role === "APPROVER" || user.role === "ADMIN") && order.approval_status && (
                <div className="order-entry__relation">
                  <small>退款审批</small>
                  <StatusPill status={order.approval_status} />
                  {order.risk_reasons?.map((reason) => <span key={reason}>{reason}</span>)}
                </div>
              )}
              {user.role === "ADMIN" && order.manual_review_id && (
                <div className="order-entry__relation">
                  <small>技术异常</small>
                  <span>{order.manual_review_category}</span>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
