import type {
  Device,
  DeviceCreateRequest,
  DeviceUpdateRequest,
  DeviceListResponse,
  DeviceResponse,
  ConnectivityTestResponse,
} from '../types/device';
import type {
  AuditEventsResponse,
  AuditEventsFilter,
} from '../types/audit';
import type {
  Plan,
  PlanListResponse,
  PlanApproveResponse,
  PlanRejectRequest,
  PlanRejectResponse,
} from '../types/plan';

const RAW_API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

if (import.meta.env.PROD && !RAW_API_BASE_URL.startsWith('https://')) {
  // In production, require HTTPS to avoid sending credentials over plain HTTP.
  // Configure VITE_API_BASE_URL accordingly in the deployment environment.
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
      credentials: 'include', // Include cookies for authentication
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

export const deviceApi = {
  async list(): Promise<Device[]> {
    const response = await fetchApi<DeviceListResponse>('/api/devices');
    return response.devices;
  },

  async create(data: DeviceCreateRequest): Promise<Device> {
    const response = await fetchApi<DeviceResponse>('/api/admin/devices', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return response.device;
  },

  async update(id: string, data: DeviceUpdateRequest): Promise<Device> {
    const response = await fetchApi<DeviceResponse>(`/api/admin/devices/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
    return response.device;
  },

  async delete(id: string): Promise<void> {
    await fetchApi<{ message: string }>(`/api/admin/devices/${id}`, {
      method: 'DELETE',
    });
  },

  async testConnectivity(id: string): Promise<ConnectivityTestResponse> {
    return await fetchApi<ConnectivityTestResponse>(`/api/admin/devices/${id}/test`, {
      method: 'POST',
    });
  },
};

export const auditApi = {
  async listEvents(filter?: AuditEventsFilter): Promise<AuditEventsResponse> {
    const params = new URLSearchParams();
    
    if (filter?.page !== undefined) {
      params.append('page', filter.page.toString());
    }
    if (filter?.page_size !== undefined) {
      params.append('page_size', filter.page_size.toString());
    }
    if (filter?.device_id) {
      params.append('device_id', filter.device_id);
    }
    if (filter?.tool_name) {
      params.append('tool_name', filter.tool_name);
    }
    if (filter?.success !== undefined) {
      params.append('success', filter.success.toString());
    }
    if (filter?.date_from) {
      params.append('date_from', filter.date_from);
    }
    if (filter?.date_to) {
      params.append('date_to', filter.date_to);
    }
    if (filter?.search) {
      params.append('search', filter.search);
    }
    
    const queryString = params.toString();
    const endpoint = `/api/audit/events${queryString ? `?${queryString}` : ''}`;
    
    return await fetchApi<AuditEventsResponse>(endpoint);
  },

  async exportToCsv(filter?: AuditEventsFilter): Promise<Blob> {
    const params = new URLSearchParams();
    
    if (filter?.device_id) {
      params.append('device_id', filter.device_id);
    }
    if (filter?.tool_name) {
      params.append('tool_name', filter.tool_name);
    }
    if (filter?.success !== undefined) {
      params.append('success', filter.success.toString());
    }
    if (filter?.date_from) {
      params.append('date_from', filter.date_from);
    }
    if (filter?.date_to) {
      params.append('date_to', filter.date_to);
    }
    if (filter?.search) {
      params.append('search', filter.search);
    }
    
    const queryString = params.toString();
    const endpoint = `/api/audit/events/export${queryString ? `?${queryString}` : ''}`;
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

  async getFilters(): Promise<{ devices: string[]; tools: string[] }> {
    return await fetchApi<{ devices: string[]; tools: string[] }>('/api/audit/filters');
  },
};

export const planApi = {
  async list(statusFilter?: string): Promise<Plan[]> {
    const params = new URLSearchParams();
    if (statusFilter) {
      params.append('status_filter', statusFilter);
    }
    
    const queryString = params.toString();
    const endpoint = `/admin/api/plans${queryString ? `?${queryString}` : ''}`;
    
    const response = await fetchApi<PlanListResponse>(endpoint);
    return response.plans;
  },

  async getDetail(planId: string): Promise<Plan> {
    return await fetchApi<Plan>(`/admin/api/plans/${planId}`);
  },

  async approve(planId: string): Promise<PlanApproveResponse> {
    return await fetchApi<PlanApproveResponse>(`/admin/api/plans/${planId}/approve`, {
      method: 'POST',
    });
  },

  async reject(planId: string, reason: string): Promise<PlanRejectResponse> {
    const data: PlanRejectRequest = { reason };
    return await fetchApi<PlanRejectResponse>(`/admin/api/plans/${planId}/reject`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};

export const userApi = {
  async list(filters?: { is_active?: boolean; role_name?: string }): Promise<import('../types/user').User[]> {
    const params = new URLSearchParams();
    
    if (filters?.is_active !== undefined) {
      params.append('is_active', filters.is_active.toString());
    }
    if (filters?.role_name) {
      params.append('role_name', filters.role_name);
    }
    
    const queryString = params.toString();
    const endpoint = `/api/admin/users${queryString ? `?${queryString}` : ''}`;
    
    const response = await fetchApi<import('../types/user').UserListResponse>(endpoint);
    return response.users;
  },

  async create(data: import('../types/user').UserCreateRequest): Promise<import('../types/user').User> {
    const response = await fetchApi<import('../types/user').UserResponse>('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return response.user;
  },

  async update(sub: string, data: import('../types/user').UserUpdateRequest): Promise<import('../types/user').User> {
    const response = await fetchApi<import('../types/user').UserResponse>(`/api/admin/users/${sub}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
    return response.user;
  },

  async delete(sub: string): Promise<void> {
    await fetchApi<{ message: string }>(`/api/admin/users/${sub}`, {
      method: 'DELETE',
    });
  },

  async updateDeviceScopes(sub: string, deviceScopes: string[]): Promise<import('../types/user').User> {
    const response = await fetchApi<import('../types/user').UserResponse>(
      `/api/admin/users/${sub}/device-scopes`,
      {
        method: 'PUT',
        body: JSON.stringify({ device_scopes: deviceScopes }),
      }
    );
    return response.user;
  },

  async listRoles(): Promise<import('../types/user').Role[]> {
    const response = await fetchApi<import('../types/user').RoleListResponse>('/api/admin/roles');
    return response.roles;
  },
};

export { ApiError };
