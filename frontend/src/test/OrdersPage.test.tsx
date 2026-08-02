import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { api } from "../api";
import { OrdersPage } from "../pages/OrdersPage";

vi.mock("../auth", () => ({
  useAuth: () => ({
    token: "customer-token",
    user: { id: "customer", role: "CUSTOMER", display_name: "林晓" },
  }),
}));

vi.mock("../api", () => ({ api: vi.fn() }));

beforeEach(() => vi.mocked(api).mockReset());

it("renders a customer-safe order ledger", async () => {
  vi.mocked(api).mockResolvedValue([
    {
      id: "order-1",
      order_number: "ORD-399",
      product_name: "云感步行鞋",
      amount: "399.00",
      status: "DELIVERED",
      delivered_at: "2026-08-01T00:00:00Z",
      customer_id: null,
      customer_name: null,
      ticket_id: null,
      ticket_status: null,
      approval_id: null,
      approval_status: null,
      approval_assigned_to: null,
      risk_reasons: null,
      manual_review_id: null,
      manual_review_category: null,
    },
  ]);
  render(<OrdersPage />);
  expect(await screen.findByText("云感步行鞋")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "我的订单" })).toBeInTheDocument();
  expect(screen.queryByText("风险规则")).not.toBeInTheDocument();
});
