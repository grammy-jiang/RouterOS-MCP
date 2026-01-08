import { useState, useEffect } from 'react';
import type { Device, DeviceCreateRequest, DeviceUpdateRequest, Environment } from '../types/device';

interface DeviceFormProps {
  device?: Device;
  onSubmit: (data: DeviceCreateRequest | DeviceUpdateRequest) => Promise<void>;
  onCancel: () => void;
}

export default function DeviceForm({ device, onSubmit, onCancel }: DeviceFormProps) {
  const [formData, setFormData] = useState({
    name: device?.name || '',
    hostname: device?.management_ip || '',
    username: '',
    password: '',
    environment: (device?.environment || 'lab') as Environment,
    port: device?.management_port || 443,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (device) {
      setFormData({
        name: device.name,
        hostname: device.management_ip,
        username: '',
        password: '',
        environment: device.environment,
        port: device.management_port,
      });
    }
  }, [device]);

  const validate = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.name.trim()) {
      newErrors.name = 'Device name is required';
    }

    if (!formData.hostname.trim()) {
      newErrors.hostname = 'Hostname is required';
    }

    if (!device) {
      // Username and password are required for new devices
      if (!formData.username.trim()) {
        newErrors.username = 'Username is required';
      }

      if (!formData.password) {
        newErrors.password = 'Password is required';
      }
    }

    if (formData.port < 1 || formData.port > 65535) {
      newErrors.port = 'Port must be between 1 and 65535';
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
      if (device) {
        // Update mode - only send changed fields
        const updateData: DeviceUpdateRequest = {
          name: formData.name !== device.name ? formData.name : undefined,
          hostname: formData.hostname !== device.management_ip ? formData.hostname : undefined,
          port: formData.port !== device.management_port ? formData.port : undefined,
        };
        
        // Only include credentials if they were provided
        if (formData.username && formData.password) {
          updateData.username = formData.username;
          updateData.password = formData.password;
        }
        
        await onSubmit(updateData);
      } else {
        // Create mode - send all fields
        await onSubmit(formData as DeviceCreateRequest);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
        <h2 className="text-2xl font-bold text-gray-800 mb-4">
          {device ? 'Edit Device' : 'Add New Device'}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
              Device Name *
            </label>
            <input
              type="text"
              id="name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                errors.name ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="router-lab-01"
            />
            {errors.name && <p className="text-red-500 text-sm mt-1">{errors.name}</p>}
          </div>

          <div>
            <label htmlFor="hostname" className="block text-sm font-medium text-gray-700 mb-1">
              Hostname / IP Address *
            </label>
            <input
              type="text"
              id="hostname"
              value={formData.hostname}
              onChange={(e) => setFormData({ ...formData, hostname: e.target.value })}
              className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                errors.hostname ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="192.168.1.1"
            />
            {errors.hostname && <p className="text-red-500 text-sm mt-1">{errors.hostname}</p>}
          </div>

          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">
              Username {!device && '*'}
            </label>
            <input
              type="text"
              id="username"
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                errors.username ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder="admin"
            />
            {errors.username && <p className="text-red-500 text-sm mt-1">{errors.username}</p>}
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
              Password {!device && '*'}
            </label>
            <input
              type="password"
              id="password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                errors.password ? 'border-red-500' : 'border-gray-300'
              }`}
              placeholder={device ? 'Leave empty to keep existing' : ''}
            />
            {errors.password && <p className="text-red-500 text-sm mt-1">{errors.password}</p>}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="environment" className="block text-sm font-medium text-gray-700 mb-1">
                Environment *
              </label>
              <select
                id="environment"
                value={formData.environment}
                onChange={(e) => setFormData({ ...formData, environment: e.target.value as Environment })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="lab">Lab</option>
                <option value="staging">Staging</option>
                <option value="prod">Production</option>
              </select>
            </div>

            <div>
              <label htmlFor="port" className="block text-sm font-medium text-gray-700 mb-1">
                Port
              </label>
              <input
                type="number"
                id="port"
                value={formData.port}
                onChange={(e) => setFormData({ ...formData, port: parseInt(e.target.value) || 443 })}
                className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                  errors.port ? 'border-red-500' : 'border-gray-300'
                }`}
                min="1"
                max="65535"
              />
              {errors.port && <p className="text-red-500 text-sm mt-1">{errors.port}</p>}
            </div>
          </div>

          <div className="flex justify-end space-x-3 pt-4">
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
              {isSubmitting ? 'Saving...' : device ? 'Update Device' : 'Add Device'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
