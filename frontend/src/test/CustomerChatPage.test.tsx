import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { CustomerChatPage } from "../pages/CustomerChatPage";
import { buildChatPayload, pollDelayForStatus } from "../pages/customerChatState";
import type { Ticket } from "../types";

vi.mock("../auth", () => ({
  useAuth: () => ({ token: "customer-token" }),
}));

vi.mock("../api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api")>();
  return { ...original, api: vi.fn() };
});

const waitingTicket: Ticket = {
  id: "ticket-waiting-user",
  conversation_id: "conversation-1",
  status: "WAITING_USER",
  current_step: "waiting_user",
  waiting_for: "USER_INPUT",
  current_question: "请提供订单号和退款原因。",
  intent: null,
  order_number: null,
  product_name: null,
  calculated_amount: null,
  risk_level: null,
  messages: [],
  created_at: "2026-08-01T00:00:00Z",
};

describe("CustomerChatPage", () => {
  beforeEach(() => {
    vi.mocked(api).mockReset();
    vi.stubGlobal("crypto", { randomUUID: () => "request-uuid" });
  });

  it("shows the agent question and resumes the same ticket", async () => {
    vi.mocked(api).mockImplementation(async (path, options) => {
      if (path === "/tickets") return [waitingTicket] as never;
      if (path === "/tickets/ticket-waiting-user") return waitingTicket as never;
      if (path === "/chat/messages" && options?.method === "POST") {
        return {
          ticket_id: waitingTicket.id,
          conversation_id: waitingTicket.conversation_id,
          status: "RUNNING",
          waiting_for: null,
          status_url: "/api/tickets/ticket-waiting-user",
        } as never;
      }
      throw new Error("Unexpected API call: " + path);
    });
    const user = userEvent.setup();

    render(<CustomerChatPage />);

    expect(await screen.findByRole("status")).toHaveTextContent("请提供订单号和退款原因。");
    const panel = document.querySelector(".conversation-panel");
    expect(panel?.lastElementChild).toHaveClass("composer");
    const input = screen.getByLabelText("补充信息");
    await user.clear(input);
    await user.type(input, "ORD-399，商品不合适");
    await user.click(screen.getByRole("button", { name: "继续处理" }));

    await waitFor(() => {
      const post = vi
        .mocked(api)
        .mock.calls.find(
          ([path, options]) => path === "/chat/messages" && options?.method === "POST",
        );
      expect(post).toBeDefined();
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
        content: "ORD-399，商品不合适",
        request_id: "request-uuid",
        ticket_id: waitingTicket.id,
      });
    });
  });

  it("uses low-frequency approval polling and stops for terminal states", () => {
    expect(pollDelayForStatus("RUNNING")).toBe(1_800);
    expect(pollDelayForStatus("WAITING_APPROVAL")).toBe(10_000);
    expect(pollDelayForStatus("WAITING_USER")).toBeNull();
    expect(pollDelayForStatus("COMPLETED")).toBeNull();
  });

  it("only adds ticket_id when answering an interrupted ticket", () => {
    expect(buildChatPayload("补充内容", waitingTicket)).toMatchObject({
      ticket_id: waitingTicket.id,
    });
    expect(buildChatPayload("新申请", { ...waitingTicket, status: "COMPLETED" })).not.toHaveProperty(
      "ticket_id",
    );
  });
});
