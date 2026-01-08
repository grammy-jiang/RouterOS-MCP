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

export { ApiError };
