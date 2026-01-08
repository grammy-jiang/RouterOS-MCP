export interface AuditEvent {
  id: string;
  timestamp: string;
  user_sub: string;
  user_email: string | null;
  user_role: string;
  device_id: string | null;
  environment: string | null;
  action: string;
  tool_name: string;
  tool_tier: string;
  success: boolean;
  error_message: string | null;
  parameters: Record<string, unknown> | null;
  result_summary: string | null;
  correlation_id: string | null;
}

export interface AuditEventsResponse {
  events: AuditEvent[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AuditEventsFilter {
  page?: number;
  page_size?: number;
  device_id?: string;
  tool_name?: string;
  success?: boolean;
  date_from?: string;
  date_to?: string;
  search?: string;
}
