import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../api";
import { OrdersPage } from "../pages/OrdersPage";

let role: "CUSTOMER" | "ADMIN" = "CUSTOMER";

vi.mock("../auth", () => ({
  useAuth: () => ({
    token: "test-token",
    user: { id: "user", role, display_name: role === "ADMIN" ? "管理员" : "林晓" },
  }),
}));

vi.mock("../api", () => ({ api: vi.fn() }));

afterEach(cleanup);

const customerOrder = {
  id: "order-1",
  order_number: "ORD-399",
  product_name: "云感步行鞋",
  amount: "399.00",
  status: "DELIVERED",
  lifecycle_status: "DELIVERED",
  delivered_at: "2026-08-01T00:00:00Z",
  customer_id: null,
  customer_name: null,
  customer_email: null,
  ticket_id: null,
  ticket_status: null,
  approval_id: null,
  approval_status: null,
  approval_assigned_to: null,
  risk_reasons: null,
  manual_review_id: null,
  manual_review_category: null,
};

beforeEach(() => {
  role = "CUSTOMER";
  vi.mocked(api).mockReset();
  vi.stubGlobal("crypto", { randomUUID: () => "demo-request-uuid" });
});

function LocationProbe() {
  const location = useLocation();
  return <span>{location.search}</span>;
}

function renderOrders() {
  return render(
    <MemoryRouter initialEntries={["/orders"]}>
      <Routes>
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/chat" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

it("renders a customer-safe order ledger", async () => {
  vi.mocked(api).mockResolvedValue([customerOrder]);
  const user = userEvent.setup();
  renderOrders();
  expect(await screen.findByText("云感步行鞋")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "我的订单" })).toBeInTheDocument();
  expect(screen.queryByText("风险规则")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "新建测试订单" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "申请售后" }));
  expect(screen.getByText(/order_id=order-1/)).toHaveTextContent("order_number=ORD-399");
});

it("lets an administrator create a controlled demo order", async () => {
  role = "ADMIN";
  const createdOrder = {
    ...customerOrder,
    id: "demo-order-1",
    order_number: "ORD-DEMO-20260802-ABC123",
    product_name: "演示旅行背包",
    customer_id: "customer-1",
    customer_name: "林晓",
    customer_email: "customer@example.com",
  };
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === "/orders") return [customerOrder] as never;
    if (path === "/demo/customers") {
      return [{ id: "customer-1", display_name: "林晓", email: "customer@example.com" }] as never;
    }
    if (path === "/demo/orders" && options?.method === "POST") {
      return { order: createdOrder, replayed: false } as never;
    }
    throw new Error("Unexpected API call: " + path);
  });
  const user = userEvent.setup();
  renderOrders();

  await user.click(await screen.findByRole("button", { name: "新建测试订单" }));
  await user.type(screen.getByLabelText("商品名称"), "演示旅行背包");
  await user.clear(screen.getByLabelText(/订单金额/));
  await user.type(screen.getByLabelText(/订单金额/), "699.50");
  await user.click(screen.getByLabelText(/风控订单/));
  await user.click(screen.getByRole("button", { name: "创建订单" }));

  await waitFor(() => {
    const createCall = vi.mocked(api).mock.calls.find(([path]) => path === "/demo/orders");
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      customer_id: "customer-1",
      product_name: "演示旅行背包",
      amount: "699.5",
      scenario: "RISK_APPROVAL",
      request_id: "demo-request-uuid",
    });
  });
  expect(await screen.findByRole("status")).toHaveTextContent(
    "ORD-DEMO-20260802-ABC123",
  );
  expect(screen.getByRole("status")).toHaveTextContent("customer@example.com");
});
