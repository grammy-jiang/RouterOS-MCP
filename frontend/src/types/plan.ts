export type PlanStatus = 
  | 'pending' 
  | 'approved' 
  | 'executing' 
  | 'completed' 
  | 'failed' 
  | 'cancelled'
  | 'rolling_back'
  | 'rolled_back';

export interface Plan {
  id: string;
  created_by: string;
  tool_name: string;
  status: PlanStatus;
  summary: string;
  device_ids: string[];
  /**
   * The proposed configuration changes for this plan.
   * Structure varies by change type (tool_name).
   * Only included in detailed plan responses, not in list responses.
   */
  changes?: Record<string, unknown>;
  created_at: string;
  approved_by?: string | null;
  approved_at?: string | null;
  approval_token?: string | null;
  approval_token_expires_at?: string | null;
}

export interface PlanListResponse {
  plans: Plan[];
}

export interface PlanApproveResponse {
  message: string;
  plan_id: string;
  approval_token: string;
  expires_at: string;
}

export interface PlanRejectRequest {
  reason: string;
}

export interface PlanRejectResponse {
  message: string;
  plan_id: string;
  reason: string;
}
