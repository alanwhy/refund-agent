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
    title: "正常订单",
    amount: "按金额判断",
    description: "不超过 ¥500 自动退款，超过后进入金额审批。",
  },
  {
    value: "RISK_APPROVAL",
    title: "风控订单",
    amount: "叠加金额规则",
    description: "命中风险信号；金额超过 ¥500 时保留两条原因。",
  },
  {
    value: "PAYMENT_UNKNOWN",
    title: "支付异常订单",
    amount: "执行结果未知",
    description: "通过前置规则后，支付结果未知并进入异常处理。",
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
  const [amount, setAmount] = useState("399.00");
  const [scenario, setScenario] = useState<DemoOrderScenario>("AUTO_REFUND");
  const [requestId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const amountValue = Number(amount);
  const amountValid =
    /^\d+(\.\d{1,2})?$/.test(amount) && amountValue >= 0.01 && amountValue <= 999999.99;

  async function createOrder() {
    if (!customerId || productName.trim().length < 2 || !amountValid || busy) return;
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
            amount,
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
        <label htmlFor="demo-amount">
          订单金额
          <span className="money-input">
            <span>¥</span>
            <input
              id="demo-amount"
              type="number"
              inputMode="decimal"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              min="0.01"
              max="999999.99"
              step="0.01"
              aria-invalid={!amountValid}
            />
          </span>
          {!amountValid && <small className="field-error">请输入 0.01–999999.99，最多两位小数</small>}
        </label>
      </div>

      <fieldset className="scenario-picker">
        <legend>选择订单特征</legend>
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
          disabled={busy || !customerId || productName.trim().length < 2 || !amountValid}
        >
          {busy ? "正在创建…" : "创建订单"}
        </button>
      </div>
    </section>
  );
}
