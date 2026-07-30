import { useState } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../auth";
import type { Role } from "../types";

const accounts: Array<{
  role: Role;
  title: string;
  email: string;
  description: string;
}> = [
  {
    role: "CUSTOMER",
    title: "客户入口",
    email: "customer@example.com",
    description: "发起退款并查看处理轨迹"
  },
  {
    role: "APPROVER",
    title: "审批入口",
    email: "approver@example.com",
    description: "核验高风险退款证据"
  },
  {
    role: "ADMIN",
    title: "管理入口",
    email: "admin@example.com",
    description: "查看审批与全链路审计"
  }
];

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [selected, setSelected] = useState(accounts[0]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function signIn() {
    setLoading(true);
    setError("");
    try {
      const user = await login(selected.email, "Demo123!");
      navigate(user.role === "CUSTOMER" ? "/chat" : "/approvals");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录未完成");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-intro">
        <div className="brand brand--login">
          <span className="brand-mark">归</span>
          <span>
            <strong>归舟</strong>
            <small>智能售后处理台</small>
          </span>
        </div>
        <p className="eyebrow">REFUND WITH EVIDENCE</p>
        <h1>
          每一笔退款，
          <br />
          都沿证据前行。
        </h1>
        <p className="intro-copy">
          从政策核验到人工审批，把复杂的售后流程整理成一条清晰、可暂停、可追溯的处理轨迹。
        </p>
        <div className="route-sketch" aria-label="处理流程：受理、核验、风控、退款">
          {["受理", "核验", "风控", "退款"].map((label, index) => (
            <span key={label}>
              <i>{index + 1}</i>
              {label}
            </span>
          ))}
        </div>
      </section>

      <section className="login-panel" aria-labelledby="login-title">
        <div>
          <p className="eyebrow">演示环境</p>
          <h2 id="login-title">选择你的工作入口</h2>
          <p className="muted">账号与数据均为演示用途，不会产生真实退款。</p>
        </div>
        <div className="role-options">
          {accounts.map((account) => (
            <button
              type="button"
              key={account.role}
              className={selected.role === account.role ? "role-card selected" : "role-card"}
              onClick={() => setSelected(account)}
              aria-pressed={selected.role === account.role}
            >
              <span className="role-letter">{account.title.slice(0, 1)}</span>
              <span>
                <strong>{account.title}</strong>
                <small>{account.description}</small>
              </span>
              <i aria-hidden="true">→</i>
            </button>
          ))}
        </div>
        {error && <p className="error-banner">{error}</p>}
        <button className="primary-button full-width" onClick={signIn} disabled={loading}>
          {loading ? "正在进入…" : "进入" + selected.title}
        </button>
        <p className="demo-credential">演示密码：Demo123!</p>
      </section>
    </main>
  );
}
