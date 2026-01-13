import type { ComplianceAuditEvent } from '../types/compliance';

interface AuditTimelineProps {
  events: ComplianceAuditEvent[];
  loading?: boolean;
}

export default function AuditTimeline({ events, loading }: AuditTimelineProps) {
  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Audit Log Timeline</h3>
        <div className="flex items-center justify-center py-8">
          <div className="text-gray-500">Loading timeline...</div>
        </div>
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Audit Log Timeline</h3>
        <div className="text-gray-500 text-center py-8">
          No audit events found for the selected filters.
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Audit Log Timeline</h3>
      <div className="space-y-4 max-h-96 overflow-y-auto">
        {events.map((event) => {
          const borderColorClass =
            event.result === 'success' ? 'border-green-500' : 'border-red-500';

          return (
            <div key={event.id} className={`border-l-4 ${borderColorClass} pl-4 py-2`}>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900">{event.action}</span>
                    {event.result === 'success' ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                        Success
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
                        Failed
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-sm text-gray-600">
                    <span className="font-medium">{event.user_email || event.user_sub}</span>
                    {event.user_role && (
                      <span className="ml-2 text-gray-500">({event.user_role})</span>
                    )}
                  </div>
                  {event.tool_name && (
                    <div className="mt-1 text-xs text-gray-500">
                      Tool: {event.tool_name}
                      {event.tool_tier && ` (${event.tool_tier})`}
                    </div>
                  )}
                  {event.device_id && (
                    <div className="mt-1 text-xs text-gray-500">Device: {event.device_id}</div>
                  )}
                  {event.error_message && (
                    <div className="mt-1 text-xs text-red-600">{event.error_message}</div>
                  )}
                </div>
                <div className="text-xs text-gray-500 whitespace-nowrap ml-4">
                  {new Date(event.timestamp).toLocaleString()}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
