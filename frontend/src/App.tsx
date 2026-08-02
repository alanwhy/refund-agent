import { Navigate, Outlet, Route, Routes } from "react-router";
import { useAuth } from "./auth";
import { AppShell } from "./components/AppShell";
import { ApprovalDashboardPage } from "./pages/ApprovalDashboardPage";
import { AuditPage } from "./pages/AuditPage";
import { CustomerChatPage } from "./pages/CustomerChatPage";
import { LoginPage } from "./pages/LoginPage";
import { ManualReviewPage } from "./pages/ManualReviewPage";
import { OrdersPage } from "./pages/OrdersPage";
import type { Role } from "./types";

function Protected({ roles }: { roles: Role[] }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (!roles.includes(user.role)) {
    return <Navigate to={user.role === "CUSTOMER" ? "/chat" : "/approvals"} replace />;
  }
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

function Home() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === "CUSTOMER" ? "/chat" : "/approvals"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Protected roles={["CUSTOMER"]} />}>
        <Route path="/chat" element={<CustomerChatPage />} />
      </Route>
      <Route element={<Protected roles={["CUSTOMER", "APPROVER", "ADMIN"]} />}>
        <Route path="/orders" element={<OrdersPage />} />
      </Route>
      <Route element={<Protected roles={["APPROVER", "ADMIN"]} />}>
        <Route path="/approvals" element={<ApprovalDashboardPage />} />
        <Route path="/manual-reviews" element={<ManualReviewPage />} />
      </Route>
      <Route element={<Protected roles={["ADMIN"]} />}>
        <Route path="/audit" element={<AuditPage />} />
      </Route>
      <Route path="/" element={<Home />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
