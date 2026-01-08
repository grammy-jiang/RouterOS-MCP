import { useState, useEffect } from 'react';
import { deviceApi, ApiError } from '../services/api';
import DeviceForm from '../components/DeviceForm';
import type { Device, DeviceCreateRequest, DeviceUpdateRequest, DeviceStatus } from '../types/device';

export default function Devices() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingDevice, setEditingDevice] = useState<Device | undefined>(undefined);
  const [deletingDevice, setDeletingDevice] = useState<Device | null>(null);
  const [testingDeviceId, setTestingDeviceId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ deviceId: string; message: string; success: boolean } | null>(null);

  useEffect(() => {
    loadDevices();
  }, []);

  const loadDevices = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await deviceApi.list();
      setDevices(data);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to load devices';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleAddDevice = async (data: DeviceCreateRequest | DeviceUpdateRequest) => {
    try {
      setOperationError(null);
      await deviceApi.create(data as DeviceCreateRequest);
      setShowForm(false);
      await loadDevices();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to create device';
      setOperationError(message);
      throw err;
    }
  };

  const handleEditDevice = async (data: DeviceCreateRequest | DeviceUpdateRequest) => {
    if (!editingDevice) return;

    try {
      setOperationError(null);
      await deviceApi.update(editingDevice.id, data as DeviceUpdateRequest);
      setEditingDevice(undefined);
      setShowForm(false);
      await loadDevices();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to update device';
      setOperationError(message);
      throw err;
    }
  };

  const handleDeleteDevice = async () => {
    if (!deletingDevice) return;

    try {
      setOperationError(null);
      await deviceApi.delete(deletingDevice.id);
      setDeletingDevice(null);
      await loadDevices();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to delete device';
      setOperationError(message);
    }
  };

  const handleTestConnectivity = async (device: Device) => {
    setTestingDeviceId(device.id);
    setTestResult(null);  // Clear previous test result

    try {
      const result = await deviceApi.testConnectivity(device.id);
      setTestResult({
        deviceId: device.id,
        message: result.message,
        success: result.reachable,
      });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to test connectivity';
      setTestResult({
        deviceId: device.id,
        message: `Error: ${message}`,
        success: false,
      });
    } finally {
      setTestingDeviceId(null);
    }
  };

  const openEditForm = (device: Device) => {
    setEditingDevice(device);
    setShowForm(true);
  };

  const openAddForm = () => {
    setEditingDevice(undefined);
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingDevice(undefined);
  };

  const getStatusColor = (status: DeviceStatus): string => {
    if (status === 'online' || status === 'healthy') return 'bg-green-500';
    if (status === 'degraded') return 'bg-yellow-500';
    return 'bg-red-500';
  };

  const getStatusLabel = (status: DeviceStatus): string => {
    if (status === 'online' || status === 'healthy') return 'Healthy';
    if (status === 'degraded') return 'Degraded';
    if (status === 'offline' || status === 'unreachable') return 'Unreachable';
    return status.charAt(0).toUpperCase() + status.slice(1);
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800">Devices</h1>
        <button
          onClick={openAddForm}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          Add Device
        </button>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded-md flex items-start justify-between">
          <p>{error}</p>
          <button
            type="button"
            onClick={() => setError(null)}
            className="ml-4 text-sm text-red-600 hover:text-red-800"
          >
            Dismiss
          </button>
        </div>
      )}

      {operationError && (
        <div className="mb-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded-md flex items-start justify-between">
          <p>{operationError}</p>
          <button
            type="button"
            onClick={() => setOperationError(null)}
            className="ml-4 text-sm text-red-600 hover:text-red-800"
          >
            Dismiss
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-center py-8">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
          <p className="mt-2 text-gray-600">Loading devices...</p>
        </div>
      ) : devices.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-600 text-lg mb-4">No devices found. Add your first device.</p>
          <button
            onClick={openAddForm}
            className="px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            Add Device
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Device Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Hostname
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Environment
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {devices.map((device) => (
                <tr key={device.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {device.name}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                    {device.management_ip}:{device.management_port}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="px-2 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800">
                      {device.environment}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <div className={`w-3 h-3 rounded-full ${getStatusColor(device.status)} mr-2`}></div>
                      <span className="text-sm text-gray-900">{getStatusLabel(device.status)}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                    <button
                      onClick={() => handleTestConnectivity(device)}
                      disabled={testingDeviceId === device.id}
                      className="text-blue-600 hover:text-blue-800 disabled:text-gray-400"
                    >
                      {testingDeviceId === device.id ? (
                        <span className="inline-flex items-center">
                          <span className="inline-block animate-spin rounded-full h-3 w-3 border-b-2 border-blue-600 mr-1"></span>
                          Testing...
                        </span>
                      ) : (
                        'Test'
                      )}
                    </button>
                    <button
                      onClick={() => openEditForm(device)}
                      className="text-green-600 hover:text-green-800"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => setDeletingDevice(device)}
                      className="text-red-600 hover:text-red-800"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {testResult && (
        <div
          className={`mt-4 p-4 rounded-md flex items-start justify-between ${
            testResult.success
              ? 'bg-green-100 border border-green-400'
              : 'bg-red-100 border border-red-400'
          }`}
        >
          <p className={testResult.success ? 'text-green-700' : 'text-red-700'}>
            {testResult.message}
          </p>
          <button
            type="button"
            onClick={() => setTestResult(null)}
            className={`ml-4 text-sm ${
              testResult.success ? 'text-green-600 hover:text-green-800' : 'text-red-600 hover:text-red-800'
            }`}
          >
            Dismiss
          </button>
        </div>
      )}

      {showForm && (
        <DeviceForm
          device={editingDevice}
          onSubmit={editingDevice ? handleEditDevice : handleAddDevice}
          onCancel={closeForm}
        />
      )}

      {deletingDevice && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
            <h2 className="text-xl font-bold text-gray-800 mb-4">Confirm Delete</h2>
            <p className="text-gray-600 mb-6">
              Are you sure you want to delete <strong>{deletingDevice.name}</strong>?
            </p>
            <div className="flex justify-end space-x-3">
              <button
                onClick={() => setDeletingDevice(null)}
                className="px-4 py-2 text-gray-700 bg-gray-200 rounded-md hover:bg-gray-300 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteDevice}
                className="px-4 py-2 text-white bg-red-600 rounded-md hover:bg-red-700 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
