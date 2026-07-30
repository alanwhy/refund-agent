export type Role = "CUSTOMER" | "APPROVER" | "ADMIN";

export interface User {
  id: string;
  email: string;
  role: Role;
  display_name: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Message {
  id: string;
  sender: "USER" | "ASSISTANT";
  content: string;
  created_at: string;
}

export interface Ticket {
  id: string;
  conversation_id?: string;
  status: string;
  current_step: string;
  intent: string | null;
  order_number: string | null;
  product_name: string | null;
  calculated_amount: string | null;
  requested_amount?: string | null;
  approved_amount?: string | null;
  risk_level: string | null;
  risk_reasons?: string[];
  matched_rule_ids?: string[];
  refund_status?: string | null;
  payment_reference?: string | null;
  approval_status?: string | null;
  messages?: Message[];
  created_at: string;
}

export interface Approval {
  id: string;
  ticket_id: string;
  status: string;
  version: number;
  risk_reasons: string[];
  suggested_amount: string;
  approved_amount: string | null;
  assigned_to: string | null;
  order_number: string | null;
  product_name: string | null;
  customer_name: string;
  expires_at: string;
  created_at: string;
}

export interface AuditEvent {
  id: string;
  ticket_id: string | null;
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  details: Record<string, unknown>;
  trace_id: string;
  created_at: string;
}
