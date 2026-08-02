import { useState } from "react";
import { api } from "../api";
import type {
  DemoCustomer,
  DemoOrderCreateResponse,
  DemoOrderScenario,
} from "../types";

const scenarios: Array<{
  value: DemoOrderScenario;
  title: string;
  amount: string;
  description: string;
}> = [
  {
    value: "AUTO_REFUND",
    title: "自动退款",
    amount: "¥399",
    description: "规则核验通过后直接完成退款。",
  },
  {
    value: "AMOUNT_APPROVAL",
    title: "金额审批",
    amount: "¥699",
    description: "金额超过 ¥500，进入退款审批。",
  },
  {
    value: "RISK_APPROVAL",
    title: "风控审批",
    amount: "¥199",
    description: "命中风险信号，进入退款审批。",
  },
  {
    value: "PAYMENT_UNKNOWN",
    title: "支付异常",
    amount: "¥299",
    description: "支付结果未知，进入技术异常处理。",
  },
];

interface Props {
  customers: DemoCustomer[];
  token: string;
  onCancel: () => void;
  onCreated: (result: DemoOrderCreateResponse) => void;
}

export function DemoOrderForm({ customers, token, onCancel, onCreated }: Props) {
  const [customerId, setCustomerId] = useState(customers[0]?.id ?? "");
  const [productName, setProductName] = useState("");
  const [scenario, setScenario] = useState<DemoOrderScenario>("AUTO_REFUND");
  const [requestId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function createOrder() {
    if (!customerId || productName.trim().length < 2 || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<DemoOrderCreateResponse>(
        "/demo/orders",
        {
          method: "POST",
          body: JSON.stringify({
            customer_id: customerId,
            product_name: productName.trim(),
            scenario,
            request_id: requestId,
          }),
        },
        token,
      );
      onCreated(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "测试订单创建失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="demo-order-form" aria-labelledby="demo-order-form-title">
      <div className="demo-order-form__intro">
        <p className="eyebrow">DEMO ORDER FACTORY</p>
        <h2 id="demo-order-form-title">新建测试订单</h2>
        <p>订单创建后不会自动退款，请切换到对应客户账号发起售后申请。</p>
      </div>

      <div className="demo-order-fields">
        <label htmlFor="demo-customer">
          订单所属客户
          <select
            id="demo-customer"
            value={customerId}
            onChange={(event) => setCustomerId(event.target.value)}
          >
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.display_name} · {customer.email}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="demo-product">
          商品名称
          <input
            id="demo-product"
            value={productName}
            onChange={(event) => setProductName(event.target.value)}
            placeholder="例如：演示旅行背包"
            maxLength={100}
          />
        </label>
      </div>

      <fieldset className="scenario-picker">
        <legend>选择验证场景</legend>
        <div>
          {scenarios.map((item) => (
            <label
              key={item.value}
              className={scenario === item.value ? "scenario-card selected" : "scenario-card"}
            >
              <input
                type="radio"
                name="demo-scenario"
                value={item.value}
                checked={scenario === item.value}
                onChange={() => setScenario(item.value)}
              />
              <span>
                <strong>{item.title}</strong>
                <b>{item.amount}</b>
              </span>
              <small>{item.description}</small>
            </label>
          ))}
        </div>
      </fieldset>

      {error && <p className="error-banner" role="alert">{error}</p>}
      <div className="demo-order-actions">
        <button className="secondary-button" type="button" onClick={onCancel} disabled={busy}>
          取消
        </button>
        <button
          className="primary-button"
          type="button"
          onClick={() => void createOrder()}
          disabled={busy || !customerId || productName.trim().length < 2}
        >
          {busy ? "正在创建…" : "创建订单"}
        </button>
      </div>
    </section>
  );
}
