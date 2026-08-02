import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { api } from "../api";
import { ManualReviewPage } from "../pages/ManualReviewPage";

vi.mock("../auth", () => ({ useAuth: () => ({ token: "approver-token" }) }));
vi.mock("../api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api")>();
  return { ...original, api: vi.fn() };
});

beforeEach(() => vi.mocked(api).mockReset());

it("shows technical handling actions without refund approval controls", async () => {
  vi.mocked(api).mockResolvedValue([
    {
      id: "manual-1",
      ticket_id: "ticket-1",
      status: "PENDING",
      category: "MODEL_FAILURE",
      version: 1,
      submitted_order_number: "ORD-400",
      technical_summary: "智能助手服务异常，需要人工继续处理。",
      assigned_to: null,
      assigned_name: null,
      resolution_note: null,
      resolved_by: null,
      customer_name: "林晓",
      order_id: null,
      order_number: null,
      product_name: null,
      ticket_status: "MANUAL_REVIEW",
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-01T00:00:00Z",
      resolved_at: null,
    },
  ]);
  render(<ManualReviewPage />);
  expect(await screen.findByText("智能助手服务异常，需要人工继续处理。")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "认领任务" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "标记已解决" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /批准退款/ })).not.toBeInTheDocument();
});
