import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Devices from './pages/Devices';
import Plans from './pages/Plans';
import AuditLog from './pages/AuditLog';
import AdminUsers from './pages/AdminUsers';
import ComplianceDashboard from './pages/ComplianceDashboard';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="devices" element={<Devices />} />
          <Route path="plans" element={<Plans />} />
          <Route path="audit" element={<AuditLog />} />
          <Route path="compliance" element={<ComplianceDashboard />} />
          <Route path="admin/users" element={<AdminUsers />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
