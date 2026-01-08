import { useState, useEffect, useRef } from 'react';
import { planApi, ApiError } from '../services/api';
import PlanDetails from '../components/PlanDetails';
import type { Plan } from '../types/plan';

export default function Plans() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [approving, setApproving] = useState<string | null>(null);
  const [approvalToken, setApprovalToken] = useState<string | null>(null);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectingPlan, setRejectingPlan] = useState<Plan | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [rejecting, setRejecting] = useState(false);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [copiedToken, setCopiedToken] = useState(false);
  const rejectModalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadPlans();
  }, []);

  // Handle Escape key for reject modal
  useEffect(() => {
    if (!showRejectModal) return;

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowRejectModal(false);
        setRejectingPlan(null);
        setRejectionReason('');
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [showRejectModal]);

  // Focus trap for reject modal
  useEffect(() => {
    if (!showRejectModal || !rejectModalRef.current) return;

    const modalElement = rejectModalRef.current;
    const focusableElements = modalElement.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const firstElement = focusableElements[0] as HTMLElement;
    const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

    firstElement?.focus();

    const handleTabKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;

      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    };

    document.addEventListener('keydown', handleTabKey);
    return () => document.removeEventListener('keydown', handleTabKey);
  }, [showRejectModal]);

  const loadPlans = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await planApi.list('pending');
      setPlans(data);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to load plans';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleRowClick = async (plan: Plan) => {
    try {
      // Fetch detailed plan information
      const detailedPlan = await planApi.getDetail(plan.id);
      setSelectedPlan(detailedPlan);
      setShowDetails(true);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to load plan details';
      setOperationError(message);
    }
  };

  const handleApprove = async (plan: Plan) => {
    setApproving(plan.id);
    setOperationError(null);
    setApprovalToken(null);

    try {
      const result = await planApi.approve(plan.id);
      setApprovalToken(result.approval_token);
      // Remove from pending list
      setPlans(plans.filter(p => p.id !== plan.id));
      setShowDetails(false);
      setSelectedPlan(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to approve plan';
      setOperationError(message);
    } finally {
      setApproving(null);
    }
  };

  const handleRejectClick = (plan: Plan) => {
    setRejectingPlan(plan);
    setRejectionReason('');
    setShowRejectModal(true);
  };

  const handleRejectSubmit = async () => {
    if (!rejectingPlan || !rejectionReason.trim()) return;

    setRejecting(true);
    setOperationError(null);

    try {
      await planApi.reject(rejectingPlan.id, rejectionReason);
      // Remove from pending list
      setPlans(plans.filter(p => p.id !== rejectingPlan.id));
      setShowRejectModal(false);
      setRejectingPlan(null);
      setRejectionReason('');
      setShowDetails(false);
      setSelectedPlan(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Failed to reject plan';
      setOperationError(message);
    } finally {
      setRejecting(false);
    }
  };

  const copyToClipboard = async () => {
    if (!approvalToken) return;

    if (!navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') {
      console.error('Clipboard API is not available in this browser/environment');
      setOperationError(
        'Copying is not supported in this browser. Please copy the token manually.'
      );
      return;
    }

    try {
      await navigator.clipboard.writeText(approvalToken);
      setCopiedToken(true);
      setTimeout(() => setCopiedToken(false), 2000);
    } catch (err) {
      console.error('Failed to copy approval token to clipboard', err);

      let message = 'Failed to copy to clipboard. Please try again.';
      if (err && typeof err === 'object') {
        const errorName = (err as { name?: string }).name;
        if (errorName === 'NotAllowedError' || errorName === 'SecurityError') {
          message =
            'Permission to access the clipboard was denied. Please check your browser permissions and try again.';
        }
      }

      setOperationError(message);
    }
  };

  const isExpired = (plan: Plan): boolean => {
    if (!plan.approval_token_expires_at) return false;
    return new Date(plan.approval_token_expires_at) < new Date();
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800">Plan Approval Queue</h1>
        <button
          onClick={loadPlans}
          disabled={loading}
          className="px-4 py-2 text-sm bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300 transition-colors disabled:bg-gray-100 disabled:text-gray-400"
        >
          {loading ? 'Refreshing...' : 'Refresh'}
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

      {approvalToken && (
        <div className="mb-4 p-4 bg-green-100 border border-green-400 rounded-md">
          <h3 className="text-lg font-semibold text-green-800 mb-2">Plan Approved!</h3>
          <p className="text-green-700 text-sm mb-3">
            Copy this approval token to use when executing the plan:
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              value={approvalToken}
              readOnly
              className="flex-1 px-3 py-2 border border-green-300 rounded-md bg-white font-mono text-sm"
            />
            <button
              onClick={copyToClipboard}
              className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors"
            >
              {copiedToken ? '✓ Copied!' : 'Copy to Clipboard'}
            </button>
          </div>
          <button
            onClick={() => setApprovalToken(null)}
            className="mt-3 text-sm text-green-700 hover:text-green-900 underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-center py-8">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
          <p className="mt-2 text-gray-600">Loading pending plans...</p>
        </div>
      ) : plans.length === 0 ? (
        <div className="text-center py-12 border-2 border-dashed border-gray-300 rounded-lg">
          <p className="text-gray-600 text-lg">No pending plans</p>
          <p className="text-gray-500 text-sm mt-2">
            All plans have been reviewed or there are no plans awaiting approval.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Plan ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Change Type
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Device Count
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Created At
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {plans.map((plan) => (
                <tr 
                  key={plan.id} 
                  onClick={() => handleRowClick(plan)}
                  className={`cursor-pointer hover:bg-gray-50 transition-colors ${
                    isExpired(plan) ? 'opacity-50 bg-gray-50' : ''
                  }`}
                >
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">
                    {plan.id}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {plan.tool_name}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {plan.device_ids.length}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {new Date(plan.created_at).toLocaleString()}
                    {isExpired(plan) && (
                      <span className="ml-2 text-xs text-red-600">(Expired)</span>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleApprove(plan);
                      }}
                      disabled={approving === plan.id}
                      className="text-green-600 hover:text-green-800 disabled:text-gray-400"
                    >
                      {approving === plan.id ? (
                        <span className="inline-flex items-center">
                          <span className="inline-block animate-spin rounded-full h-3 w-3 border-b-2 border-green-600 mr-1"></span>
                          Approving...
                        </span>
                      ) : (
                        'Approve'
                      )}
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRejectClick(plan);
                      }}
                      className="text-red-600 hover:text-red-800"
                    >
                      Reject
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showDetails && selectedPlan && (
        <PlanDetails 
          plan={selectedPlan} 
          onClose={() => {
            setShowDetails(false);
            setSelectedPlan(null);
          }} 
        />
      )}

      {showRejectModal && rejectingPlan && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div 
            ref={rejectModalRef}
            className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reject-modal-title"
          >
            <h2 id="reject-modal-title" className="text-xl font-bold text-gray-800 mb-4">Reject Plan</h2>
            <p className="text-gray-600 mb-4">
              Please provide a reason for rejecting plan <strong>{rejectingPlan.id}</strong>:
            </p>
            <textarea
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 mb-4"
              rows={4}
              placeholder="Enter rejection reason..."
              required
              aria-label="Rejection reason"
            />
            {!rejectionReason.trim() && (
              <p className="text-sm text-red-600 mb-4">Reason is required</p>
            )}
            <div className="flex justify-end space-x-3">
              <button
                onClick={() => {
                  setShowRejectModal(false);
                  setRejectingPlan(null);
                  setRejectionReason('');
                }}
                disabled={rejecting}
                className="px-4 py-2 text-gray-700 bg-gray-200 rounded-md hover:bg-gray-300 transition-colors disabled:bg-gray-100"
              >
                Cancel
              </button>
              <button
                onClick={handleRejectSubmit}
                disabled={rejecting || !rejectionReason.trim()}
                className="px-4 py-2 text-white bg-red-600 rounded-md hover:bg-red-700 transition-colors disabled:bg-red-400"
              >
                {rejecting ? 'Rejecting...' : 'Reject Plan'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
