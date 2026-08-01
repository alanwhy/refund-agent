import type { Ticket } from "../types";

export function pollDelayForStatus(status: string): number | null {
  if (status === "WAITING_APPROVAL") return 10_000;
  if (status === "CREATED" || status === "RUNNING") return 1_800;
  return null;
}

export function buildChatPayload(content: string, ticket: Ticket | null) {
  return {
    content,
    request_id: crypto.randomUUID(),
    ...(ticket?.status === "WAITING_USER" ? { ticket_id: ticket.id } : {}),
  };
}
