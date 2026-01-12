export interface User {
  sub: string;
  email: string | null;
  display_name: string | null;
  role_name: string;
  role_description: string | null;
  device_scopes: string[];
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Role {
  id: string;
  name: string;
  description: string;
}

export interface UserCreateRequest {
  sub: string;
  email?: string;
  display_name?: string;
  role_name: string;
  device_scopes?: string[];
  is_active?: boolean;
}

export interface UserUpdateRequest {
  email?: string;
  display_name?: string;
  role_name?: string;
  device_scopes?: string[];
  is_active?: boolean;
}

export interface DeviceScopesUpdateRequest {
  device_scopes: string[];
}

export interface UserListResponse {
  users: User[];
}

export interface UserResponse {
  message: string;
  user: User;
}

export interface RoleListResponse {
  roles: Role[];
}
