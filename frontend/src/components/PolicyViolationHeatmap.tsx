import React from 'react';
import type { PolicyViolation } from '../types/compliance';

interface PolicyViolationHeatmapProps {
  violations: PolicyViolation[];
  violationsByDevice: Record<string, number>;
  loading?: boolean;
}

export default function PolicyViolationHeatmap({
  violations,
  violationsByDevice,
  loading,
}: PolicyViolationHeatmapProps) {
  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Policy Violations</h3>
        <div className="flex items-center justify-center py-8">
          <div className="text-gray-500">Loading violations...</div>
        </div>
      </div>
    );
  }

  const maxViolations = Math.max(...Object.values(violationsByDevice), 1);

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Policy Violations</h3>

      {/* Violations by Device Heatmap */}
      {Object.keys(violationsByDevice).length > 0 ? (
        <div className="mb-6">
          <h4 className="text-sm font-medium text-gray-700 mb-3">Violations by Device</h4>
          <div className="space-y-2">
            {Object.entries(violationsByDevice)
              .sort(([, a], [, b]) => b - a)
              .map(([deviceId, count]) => {
                const percentage = (count / maxViolations) * 100;
                const intensity = Math.min(Math.floor((count / maxViolations) * 9), 9);
                const colorClasses = [
                  'bg-red-50',
                  'bg-red-100',
                  'bg-red-200',
                  'bg-red-300',
                  'bg-red-400',
                  'bg-red-500',
                  'bg-red-600',
                  'bg-red-700',
                  'bg-red-800',
                  'bg-red-900',
                ];

                return (
                  <div key={deviceId} className="flex items-center gap-2">
                    <div className="w-32 text-sm text-gray-700 truncate" title={deviceId}>
                      {deviceId}
                    </div>
                    <div className="flex-1 h-8 bg-gray-100 rounded overflow-hidden">
                      <div
                        className={`h-full ${colorClasses[intensity]} flex items-center px-2 text-white text-xs font-medium transition-all`}
                        style={{ width: `${percentage}%` }}
                      >
                        {count > 0 && <span>{count}</span>}
                      </div>
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      ) : (
        <div className="text-gray-500 text-center py-4 mb-6">
          No violations by device found.
        </div>
      )}

      {/* Recent Violations Table */}
      {violations.length > 0 ? (
        <div>
          <h4 className="text-sm font-medium text-gray-700 mb-3">Recent Violations</h4>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Timestamp
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    User
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Device
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Tool
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Error
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {violations.slice(0, 10).map((violation) => (
                  <tr key={violation.id}>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900">
                      {new Date(violation.timestamp).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-900">
                      <div>{violation.user_email || violation.user_sub}</div>
                      {violation.user_role && (
                        <div className="text-gray-500">({violation.user_role})</div>
                      )}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900">
                      {violation.device_id || 'N/A'}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900">
                      {violation.tool_name}
                    </td>
                    <td className="px-3 py-2 text-xs text-red-600 max-w-xs truncate" title={violation.error_message || ''}>
                      {violation.error_message || 'Authorization denied'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="text-gray-500 text-center py-4">
          No recent violations found.
        </div>
      )}
    </div>
  );
}
