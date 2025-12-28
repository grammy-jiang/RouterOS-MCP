// RouterOS MCP Admin Console - Alpine.js App

function adminApp() {
    return {
        // State
        currentView: 'dashboard',
        devices: [],
        plans: [],
        selectedPlan: null,
        showPlanDetail: false,
        showRejectDialog: false,
        rejectReason: '',
        planFilter: '',
        loading: false,
        errorMessage: '',
        successMessage: '',
        userEmail: '',
        userRole: '',

        // Initialize
        async init() {
            console.log('Initializing admin app...');
            await this.loadUserInfo();
            await this.loadDevices();
            await this.loadPlans();
        },

        // Load user information
        async loadUserInfo() {
            try {
                const response = await fetch('/api/user');
                if (response.ok) {
                    const data = await response.json();
                    this.userEmail = data.email || 'anonymous@localhost';
                    this.userRole = data.role || 'read_only';
                } else {
                    // If OIDC is disabled, use default values
                    this.userEmail = 'anonymous@localhost';
                    this.userRole = 'admin';
                }
            } catch (error) {
                console.error('Error loading user info:', error);
                this.userEmail = 'anonymous@localhost';
                this.userRole = 'admin';
            }
        },

        // Load devices
        async loadDevices() {
            this.loading = true;
            try {
                const response = await fetch('/admin/api/devices');
                if (!response.ok) {
                    throw new Error(`Failed to load devices: ${response.statusText}`);
                }
                const data = await response.json();
                this.devices = data.devices || [];
            } catch (error) {
                console.error('Error loading devices:', error);
                this.showError('Failed to load devices: ' + error.message);
            } finally {
                this.loading = false;
            }
        },

        // Load plans
        async loadPlans() {
            this.loading = true;
            try {
                const url = this.planFilter 
                    ? `/admin/api/plans?status_filter=${this.planFilter}`
                    : '/admin/api/plans';
                
                const response = await fetch(url);
                if (!response.ok) {
                    throw new Error(`Failed to load plans: ${response.statusText}`);
                }
                const data = await response.json();
                this.plans = data.plans || [];
            } catch (error) {
                console.error('Error loading plans:', error);
                this.showError('Failed to load plans: ' + error.message);
            } finally {
                this.loading = false;
            }
        },

        // View plan detail
        async viewPlanDetail(planId) {
            this.loading = true;
            try {
                const response = await fetch(`/admin/api/plans/${planId}`);
                if (!response.ok) {
                    throw new Error(`Failed to load plan: ${response.statusText}`);
                }
                this.selectedPlan = await response.json();
                this.showPlanDetail = true;
            } catch (error) {
                console.error('Error loading plan detail:', error);
                this.showError('Failed to load plan: ' + error.message);
            } finally {
                this.loading = false;
            }
        },

        // Approve plan
        async approvePlan() {
            if (!this.selectedPlan) return;

            const confirmed = confirm(
                'Are you sure you want to approve this plan? ' +
                'This will generate an approval token that can be used to execute the plan.'
            );

            if (!confirmed) return;

            this.loading = true;
            try {
                const response = await fetch(
                    `/admin/api/plans/${this.selectedPlan.id}/approve`,
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({}),
                    }
                );

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to approve plan');
                }

                const result = await response.json();
                this.showSuccess('Plan approved successfully! Token: ' + result.approval_token);
                
                // Reload plan to get updated status and token
                await this.viewPlanDetail(this.selectedPlan.id);
                await this.loadPlans();
            } catch (error) {
                console.error('Error approving plan:', error);
                this.showError('Failed to approve plan: ' + error.message);
            } finally {
                this.loading = false;
            }
        },

        // Reject plan
        async rejectPlan() {
            if (!this.selectedPlan || !this.rejectReason.trim()) {
                this.showError('Please provide a reason for rejection');
                return;
            }

            this.loading = true;
            try {
                const response = await fetch(
                    `/admin/api/plans/${this.selectedPlan.id}/reject`,
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ reason: this.rejectReason }),
                    }
                );

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to reject plan');
                }

                this.showSuccess('Plan rejected successfully');
                this.showRejectDialog = false;
                this.showPlanDetail = false;
                this.rejectReason = '';
                await this.loadPlans();
            } catch (error) {
                console.error('Error rejecting plan:', error);
                this.showError('Failed to reject plan: ' + error.message);
            } finally {
                this.loading = false;
            }
        },

        // Format date
        formatDate(dateString) {
            if (!dateString) return 'N/A';
            const date = new Date(dateString);
            return date.toLocaleString();
        },

        // Format changes for preview
        formatChanges(changes) {
            if (!changes) return 'No changes';
            return JSON.stringify(changes, null, 2);
        },

        // Show error message
        showError(message) {
            this.errorMessage = message;
            setTimeout(() => {
                this.errorMessage = '';
            }, 5000);
        },

        // Show success message
        showSuccess(message) {
            this.successMessage = message;
            setTimeout(() => {
                this.successMessage = '';
            }, 5000);
        },
    };
}
