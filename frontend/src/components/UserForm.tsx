import { useState, useEffect } from 'react';
import type { User, UserCreateRequest, UserUpdateRequest, Role } from '../types/user';

interface UserFormProps {
  user?: User;
  roles: Role[];
  devices: Array<{ id: string; name: string }>;
  onSubmit: (data: UserCreateRequest | UserUpdateRequest) => Promise<void>;
  onCancel: () => void;
}

export default function UserForm({ user, roles, devices, onSubmit, onCancel }: UserFormProps) {
  const [formData, setFormData] = useState({
    sub: user?.sub || '',
    email: user?.email || '',
    display_name: user?.display_name || '',
    role_name: user?.role_name || '',
    device_scopes: user?.device_scopes || [] as string[],
    is_active: user?.is_active ?? true,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deviceScopesMode, setDeviceScopesMode] = useState<'all' | 'specific'>(
    user?.device_scopes && user.device_scopes.length > 0 ? 'specific' : 'all'
  );

  useEffect(() => {
    if (user) {
      setFormData({
        sub: user.sub,
        email: user.email || '',
        display_name: user.display_name || '',
        role_name: user.role_name,
        device_scopes: user.device_scopes || [],
        is_active: user.is_active,
      });
      setDeviceScopesMode(user.device_scopes && user.device_scopes.length > 0 ? 'specific' : 'all');
    }
  }, [user]);

  const validate = () => {
    const newErrors: Record<string, string> = {};

    if (!user) {
      // Creating new user - sub is required
      if (!formData.sub.trim()) {
        newErrors.sub = 'User ID (sub) is required';
      }
    }

    if (!formData.role_name) {
      newErrors.role_name = 'Role is required';
    }

    if (deviceScopesMode === 'specific' && formData.device_scopes.length === 0) {
      newErrors.device_scopes = 'Select at least one device or choose "All Devices"';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) {
      return;
    }

    setIsSubmitting(true);
    try {
      const submitData: UserCreateRequest | UserUpdateRequest = user
        ? {
            // Update mode - only send changed fields
            email: formData.email !== user.email ? formData.email : undefined,
            display_name: formData.display_name !== user.display_name ? formData.display_name : undefined,
            role_name: formData.role_name !== user.role_name ? formData.role_name : undefined,
            device_scopes: deviceScopesMode === 'all' ? [] : formData.device_scopes,
            is_active: formData.is_active !== user.is_active ? formData.is_active : undefined,
          }
        : {
            // Create mode
            sub: formData.sub,
            email: formData.email || undefined,
            display_name: formData.display_name || undefined,
            role_name: formData.role_name,
            device_scopes: deviceScopesMode === 'all' ? [] : formData.device_scopes,
            is_active: formData.is_active,
          };

      await onSubmit(submitData);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeviceScopeToggle = (deviceId: string) => {
    setFormData((prev) => ({
      ...prev,
      device_scopes: prev.device_scopes.includes(deviceId)
        ? prev.device_scopes.filter((id) => id !== deviceId)
        : [...prev.device_scopes, deviceId],
    }));
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-y-auto">
      <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-2xl my-8 mx-4">
        <h2 className="text-2xl font-bold text-gray-800 mb-4">
          {user ? 'Edit User' : 'Add New User'}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          {!user && (
            <div>
              <label htmlFor="sub" className="block text-sm font-medium text-gray-700 mb-1">
                User ID (OIDC Subject) *
              </label>
              <input
                type="text"
                id="sub"
                value={formData.sub}
                onChange={(e) => setFormData({ ...formData, sub: e.target.value })}
                className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                  errors.sub ? 'border-red-500' : 'border-gray-300'
                }`}
                placeholder="auth0|123456789"
              />
              {errors.sub && <p className="text-red-500 text-sm mt-1">{errors.sub}</p>}
              <p className="text-sm text-gray-500 mt-1">
                Unique identifier from OIDC provider (e.g., auth0|123456789)
              </p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                Email
              </label>
              <input
                type="email"
                id="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="user@example.com"
              />
            </div>

            <div>
              <label htmlFor="display_name" className="block text-sm font-medium text-gray-700 mb-1">
                Display Name
              </label>
              <input
                type="text"
                id="display_name"
                value={formData.display_name}
                onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="John Doe"
              />
            </div>
          </div>

          <div>
            <label htmlFor="role_name" className="block text-sm font-medium text-gray-700 mb-1">
              Role *
            </label>
            <select
              id="role_name"
              value={formData.role_name}
              onChange={(e) => setFormData({ ...formData, role_name: e.target.value })}
              className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                errors.role_name ? 'border-red-500' : 'border-gray-300'
              }`}
            >
              <option value="">Select a role...</option>
              {roles.map((role) => (
                <option key={role.id} value={role.name}>
                  {role.name} - {role.description}
                </option>
              ))}
            </select>
            {errors.role_name && <p className="text-red-500 text-sm mt-1">{errors.role_name}</p>}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Device Access
            </label>
            <div className="space-y-2">
              <label className="flex items-center">
                <input
                  type="radio"
                  name="device_scopes_mode"
                  checked={deviceScopesMode === 'all'}
                  onChange={() => {
                    setDeviceScopesMode('all');
                    setFormData({ ...formData, device_scopes: [] });
                  }}
                  className="mr-2"
                />
                <span className="text-sm text-gray-700">All Devices (Full Access)</span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="device_scopes_mode"
                  checked={deviceScopesMode === 'specific'}
                  onChange={() => setDeviceScopesMode('specific')}
                  className="mr-2"
                />
                <span className="text-sm text-gray-700">Specific Devices Only</span>
              </label>
            </div>

            {deviceScopesMode === 'specific' && (
              <div className="mt-3 border border-gray-300 rounded-md p-3 max-h-48 overflow-y-auto">
                {devices.length === 0 ? (
                  <p className="text-sm text-gray-500">No devices available</p>
                ) : (
                  <div className="space-y-2">
                    {devices.map((device) => (
                      <label key={device.id} className="flex items-center">
                        <input
                          type="checkbox"
                          checked={formData.device_scopes.includes(device.id)}
                          onChange={() => handleDeviceScopeToggle(device.id)}
                          className="mr-2"
                        />
                        <span className="text-sm text-gray-700">{device.name} ({device.id})</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}
            {errors.device_scopes && (
              <p className="text-red-500 text-sm mt-1">{errors.device_scopes}</p>
            )}
          </div>

          <div>
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                className="mr-2"
              />
              <span className="text-sm font-medium text-gray-700">Active</span>
            </label>
            <p className="text-sm text-gray-500 ml-6">
              Inactive users cannot log in or perform any actions
            </p>
          </div>

          <div className="flex justify-end space-x-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-gray-700 bg-gray-200 rounded-md hover:bg-gray-300 transition-colors"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Saving...' : user ? 'Update User' : 'Create User'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
