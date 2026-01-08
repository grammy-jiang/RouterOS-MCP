import type { Plan } from '../types/plan';

interface PlanDetailsProps {
  plan: Plan;
  onClose: () => void;
}

export default function PlanDetails({ plan, onClose }: PlanDetailsProps) {
  const isExpired = plan.approval_token_expires_at 
    ? new Date(plan.approval_token_expires_at) < new Date()
    : false;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center">
          <h2 className="text-2xl font-bold text-gray-800">Plan Details</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 text-2xl font-bold"
          >
            ×
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Plan ID and Status */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Plan ID</label>
              <p className="text-sm text-gray-900 font-mono bg-gray-50 px-3 py-2 rounded">{plan.id}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
              <span className={`inline-block px-3 py-1 text-sm font-medium rounded-full ${
                plan.status === 'pending' ? 'bg-yellow-100 text-yellow-800' :
                plan.status === 'approved' ? 'bg-green-100 text-green-800' :
                plan.status === 'executing' ? 'bg-blue-100 text-blue-800' :
                plan.status === 'completed' ? 'bg-green-100 text-green-800' :
                plan.status === 'failed' ? 'bg-red-100 text-red-800' :
                'bg-gray-100 text-gray-800'
              }`}>
                {plan.status}
              </span>
              {isExpired && plan.status === 'approved' && (
                <span className="ml-2 text-xs text-red-600">(Token Expired)</span>
              )}
            </div>
          </div>

          {/* Created By and Time */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Created By</label>
              <p className="text-sm text-gray-900">{plan.created_by}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Created At</label>
              <p className="text-sm text-gray-900">
                {new Date(plan.created_at).toLocaleString()}
              </p>
            </div>
          </div>

          {/* Tool Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Change Type</label>
            <p className="text-sm text-gray-900">{plan.tool_name}</p>
          </div>

          {/* Summary */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Summary</label>
            <p className="text-sm text-gray-900 whitespace-pre-wrap">{plan.summary}</p>
          </div>

          {/* Affected Devices */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Affected Devices ({plan.device_ids.length})
            </label>
            <div className="bg-gray-50 rounded-md p-3">
              <ul className="space-y-1">
                {plan.device_ids.map((deviceId) => (
                  <li key={deviceId} className="text-sm text-gray-900 font-mono">
                    • {deviceId}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Changes/Diff */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Proposed Changes
            </label>
            <div className="bg-gray-900 text-gray-100 rounded-md p-4 overflow-x-auto">
              <pre className="text-xs font-mono whitespace-pre-wrap">
                {JSON.stringify(plan.changes, null, 2)}
              </pre>
            </div>
          </div>

          {/* Approval Info (if approved) */}
          {plan.approved_by && (
            <div className="grid grid-cols-2 gap-4 border-t border-gray-200 pt-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Approved By</label>
                <p className="text-sm text-gray-900">{plan.approved_by}</p>
              </div>
              {plan.approved_at && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Approved At</label>
                  <p className="text-sm text-gray-900">
                    {new Date(plan.approved_at).toLocaleString()}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="sticky bottom-0 bg-gray-50 border-t border-gray-200 px-6 py-4 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
