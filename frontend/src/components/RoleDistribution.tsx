import type { RoleHistoryEntry } from '../types/compliance';

interface RoleDistributionProps {
  roleHistory: Record<string, RoleHistoryEntry[]>;
  loading?: boolean;
}

export default function RoleDistribution({ roleHistory, loading }: RoleDistributionProps) {
  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Role Distribution</h3>
        <div className="flex items-center justify-center py-8">
          <div className="text-gray-500">Loading role data...</div>
        </div>
      </div>
    );
  }

  // Count actions by role across all users
  const roleCounts: Record<string, number> = {};
  Object.values(roleHistory).forEach((entries) => {
    entries.forEach((entry) => {
      if (entry.user_role) {
        roleCounts[entry.user_role] = (roleCounts[entry.user_role] || 0) + 1;
      }
    });
  });

  const totalActions = Object.values(roleCounts).reduce((sum, count) => sum + count, 0);
  const roleEntries = Object.entries(roleCounts).sort(([, a], [, b]) => b - a);

  // Color map for roles
  const roleColors: Record<string, { bg: string; text: string }> = {
    admin: { bg: 'bg-red-500', text: 'text-red-700' },
    approver: { bg: 'bg-blue-500', text: 'text-blue-700' },
    auditor: { bg: 'bg-purple-500', text: 'text-purple-700' },
    operator: { bg: 'bg-green-500', text: 'text-green-700' },
    read_only: { bg: 'bg-gray-500', text: 'text-gray-700' },
  };

  const getColorForRole = (role: string) => {
    return roleColors[role] || { bg: 'bg-indigo-500', text: 'text-indigo-700' };
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Role Distribution</h3>

      {roleEntries.length === 0 ? (
        <div className="text-gray-500 text-center py-8">No role data available.</div>
      ) : (
        <>
          {/* Pie Chart (Simple horizontal bars as visualization) */}
          <div className="mb-6">
            <div className="space-y-3">
              {roleEntries.map(([role, count]) => {
                const percentage = ((count / totalActions) * 100).toFixed(1);
                const colors = getColorForRole(role);
                return (
                  <div key={role}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-gray-700 capitalize">
                        {role.replaceAll('_', ' ')}
                      </span>
                      <span className="text-sm text-gray-600">
                        {count} ({percentage}%)
                      </span>
                    </div>
                    <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${colors.bg} transition-all`}
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Role Legend */}
          <div className="border-t pt-4">
            <h4 className="text-sm font-medium text-gray-700 mb-3">Role Actions Summary</h4>
            <div className="grid grid-cols-2 gap-3">
              {roleEntries.map(([role, count]) => {
                const colors = getColorForRole(role);
                return (
                  <div key={role} className="flex items-center gap-2">
                    <div className={`w-3 h-3 rounded-full ${colors.bg}`} />
                    <span className="text-sm text-gray-700 capitalize">
                      {role.replaceAll('_', ' ')}
                    </span>
                    <span className="text-sm font-medium text-gray-900 ml-auto">{count}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Top Active Users by Role */}
          {Object.keys(roleHistory).length > 0 && (
            <div className="border-t pt-4 mt-4">
              <h4 className="text-sm font-medium text-gray-700 mb-3">Most Active Users</h4>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {Object.entries(roleHistory)
                  .sort(([, a], [, b]) => b.length - a.length)
                  .slice(0, 5)
                  .map(([userId, entries]) => {
                    const latestEntry = entries[0];
                    return (
                      <div key={userId} className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-gray-900 truncate">
                            {latestEntry.user_email || userId}
                          </div>
                          {latestEntry.user_role && (
                            <div className="text-xs text-gray-500 capitalize">
                              {latestEntry.user_role.replaceAll('_', ' ')}
                            </div>
                          )}
                        </div>
                        <div className="text-sm font-medium text-gray-700 ml-2">
                          {entries.length} actions
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
