import { useState, useEffect, useCallback } from 'react';
import { complianceApi, ApiError } from '../services/compliance';
import AuditTimeline from '../components/AuditTimeline';
import PolicyViolationHeatmap from '../components/PolicyViolationHeatmap';
import ApprovalMetrics from '../components/ApprovalMetrics';
import RoleDistribution from '../components/RoleDistribution';
import type {
  ComplianceAuditEvent,
  PolicyViolation,
  ApprovalDecision,
  ApprovalStatistics,
  RoleHistoryEntry,
  ComplianceFilters,
} from '../types/compliance';

export default function ComplianceDashboard() {
  // Loading states
  const [loadingAudit, setLoadingAudit] = useState(true);
  const [loadingViolations, setLoadingViolations] = useState(true);
  const [loadingApprovals, setLoadingApprovals] = useState(true);
  const [loadingRoles, setLoadingRoles] = useState(true);
  
  // Error states - separate for each section
  const [auditError, setAuditError] = useState<string | null>(null);
  const [violationsError, setViolationsError] = useState<string | null>(null);
  const [approvalsError, setApprovalsError] = useState<string | null>(null);
  const [rolesError, setRolesError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  // Data states
  const [auditEvents, setAuditEvents] = useState<ComplianceAuditEvent[]>([]);
  const [violations, setViolations] = useState<PolicyViolation[]>([]);
  const [violationsByDevice, setViolationsByDevice] = useState<Record<string, number>>({});
  const [approvalDecisions, setApprovalDecisions] = useState<ApprovalDecision[]>([]);
  const [approvalStatistics, setApprovalStatistics] = useState<ApprovalStatistics>({
    approved: 0,
    rejected: 0,
    pending: 0,
  });
  const [roleHistory, setRoleHistory] = useState<Record<string, RoleHistoryEntry[]>>({});

  // Filter states
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [deviceFilter, setDeviceFilter] = useState<string>('');
  const [userFilter, setUserFilter] = useState<string>('');

  // Set default date range (last 30 days)
  useEffect(() => {
    const now = new Date();
    const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    setDateFrom(thirtyDaysAgo.toISOString().split('T')[0]);
    setDateTo(now.toISOString().split('T')[0]);
  }, []);

  // Helper function to build filters from current state
  const buildFilters = useCallback((limit: number = 100): ComplianceFilters => {
    const filters: ComplianceFilters = { limit };
    
    if (dateFrom) {
      const fromDate = new Date(dateFrom);
      if (!isNaN(fromDate.getTime())) {
        filters.date_from = fromDate.toISOString();
      }
    }
    if (dateTo) {
      const toDate = new Date(dateTo);
      if (!isNaN(toDate.getTime())) {
        filters.date_to = toDate.toISOString();
      }
    }
    if (deviceFilter) {
      filters.device_id = deviceFilter;
    }
    if (userFilter) {
      filters.user_id = userFilter;
    }
    
    return filters;
  }, [dateFrom, dateTo, deviceFilter, userFilter]);

  // Fetch audit events
  const fetchAuditEvents = useCallback(async () => {
    setLoadingAudit(true);
    try {
      const filters = buildFilters(100);
      const response = await complianceApi.getAuditExport(filters);
      setAuditEvents(response.events);
      setAuditError(null);
    } catch (err) {
      console.error('Failed to fetch audit events:', err);
      setAuditError(err instanceof ApiError ? err.message : 'Failed to fetch audit events');
    } finally {
      setLoadingAudit(false);
    }
  }, [buildFilters]);

  // Fetch policy violations
  const fetchViolations = useCallback(async () => {
    setLoadingViolations(true);
    try {
      const filters = buildFilters(100);
      const response = await complianceApi.getPolicyViolations(filters);
      setViolations(response.violations);
      setViolationsByDevice(response.statistics.by_device);
      setViolationsError(null);
    } catch (err) {
      console.error('Failed to fetch policy violations:', err);
      setViolationsError(err instanceof ApiError ? err.message : 'Failed to fetch policy violations');
    } finally {
      setLoadingViolations(false);
    }
  }, [buildFilters]);

  // Fetch approval metrics
  const fetchApprovals = useCallback(async () => {
    setLoadingApprovals(true);
    try {
      const filters = buildFilters(100);
      const response = await complianceApi.getApprovalSummary(filters);
      setApprovalDecisions(response.decisions);
      setApprovalStatistics(response.statistics);
      setApprovalsError(null);
    } catch (err) {
      console.error('Failed to fetch approval metrics:', err);
      setApprovalsError(err instanceof ApiError ? err.message : 'Failed to fetch approval metrics');
    } finally {
      setLoadingApprovals(false);
    }
  }, [buildFilters]);

  // Fetch role distribution
  const fetchRoleDistribution = useCallback(async () => {
    setLoadingRoles(true);
    try {
      const filters = buildFilters(500);
      const response = await complianceApi.getRoleAudit(filters);
      setRoleHistory(response.role_history);
      setRolesError(null);
    } catch (err) {
      console.error('Failed to fetch role distribution:', err);
      setRolesError(err instanceof ApiError ? err.message : 'Failed to fetch role distribution');
    } finally {
      setLoadingRoles(false);
    }
  }, [buildFilters]);

  // Fetch all data
  const fetchAllData = useCallback(() => {
    if (dateFrom && dateTo) {
      fetchAuditEvents();
      fetchViolations();
      fetchApprovals();
      fetchRoleDistribution();
    }
  }, [dateFrom, dateTo, fetchAuditEvents, fetchViolations, fetchApprovals, fetchRoleDistribution]);

  // Initial load and refresh when filters change
  useEffect(() => {
    fetchAllData();
  }, [fetchAllData]);

  // Export handlers
  const handleExportJson = async () => {
    setExportError(null);
    try {
      const filters = buildFilters(10000);
      const response = await complianceApi.getAuditExport(filters);
      const dataStr = JSON.stringify(response, null, 2);
      const dataBlob = new Blob([dataStr], { type: 'application/json' });
      const url = URL.createObjectURL(dataBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `compliance-audit-${new Date().toISOString()}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to export JSON:', err);
      setExportError(err instanceof ApiError ? err.message : 'Failed to export data to JSON');
    }
  };

  const handleExportCsv = async () => {
    setExportError(null);
    try {
      const filters = buildFilters(10000);
      const blob = await complianceApi.exportAuditToCsv(filters);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `compliance-audit-${new Date().toISOString()}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to export CSV:', err);
      setExportError(err instanceof ApiError ? err.message : 'Failed to export data to CSV');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Compliance Dashboard</h1>
          <p className="mt-1 text-sm text-gray-600">
            Monitor audit logs, policy violations, and approval metrics
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleExportJson}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
          >
            Export JSON
          </button>
          <button
            onClick={handleExportCsv}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-medium"
          >
            Export CSV
          </button>
        </div>
      </div>

      {/* Error Display */}
      {(exportError || auditError || violationsError || approvalsError || rolesError) && (
        <div className="space-y-2">
          {exportError && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
              <strong className="font-medium">Export Error:</strong> {exportError}
            </div>
          )}
          {auditError && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
              <strong className="font-medium">Audit Error:</strong> {auditError}
            </div>
          )}
          {violationsError && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
              <strong className="font-medium">Violations Error:</strong> {violationsError}
            </div>
          )}
          {approvalsError && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
              <strong className="font-medium">Approvals Error:</strong> {approvalsError}
            </div>
          )}
          {rolesError && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
              <strong className="font-medium">Roles Error:</strong> {rolesError}
            </div>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Filters</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label htmlFor="dateFrom" className="block text-sm font-medium text-gray-700 mb-1">
              Date From
            </label>
            <input
              type="date"
              id="dateFrom"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label htmlFor="dateTo" className="block text-sm font-medium text-gray-700 mb-1">
              Date To
            </label>
            <input
              type="date"
              id="dateTo"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label htmlFor="deviceFilter" className="block text-sm font-medium text-gray-700 mb-1">
              Device ID
            </label>
            <input
              type="text"
              id="deviceFilter"
              value={deviceFilter}
              onChange={(e) => setDeviceFilter(e.target.value)}
              placeholder="Filter by device..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label htmlFor="userFilter" className="block text-sm font-medium text-gray-700 mb-1">
              User ID
            </label>
            <input
              type="text"
              id="userFilter"
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value)}
              placeholder="Filter by user..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
        </div>
        <div className="mt-4">
          <button
            onClick={fetchAllData}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
          >
            Apply Filters
          </button>
        </div>
      </div>

      {/* Dashboard Grid - Lazy Load Components */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="lg:col-span-2">
          <AuditTimeline events={auditEvents} loading={loadingAudit} />
        </div>

        <div>
          <PolicyViolationHeatmap
            violations={violations}
            violationsByDevice={violationsByDevice}
            loading={loadingViolations}
          />
        </div>

        <div>
          <ApprovalMetrics
            statistics={approvalStatistics}
            decisions={approvalDecisions}
            loading={loadingApprovals}
          />
        </div>

        <div className="lg:col-span-2">
          <RoleDistribution roleHistory={roleHistory} loading={loadingRoles} />
        </div>
      </div>
    </div>
  );
}
