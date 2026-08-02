import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { api } from "../api";
import { AuditPage } from "../pages/AuditPage";

vi.mock("../auth", () => ({
  useAuth: () => ({ token: "admin-token" }),
}));

vi.mock("../api", () => ({ api: vi.fn() }));

const requested = {
  id: "audit-requested",
  ticket_id: "ticket-1",
  actor_id: null,
  action: "model.requested",
  entity_type: "model",
  entity_id: null,
  details: {
    model: "demo-model",
    logical_step: 1,
    input: { messages: [{ type: "system", content: "系统提示" }], tools: ["get_order"] },
  },
  run_id: "run-1",
  node_name: "reason_and_route",
  trace_id: "trace-requested",
  created_at: "2026-08-02T00:00:00Z",
};

const completed = {
  ...requested,
  id: "audit-completed",
  action: "model.completed",
  details: {
    model: "demo-model",
    logical_step: 1,
    output: {
      type: "ai",
      content: "查询完成",
      tool_calls: [{ name: "get_order", args: { order_number: "ORD-399" } }],
    },
    duration_ms: 210,
    usage: { input_tokens: 12, output_tokens: 4 },
  },
};

beforeEach(() => {
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.includes("category=model")) return [completed, requested] as never;
    return [] as never;
  });
});

it("separates model calls and renders structured input and output", async () => {
  const user = userEvent.setup();
  render(<AuditPage />);

  await user.click(screen.getByRole("button", { name: "模型调用" }));

  await waitFor(() => {
    expect(vi.mocked(api).mock.calls.some(([path]) => path.includes("category=model"))).toBe(true);
  });
  expect(await screen.findByText("模型输入")).toBeInTheDocument();
  expect(screen.getByText("模型输出")).toBeInTheDocument();
  expect(screen.getByText("Tool Calls")).toBeInTheDocument();
  expect(screen.getByText("demo-model")).toBeInTheDocument();
  expect(screen.getByText(/系统提示/)).toBeInTheDocument();
  expect(screen.getByText(/查询完成/)).toBeInTheDocument();
  expect(screen.getAllByText(/get_order/)).toHaveLength(3);
  expect(screen.getByText(/210 ms/)).toBeInTheDocument();
});
