import { useState, useEffect } from 'react';
import { userApi, deviceApi, ApiError } from '../services/api';
import UserForm from '../components/UserForm';
import type { User, UserCreateRequest, UserUpdateRequest, Role } from '../types/user';
import type { Device } from '../types/device';

export default function AdminUsers() {
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingUser, setEditingUser] = useState<User | undefined>(undefined);
  const [deletingUser, setDeletingUser] = useState<User | null>(null);
  const [filterActive, setFilterActive] = useState<boolean | null>(null);
  const [filterRole, setFilterRole] = useState<string>('');

  useEffect(() => {
    loadData();
  }, [filterActive, filterRole]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [usersData, rolesData, devicesData] = await Promise.all([
        userApi.list({
          is_active: filterActive ?? undefined,
          role_name: filterRole || undefined,
        }),
        userApi.listRoles(),
        deviceApi.list(),
      ]);

      setUsers(usersData);
      setRoles(rolesData);
      setDevices(devicesData);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to load data';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleAddUser = async (data: UserCreateRequest | UserUpdateRequest) => {
    try {
      setOperationError(null);
      await userApi.create(data as UserCreateRequest);
      setShowForm(false);
      await loadData();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to create user';
      setOperationError(message);
      throw err;
    }
  };

  const handleEditUser = async (data: UserCreateRequest | UserUpdateRequest) => {
    if (!editingUser) return;

    try {
      setOperationError(null);
      await userApi.update(editingUser.sub, data as UserUpdateRequest);
      setEditingUser(undefined);
      setShowForm(false);
      await loadData();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to update user';
      setOperationError(message);
      throw err;
    }
  };

  const handleDeleteUser = async () => {
    if (!deletingUser) return;

    try {
      setOperationError(null);
      await userApi.delete(deletingUser.sub);
      setDeletingUser(null);
      await loadData();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to delete user';
      setOperationError(message);
    }
  };

  const openEditForm = (user: User) => {
    setEditingUser(user);
    setShowForm(true);
  };

  const openAddForm = () => {
    setEditingUser(undefined);
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingUser(undefined);
  };

  const getStatusBadge = (user: User) => {
    if (!user.is_active) {
      return <span className="px-2 py-1 text-xs font-medium rounded-full bg-gray-100 text-gray-800">Inactive</span>;
    }
    return <span className="px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800">Active</span>;
  };

  const getAccessBadge = (deviceScopes: string[]) => {
    if (deviceScopes.length === 0) {
      return <span className="px-2 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800">All Devices</span>;
    }
    return (
      <span className="px-2 py-1 text-xs font-medium rounded-full bg-yellow-100 text-yellow-800">
        {deviceScopes.length} Device{deviceScopes.length !== 1 ? 's' : ''}
      </span>
    );
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <h1 className="text-3xl font-bold text-gray-800">User Management</h1>
        <button
          onClick={openAddForm}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          Add User
        </button>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-col sm:flex-row gap-4">
        <div className="flex-1">
          <label htmlFor="filter-role" className="block text-sm font-medium text-gray-700 mb-1">
            Filter by Role
          </label>
          <select
            id="filter-role"
            value={filterRole}
            onChange={(e) => setFilterRole(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Roles</option>
            {roles.map((role) => (
              <option key={role.id} value={role.name}>
                {role.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label htmlFor="filter-active" className="block text-sm font-medium text-gray-700 mb-1">
            Filter by Status
          </label>
          <select
            id="filter-active"
            value={filterActive === null ? '' : filterActive.toString()}
            onChange={(e) => setFilterActive(e.target.value === '' ? null : e.target.value === 'true')}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Statuses</option>
            <option value="true">Active Only</option>
            <option value="false">Inactive Only</option>
          </select>
        </div>
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
          <p className="mt-2 text-gray-600">Loading users...</p>
        </div>
      ) : users.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-600 text-lg mb-4">No users found. Add your first user.</p>
          <button
            onClick={openAddForm}
            className="px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            Add User
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  User
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Role
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Device Access
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Last Login
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {users.map((user) => (
                <tr key={user.sub} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex flex-col">
                      <div className="text-sm font-medium text-gray-900">
                        {user.display_name || user.email || 'N/A'}
                      </div>
                      {user.email && user.display_name && (
                        <div className="text-sm text-gray-500">{user.email}</div>
                      )}
                      <div className="text-xs text-gray-400">{user.sub}</div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-gray-900">{user.role_name}</span>
                      {user.role_description && (
                        <span className="text-xs text-gray-500">{user.role_description}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {getAccessBadge(user.device_scopes)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {getStatusBadge(user)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                    {user.last_login_at
                      ? new Date(user.last_login_at).toLocaleString()
                      : 'Never'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                    <button
                      onClick={() => openEditForm(user)}
                      className="text-green-600 hover:text-green-800"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => setDeletingUser(user)}
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

      {showForm && (
        <UserForm
          user={editingUser}
          roles={roles}
          devices={devices.map((d) => ({ id: d.id, name: d.name }))}
          onSubmit={editingUser ? handleEditUser : handleAddUser}
          onCancel={closeForm}
        />
      )}

      {deletingUser && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
            <h2 className="text-xl font-bold text-gray-800 mb-4">Confirm Delete</h2>
            <p className="text-gray-600 mb-6">
              Are you sure you want to delete user{' '}
              <strong>{deletingUser.display_name || deletingUser.email || deletingUser.sub}</strong>?
              This action cannot be undone.
            </p>
            <div className="flex justify-end space-x-3">
              <button
                onClick={() => setDeletingUser(null)}
                className="px-4 py-2 text-gray-700 bg-gray-200 rounded-md hover:bg-gray-300 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteUser}
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
