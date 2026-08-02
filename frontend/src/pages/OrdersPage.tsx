import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { api } from "../api";
import { useAuth } from "../auth";
import { DemoOrderForm } from "../components/DemoOrderForm";
import { StatusPill } from "../components/StatusPill";
import type { DemoCustomer, DemoOrderCreateResponse, OrderView } from "../types";

const titles = {
  CUSTOMER: ["我的订单", "查看自己的订单与售后处理进度。"],
  APPROVER: ["审批订单", "这里只展示进入你审批范围的退款订单。"],
  ADMIN: ["全部订单", "查看订单与退款、审批和异常记录的关联。"],
} as const;

export function OrdersPage() {
  const navigate = useNavigate();
  const { token, user } = useAuth();
  const [orders, setOrders] = useState<OrderView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [customers, setCustomers] = useState<DemoCustomer[]>([]);
  const [customerError, setCustomerError] = useState("");
  const [success, setSuccess] = useState("");
  const [highlightedOrderId, setHighlightedOrderId] = useState<string | null>(null);

  const loadOrders = useCallback(async () => {
    if (!token) return;
    const result = await api<OrderView[]>("/orders", {}, token);
    setOrders(result);
  }, [token]);

  useEffect(() => {
    setLoading(true);
    void loadOrders()
      .catch((reason) => setError(reason instanceof Error ? reason.message : "订单加载失败"))
      .finally(() => setLoading(false));
  }, [loadOrders]);

  useEffect(() => {
    if (!highlightedOrderId) return;
    const timer = window.setTimeout(() => setHighlightedOrderId(null), 5000);
    return () => window.clearTimeout(timer);
  }, [highlightedOrderId]);

  if (!user) return null;
  const [title, description] = titles[user.role];

  async function openDemoOrderForm() {
    setSuccess("");
    setHighlightedOrderId(null);
    setCustomerError("");
    if (customers.length === 0 && token) {
      try {
        setCustomers(await api<DemoCustomer[]>("/demo/customers", {}, token));
      } catch (reason) {
        setCustomerError(reason instanceof Error ? reason.message : "客户列表加载失败");
      }
    }
    setFormOpen(true);
  }

  function handleCreated(result: DemoOrderCreateResponse) {
    setFormOpen(false);
    setHighlightedOrderId(result.order.id);
    setOrders((current) => [result.order, ...current.filter((item) => item.id !== result.order.id)]);
    setSuccess(
      `测试订单 ${result.order.order_number} 已创建，请使用 ${result.order.customer_email} 发起退款。`,
    );
    void loadOrders().catch(() => {
      setError("订单已创建，但列表刷新失败。请点击刷新订单列表。");
    });
  }

  function openAfterSales(order: OrderView) {
    if (order.ticket_id) {
      navigate(`/chat?ticket_id=${encodeURIComponent(order.ticket_id)}`);
      return;
    }
    navigate(
      `/chat?order_id=${encodeURIComponent(order.id)}&order_number=${encodeURIComponent(order.order_number)}`,
    );
  }

  return (
    <div className="record-page orders-page">
      <header className="record-page__header">
        <div>
          <p className="eyebrow">ORDER LEDGER</p>
          <h1>{title}</h1>
          <p className="muted">{description}</p>
        </div>
        <div className="record-page__actions">
          <span className="record-count">{orders.length} 笔</span>
          {user.role === "ADMIN" && (
            <button className="primary-button" onClick={() => void openDemoOrderForm()}>
              新建测试订单
            </button>
          )}
        </div>
      </header>
      {success && <p className="success-banner" role="status">{success}</p>}
      {error && <p className="error-banner">{error}</p>}
      {customerError && <p className="error-banner">{customerError}</p>}
      {formOpen && token && customers.length > 0 && (
        <DemoOrderForm
          customers={customers}
          token={token}
          onCancel={() => setFormOpen(false)}
          onCreated={handleCreated}
        />
      )}
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
            <article
              className={
                highlightedOrderId === order.id ? "order-entry order-entry--new" : "order-entry"
              }
              key={order.id}
            >
              <div className="order-entry__number">
                <small>订单号</small>
                <strong>{order.order_number}</strong>
              </div>
              <div className="order-entry__product">
                <strong>{order.product_name}</strong>
                <span>{new Date(order.delivered_at).toLocaleDateString("zh-CN")} 签收</span>
                {user.role === "ADMIN" && (
                  <span>客户 · {order.customer_name} · {order.customer_email}</span>
                )}
              </div>
              <div className="order-entry__amount">
                <small>实付金额</small>
                <strong>¥{order.amount}</strong>
              </div>
              <div className="order-entry__status">
                <StatusPill status={order.lifecycle_status} />
              </div>
              {user.role === "CUSTOMER" && (
                <div className="order-entry__action">
                  <button className="secondary-button" onClick={() => openAfterSales(order)}>
                    {order.ticket_id ? "查看售后" : "申请售后"}
                  </button>
                </div>
              )}
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
