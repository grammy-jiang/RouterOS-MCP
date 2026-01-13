export interface ComplianceAuditEvent {
  id: string;
  timestamp: string;
  user_sub: string;
  user_email: string | null;
  user_role: string;
  user_id: string | null;
  approver_id: string | null;
  approval_request_id: string | null;
  device_id: string | null;
  environment: string | null;
  action: string;
  tool_name: string;
  tool_tier: string;
  plan_id: string | null;
  job_id: string | null;
  result: string;
  error_message: string | null;
}

export interface ComplianceAuditExportResponse {
  events: ComplianceAuditEvent[];
  count: number;
  filters: {
    date_from: string | null;
    date_to: string | null;
    device_id: string | null;
    tool_name: string | null;
    user_id: string | null;
  };
}

export interface ApprovalDecision {
  id: string;
  plan_id: string;
  requested_by: string;
  requested_at: string;
  status: 'approved' | 'rejected' | 'pending';
  approved_by: string | null;
  approved_at: string | null;
  rejected_by: string | null;
  rejected_at: string | null;
  notes: string | null;
}

export interface ApprovalStatistics {
  approved: number;
  rejected: number;
  pending: number;
}

export interface ApprovalSummaryResponse {
  decisions: ApprovalDecision[];
  total: number;
  limit: number;
  offset: number;
  statistics: ApprovalStatistics;
  filters: {
    status: string | null;
    date_from: string | null;
  };
}

export interface PolicyViolation {
  id: string;
  timestamp: string;
  user_sub: string;
  user_email: string | null;
  user_role: string;
  user_id: string | null;
  device_id: string | null;
  environment: string | null;
  tool_name: string;
  tool_tier: string;
  error_message: string | null;
}

export interface PolicyViolationResponse {
  violations: PolicyViolation[];
  total: number;
  limit: number;
  statistics: {
    total_violations: number;
    by_device: Record<string, number>;
  };
  filters: {
    device_id: string | null;
    date_from: string | null;
    date_to: string | null;
  };
}

export interface RoleHistoryEntry {
  timestamp: string;
  user_sub: string;
  user_email: string | null;
  user_role: string;
  action: string;
  tool_name: string;
}

export interface RoleAuditResponse {
  role_history: Record<string, RoleHistoryEntry[]>;
  total_events: number;
  limit: number;
  filters: {
    user_id: string | null;
    date_from: string | null;
    date_to: string | null;
  };
}

export interface ComplianceFilters {
  date_from?: string;
  date_to?: string;
  device_id?: string;
  tool_name?: string;
  user_id?: string;
  status?: 'approved' | 'rejected' | 'pending';
  limit?: number;
  offset?: number;
}
