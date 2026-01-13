import type { ApprovalStatistics, ApprovalDecision } from '../types/compliance';

interface ApprovalMetricsProps {
  statistics: ApprovalStatistics;
  decisions: ApprovalDecision[];
  loading?: boolean;
}

export default function ApprovalMetrics({ statistics, decisions, loading }: ApprovalMetricsProps) {
  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Approval Metrics</h3>
        <div className="flex items-center justify-center py-8">
          <div className="text-gray-500">Loading metrics...</div>
        </div>
      </div>
    );
  }

  const total = statistics.approved + statistics.rejected + statistics.pending;
  const approvalRate = total > 0 ? ((statistics.approved / total) * 100).toFixed(1) : '0.0';

  // Calculate average decision time for approved/rejected requests
  const decisionsWithTime = decisions.filter(
    (d) => d.status !== 'pending' && (d.approved_at || d.rejected_at) && d.requested_at
  );

  let avgDecisionTimeMinutes = 0;
  if (decisionsWithTime.length > 0) {
    const totalMinutes = decisionsWithTime.reduce((sum, d) => {
      const requestedAt = new Date(d.requested_at).getTime();
      const decidedAtStr = d.approved_at || d.rejected_at || '';
      const decidedAt = new Date(decidedAtStr).getTime();
      
      // Validate that both dates are valid before calculating
      if (isNaN(requestedAt) || isNaN(decidedAt)) {
        return sum;
      }
      
      const diffMinutes = (decidedAt - requestedAt) / 1000 / 60;
      return sum + diffMinutes;
    }, 0);
    avgDecisionTimeMinutes = totalMinutes / decisionsWithTime.length;
  }

  // Format average decision time
  const formatDecisionTime = (minutes: number): string => {
    if (minutes < 1) return '< 1 min';
    if (minutes < 60) return `${Math.round(minutes)} min`;
    const hours = minutes / 60;
    if (hours < 24) return `${hours.toFixed(1)} hrs`;
    const days = hours / 24;
    return `${days.toFixed(1)} days`;
  };

  // Get top approvers
  const approverCounts: Record<string, number> = {};
  decisions.forEach((d) => {
    if (d.approved_by) {
      approverCounts[d.approved_by] = (approverCounts[d.approved_by] || 0) + 1;
    }
  });
  const topApprovers = Object.entries(approverCounts)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Approval Metrics</h3>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-blue-50 rounded-lg p-4">
          <div className="text-sm text-blue-600 font-medium">Approval Rate</div>
          <div className="text-2xl font-bold text-blue-900 mt-1">{approvalRate}%</div>
          <div className="text-xs text-blue-600 mt-1">
            {statistics.approved} of {total} total
          </div>
        </div>

        <div className="bg-green-50 rounded-lg p-4">
          <div className="text-sm text-green-600 font-medium">Avg Decision Time</div>
          <div className="text-2xl font-bold text-green-900 mt-1">
            {formatDecisionTime(avgDecisionTimeMinutes)}
          </div>
          <div className="text-xs text-green-600 mt-1">
            {decisionsWithTime.length} decisions
          </div>
        </div>

        <div className="bg-purple-50 rounded-lg p-4">
          <div className="text-sm text-purple-600 font-medium">Pending Approvals</div>
          <div className="text-2xl font-bold text-purple-900 mt-1">{statistics.pending}</div>
          <div className="text-xs text-purple-600 mt-1">awaiting review</div>
        </div>
      </div>

      {/* Status Distribution */}
      <div className="mb-6">
        <h4 className="text-sm font-medium text-gray-700 mb-3">Status Distribution</h4>
        <div className="space-y-2">
          <div className="flex items-center">
            <div className="w-24 text-sm text-gray-700">Approved</div>
            <div className="flex-1 h-6 bg-gray-100 rounded overflow-hidden">
              <div
                className="h-full bg-green-500 flex items-center px-2 text-white text-xs font-medium"
                style={{
                  width: total > 0 ? `${(statistics.approved / total) * 100}%` : '0%',
                }}
              >
                {statistics.approved > 0 && <span>{statistics.approved}</span>}
              </div>
            </div>
          </div>
          <div className="flex items-center">
            <div className="w-24 text-sm text-gray-700">Rejected</div>
            <div className="flex-1 h-6 bg-gray-100 rounded overflow-hidden">
              <div
                className="h-full bg-red-500 flex items-center px-2 text-white text-xs font-medium"
                style={{
                  width: total > 0 ? `${(statistics.rejected / total) * 100}%` : '0%',
                }}
              >
                {statistics.rejected > 0 && <span>{statistics.rejected}</span>}
              </div>
            </div>
          </div>
          <div className="flex items-center">
            <div className="w-24 text-sm text-gray-700">Pending</div>
            <div className="flex-1 h-6 bg-gray-100 rounded overflow-hidden">
              <div
                className="h-full bg-yellow-500 flex items-center px-2 text-white text-xs font-medium"
                style={{
                  width: total > 0 ? `${(statistics.pending / total) * 100}%` : '0%',
                }}
              >
                {statistics.pending > 0 && <span>{statistics.pending}</span>}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Top Approvers */}
      {topApprovers.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 mb-3">Top Approvers</h4>
          <div className="space-y-2">
            {topApprovers.map(([approver, count], index) => (
              <div key={approver} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-gray-400">#{index + 1}</span>
                  <span className="text-sm text-gray-900">{approver}</span>
                </div>
                <span className="text-sm font-medium text-blue-600">{count} approvals</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
