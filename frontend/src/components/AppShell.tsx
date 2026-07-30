import type { PropsWithChildren } from "react";
import { NavLink } from "react-router";
import { useAuth } from "../auth";

const roleLabels = {
  CUSTOMER: "客户",
  APPROVER: "审批专员",
  ADMIN: "管理员"
};

export function AppShell({ children }: PropsWithChildren) {
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <div className="app-shell">
      <header className="masthead">
        <NavLink to="/" className="brand" aria-label="归舟智能售后首页">
          <span className="brand-mark" aria-hidden="true">
            归
          </span>
          <span>
            <strong>归舟</strong>
            <small>智能售后处理台</small>
          </span>
        </NavLink>
        <nav className="main-nav" aria-label="主导航">
          {user.role === "CUSTOMER" && <NavLink to="/chat">申请退款</NavLink>}
          {(user.role === "APPROVER" || user.role === "ADMIN") && (
            <NavLink to="/approvals">审批工作台</NavLink>
          )}
          {user.role === "ADMIN" && <NavLink to="/audit">审计记录</NavLink>}
        </nav>
        <div className="account">
          <span>
            <strong>{user.display_name}</strong>
            <small>{roleLabels[user.role]}</small>
          </span>
          <button className="text-button" onClick={logout}>
            退出
          </button>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
