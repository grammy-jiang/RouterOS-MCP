import React, { useState, useEffect, useCallback } from 'react';
import { auditApi, deviceApi, ApiError } from '../services/api';
import type { AuditEvent, AuditEventsFilter } from '../types/audit';

export default function AuditLog() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  // Filter state
  const [deviceFilter, setDeviceFilter] = useState<string>('');
  const [toolFilter, setToolFilter] = useState<string>('');
  const [resultFilter, setResultFilter] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Filter options
  const [availableDevices, setAvailableDevices] = useState<string[]>([]);
  const [availableTools, setAvailableTools] = useState<string[]>([]);

  // Helper function to build filter object from current state
  const buildFilter = (): AuditEventsFilter => {
    const filter: AuditEventsFilter = {};

    if (deviceFilter) filter.device_id = deviceFilter;
    if (toolFilter) filter.tool_name = toolFilter;
    if (resultFilter) {
      filter.success = resultFilter === 'success' ? true : resultFilter === 'failure' ? false : undefined;
    }
    if (dateFrom) {
      const fromDate = new Date(dateFrom);
      if (!isNaN(fromDate.getTime())) {
        filter.date_from = fromDate.toISOString();
      }
    }
    if (dateTo) {
      const toDate = new Date(dateTo);
      if (!isNaN(toDate.getTime())) {
        filter.date_to = toDate.toISOString();
      }
    }
    if (searchQuery) filter.search = searchQuery;

    return filter;
  };

  useEffect(() => {
    loadFilterOptions();
  }, []);

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  const loadFilterOptions = async () => {
    try {
      // Load devices
      const devices = await deviceApi.list();
      setAvailableDevices(devices.map(d => d.id));

      // Load available filter options from audit API
      const filterData = await auditApi.getFilters();
      if (filterData.tools) {
        setAvailableTools(filterData.tools);
      }
    } catch (err) {
      console.error('Failed to load filter options:', err);
    }
  };

  const loadEvents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const filter: AuditEventsFilter = {
        ...buildFilter(),
        page: currentPage,
        page_size: pageSize,
      };

      const response = await auditApi.listEvents(filter);
      setEvents(response.events);
      setTotal(response.total);
      setTotalPages(response.total_pages);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to load audit events';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [currentPage, deviceFilter, toolFilter, resultFilter, dateFrom, dateTo, searchQuery, pageSize]);

  const handleExportCsv = async () => {
    try {
      const filter = buildFilter();

      const blob = await auditApi.exportToCsv(filter);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_events_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to export CSV';
      setError(message);
    }
  };

  const handleResetFilters = () => {
    setDeviceFilter('');
    setToolFilter('');
    setResultFilter('');
    setDateFrom('');
    setDateTo('');
    setSearchQuery('');
    setCurrentPage(1);
  };

  const toggleExpandEvent = (eventId: string) => {
    setExpandedEventId(expandedEventId === eventId ? null : eventId);
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString();
  };

  const getResultBadge = (success: boolean) => {
    if (success) {
      return (
        <span className="px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800">
          Success
        </span>
      );
    }
    return (
      <span className="px-2 py-1 text-xs font-medium rounded-full bg-red-100 text-red-800">
        Failure
      </span>
    );
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800">Audit Log</h1>
        <button
          onClick={handleExportCsv}
          className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors"
        >
          Export CSV
        </button>
      </div>

      {/* Filters */}
      <div className="mb-6 p-4 bg-gray-50 rounded-lg">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          {/* Date From */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Date From
            </label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Date To */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Date To
            </label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Device Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Device
            </label>
            <select
              value={deviceFilter}
              onChange={(e) => {
                setDeviceFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All Devices</option>
              {availableDevices.map((device) => (
                <option key={device} value={device}>
                  {device}
                </option>
              ))}
            </select>
          </div>

          {/* Tool Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Tool
            </label>
            <select
              value={toolFilter}
              onChange={(e) => {
                setToolFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All Tools</option>
              {availableTools.map((tool) => (
                <option key={tool} value={tool}>
                  {tool}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Result Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Result
            </label>
            <select
              value={resultFilter}
              onChange={(e) => {
                setResultFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All Results</option>
              <option value="success">Success</option>
              <option value="failure">Failure</option>
            </select>
          </div>

          {/* Search */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Search
            </label>
            <input
              type="text"
              placeholder="Search in event details..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        <div className="mt-4">
          <button
            onClick={handleResetFilters}
            className="px-4 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Reset Filters
          </button>
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

      {loading ? (
        <div className="text-center py-8">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
          <p className="mt-2 text-gray-600">Loading audit events...</p>
        </div>
      ) : events.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-600 text-lg">No audit events found.</p>
        </div>
      ) : (
        <>
          {/* Results Summary */}
          <div className="mb-4 text-sm text-gray-600">
            Showing {events.length} of {total} events (Page {currentPage} of {totalPages})
          </div>

          {/* Events Table */}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Timestamp
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    User
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Device
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Tool/Action
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Result
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {events.map((event) => (
                  <React.Fragment key={event.id}>
                    <tr className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {formatTimestamp(event.timestamp)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                        <div className="max-w-xs truncate" title={event.user_email || event.user_sub}>
                          {event.user_email || event.user_sub}
                        </div>
                        <div className="text-xs text-gray-500">{event.user_role}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                        {event.device_id || '-'}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900">
                        <div className="font-medium">{event.tool_name}</div>
                        <div className="text-xs text-gray-500">{event.action}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {getResultBadge(event.success)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        <button
                          onClick={() => toggleExpandEvent(event.id)}
                          className="text-blue-600 hover:text-blue-800"
                        >
                          {expandedEventId === event.id ? 'Hide Details' : 'View Details'}
                        </button>
                      </td>
                    </tr>
                    {expandedEventId === event.id && (
                      <tr key={`${event.id}-details`} className="bg-gray-50">
                        <td colSpan={6} className="px-6 py-4">
                          <div className="space-y-2">
                            <h4 className="font-medium text-gray-900">Event Details</h4>
                            
                            {event.result_summary && (
                              <div>
                                <span className="font-medium text-gray-700">Summary: </span>
                                <span className="text-gray-600">{event.result_summary}</span>
                              </div>
                            )}
                            
                            {event.error_message && (
                              <div>
                                <span className="font-medium text-gray-700">Error: </span>
                                <span className="text-red-600">{event.error_message}</span>
                              </div>
                            )}
                            
                            {event.correlation_id && (
                              <div>
                                <span className="font-medium text-gray-700">Correlation ID: </span>
                                <span className="text-gray-600 font-mono text-sm">{event.correlation_id}</span>
                              </div>
                            )}
                            
                            <div className="mt-4">
                              <span className="font-medium text-gray-700">Full Event Data:</span>
                              <pre className="mt-2 p-4 bg-gray-100 rounded-md overflow-x-auto text-xs">
                                {JSON.stringify(event, null, 2)}
                              </pre>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-6 flex justify-center items-center space-x-2">
              <button
                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                disabled={currentPage === 1}
                className="px-4 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Previous
              </button>

              {/* Page numbers */}
              <div className="flex space-x-1">
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let pageNum;
                  if (totalPages <= 5) {
                    pageNum = i + 1;
                  } else if (currentPage <= 3) {
                    pageNum = i + 1;
                  } else if (currentPage >= totalPages - 2) {
                    pageNum = totalPages - 4 + i;
                  } else {
                    pageNum = currentPage - 2 + i;
                  }

                  return (
                    <button
                      key={pageNum}
                      onClick={() => setCurrentPage(pageNum)}
                      className={`px-3 py-2 text-sm rounded-md transition-colors ${
                        currentPage === pageNum
                          ? 'bg-blue-600 text-white'
                          : 'text-gray-700 bg-white border border-gray-300 hover:bg-gray-50'
                      }`}
                    >
                      {pageNum}
                    </button>
                  );
                })}
              </div>

              <button
                onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                disabled={currentPage === totalPages}
                className="px-4 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
