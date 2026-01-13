import type {
  ComplianceAuditExportResponse,
  ApprovalSummaryResponse,
  PolicyViolationResponse,
  RoleAuditResponse,
  ComplianceFilters,
} from '../types/compliance';
import { ApiError } from './api';

const RAW_API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

if (import.meta.env.PROD && !RAW_API_BASE_URL.startsWith('https://')) {
  throw new Error(
    'Insecure API base URL configuration: HTTPS is required in production. ' +
      'Set VITE_API_BASE_URL to an https:// URL.'
  );
}

const API_BASE_URL = RAW_API_BASE_URL;

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

/**
 * Build URL query parameters from filters object
 */
function buildQueryParams(
  filters: ComplianceFilters | undefined,
  keys: (keyof ComplianceFilters)[]
): string {
  const params = new URLSearchParams();

  for (const key of keys) {
    const value = filters?.[key];
    if (value !== undefined && value !== null) {
      params.append(key as string, String(value));
    }
  }

  return params.toString();
}

export const complianceApi = {
  async getAuditExport(filters?: ComplianceFilters): Promise<ComplianceAuditExportResponse> {
    const baseParams = buildQueryParams(filters, [
      'date_from',
      'date_to',
      'device_id',
      'tool_name',
      'user_id',
      'limit',
    ]);
    
    const params = new URLSearchParams(baseParams);
    params.append('format', 'json');
    
    const queryString = params.toString();
    const endpoint = `/api/compliance/audit-export${queryString ? `?${queryString}` : ''}`;
    
    return await fetchApi<ComplianceAuditExportResponse>(endpoint);
  },

  async exportAuditToCsv(filters?: ComplianceFilters): Promise<Blob> {
    const baseParams = buildQueryParams(filters, [
      'date_from',
      'date_to',
      'device_id',
      'tool_name',
      'user_id',
      'limit',
    ]);
    
    const params = new URLSearchParams(baseParams);
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
    const queryString = buildQueryParams(filters, [
      'status',
      'date_from',
      'limit',
      'offset',
    ]);
    const endpoint = `/api/compliance/approvals${queryString ? `?${queryString}` : ''}`;
    
    return await fetchApi<ApprovalSummaryResponse>(endpoint);
  },

  async getPolicyViolations(filters?: ComplianceFilters): Promise<PolicyViolationResponse> {
    const queryString = buildQueryParams(filters, [
      'device_id',
      'date_from',
      'date_to',
      'limit',
    ]);
    const endpoint = `/api/compliance/policy-violations${queryString ? `?${queryString}` : ''}`;
    
    return await fetchApi<PolicyViolationResponse>(endpoint);
  },

  async getRoleAudit(filters?: ComplianceFilters): Promise<RoleAuditResponse> {
    const queryString = buildQueryParams(filters, [
      'user_id',
      'date_from',
      'date_to',
      'limit',
    ]);
    const endpoint = `/api/compliance/role-audit${queryString ? `?${queryString}` : ''}`;
    
    return await fetchApi<RoleAuditResponse>(endpoint);
  },
};

export { ApiError };
