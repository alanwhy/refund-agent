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

export interface PolicyEvidence {
  document_id: string;
  title: string;
  version: string;
  excerpt: string;
}

export interface ChatAccepted {
  ticket_id: string;
  conversation_id: string;
  status: string;
  waiting_for: string | null;
  status_url: string;
}

export interface Ticket {
  id: string;
  conversation_id?: string;
  status: string;
  current_step: string;
  waiting_for: string | null;
  current_question: string | null;
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
  policy_evidence?: PolicyEvidence[];
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

export interface OrderView {
  id: string;
  order_number: string;
  product_name: string;
  amount: string;
  status: string;
  delivered_at: string;
  customer_id: string | null;
  customer_name: string | null;
  ticket_id: string | null;
  ticket_status: string | null;
  approval_id: string | null;
  approval_status: string | null;
  approval_assigned_to: string | null;
  risk_reasons: string[] | null;
  manual_review_id: string | null;
  manual_review_category: string | null;
}

export interface ManualReviewTask {
  id: string;
  ticket_id: string;
  status: "PENDING" | "RESOLVED" | "UNRESOLVABLE";
  category:
    | "MODEL_FAILURE"
    | "PAYMENT_UNKNOWN"
    | "DATA_INCONSISTENCY"
    | "SECURITY_REJECTION";
  version: number;
  submitted_order_number: string | null;
  technical_summary: string;
  assigned_to: string | null;
  assigned_name: string | null;
  resolution_note: string | null;
  resolved_by: string | null;
  customer_name: string;
  order_id: string | null;
  order_number: string | null;
  product_name: string | null;
  ticket_status: string;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}
