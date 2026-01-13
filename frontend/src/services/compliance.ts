import type {
  ComplianceAuditExportResponse,
  ApprovalSummaryResponse,
  PolicyViolationResponse,
  RoleAuditResponse,
  ComplianceFilters,
} from '../types/compliance';

const RAW_API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

if (import.meta.env.PROD && !RAW_API_BASE_URL.startsWith('https://')) {
  throw new Error(
    'Insecure API base URL configuration: HTTPS is required in production. ' +
      'Set VITE_API_BASE_URL to an https:// URL.'
  );
}

const API_BASE_URL = RAW_API_BASE_URL;

class ApiError extends Error {
  status: number;
  data?: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      credentials: 'include',
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData
      );
    }

    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      error instanceof Error ? error.message : 'Network error',
      0
    );
  }
}

export const complianceApi = {
  async getAuditExport(filters?: ComplianceFilters): Promise<ComplianceAuditExportResponse> {
    const params = new URLSearchParams();
    
    if (filters?.date_from) {
      params.append('date_from', filters.date_from);
    }
    if (filters?.date_to) {
      params.append('date_to', filters.date_to);
    }
    if (filters?.device_id) {
      params.append('device_id', filters.device_id);
    }
    if (filters?.tool_name) {
      params.append('tool_name', filters.tool_name);
    }
    if (filters?.user_id) {
      params.append('user_id', filters.user_id);
    }
    if (filters?.limit) {
      params.append('limit', filters.limit.toString());
    }
    
    params.append('format', 'json');
    
    const queryString = params.toString();
    const endpoint = `/api/compliance/audit-export${queryString ? `?${queryString}` : ''}`;
    
    return await fetchApi<ComplianceAuditExportResponse>(endpoint);
  },

  async exportAuditToCsv(filters?: ComplianceFilters): Promise<Blob> {
    const params = new URLSearchParams();
    
    if (filters?.date_from) {
      params.append('date_from', filters.date_from);
    }
    if (filters?.date_to) {
      params.append('date_to', filters.date_to);
    }
    if (filters?.device_id) {
      params.append('device_id', filters.device_id);
    }
    if (filters?.tool_name) {
      params.append('tool_name', filters.tool_name);
    }
    if (filters?.user_id) {
      params.append('user_id', filters.user_id);
    }
    if (filters?.limit) {
      params.append('limit', filters.limit.toString());
    }
    
    params.append('format', 'csv');
    
    const queryString = params.toString();
    const endpoint = `/api/compliance/audit-export${queryString ? `?${queryString}` : ''}`;
    const url = `${API_BASE_URL}${endpoint}`;
    
    const response = await fetch(url, {
      credentials: 'include',
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData
      );
    }
    
    return await response.blob();
  },

  async getApprovalSummary(filters?: ComplianceFilters): Promise<ApprovalSummaryResponse> {
    const params = new URLSearchParams();
    
    if (filters?.status) {
      params.append('status', filters.status);
    }
    if (filters?.date_from) {
      params.append('date_from', filters.date_from);
    }
    if (filters?.limit) {
      params.append('limit', filters.limit.toString());
    }
    if (filters?.offset) {
      params.append('offset', filters.offset.toString());
    }
    
    const queryString = params.toString();
    const endpoint = `/api/compliance/approvals${queryString ? `?${queryString}` : ''}`;
    
    return await fetchApi<ApprovalSummaryResponse>(endpoint);
  },

  async getPolicyViolations(filters?: ComplianceFilters): Promise<PolicyViolationResponse> {
    const params = new URLSearchParams();
    
    if (filters?.device_id) {
      params.append('device_id', filters.device_id);
    }
    if (filters?.date_from) {
      params.append('date_from', filters.date_from);
    }
    if (filters?.date_to) {
      params.append('date_to', filters.date_to);
    }
    if (filters?.limit) {
      params.append('limit', filters.limit.toString());
    }
    
    const queryString = params.toString();
    const endpoint = `/api/compliance/policy-violations${queryString ? `?${queryString}` : ''}`;
    
    return await fetchApi<PolicyViolationResponse>(endpoint);
  },

  async getRoleAudit(filters?: ComplianceFilters): Promise<RoleAuditResponse> {
    const params = new URLSearchParams();
    
    if (filters?.user_id) {
      params.append('user_id', filters.user_id);
    }
    if (filters?.date_from) {
      params.append('date_from', filters.date_from);
    }
    if (filters?.date_to) {
      params.append('date_to', filters.date_to);
    }
    if (filters?.limit) {
      params.append('limit', filters.limit.toString());
    }
    
    const queryString = params.toString();
    const endpoint = `/api/compliance/role-audit${queryString ? `?${queryString}` : ''}`;
    
    return await fetchApi<RoleAuditResponse>(endpoint);
  },
};

export { ApiError };
