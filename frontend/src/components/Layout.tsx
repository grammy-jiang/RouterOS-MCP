import { Link, Outlet } from 'react-router-dom';

export default function Layout() {
  return (
    <div className="flex h-screen bg-gray-100">
      {/* Sidebar */}
      <aside className="w-64 bg-white shadow-md">
        <div className="p-6">
          <h1 className="text-2xl font-bold text-gray-800">RouterOS MCP</h1>
        </div>
        <nav className="mt-6">
          <Link
            to="/"
            className="block py-2.5 px-6 text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors"
          >
            Dashboard
          </Link>
          <Link
            to="/devices"
            className="block py-2.5 px-6 text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors"
          >
            Devices
          </Link>
          <Link
            to="/plans"
            className="block py-2.5 px-6 text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors"
          >
            Plans
          </Link>
          <Link
            to="/audit"
            className="block py-2.5 px-6 text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors"
          >
            Audit Log
          </Link>
        </nav>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="bg-white shadow-sm">
          <div className="px-6 py-4">
            <h2 className="text-xl font-semibold text-gray-800">RouterOS MCP Admin</h2>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-x-hidden overflow-y-auto bg-gray-100 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
