# RouterOS MCP - Web Admin UI

Phase 4 web-based admin interface for RouterOS MCP service.

## Overview

This is a React + TypeScript + Vite application providing a web UI for:
- Device management
- Plan approval workflows  
- Audit log viewing
- System configuration

## Tech Stack

- **React 19.2.0** - UI framework
- **TypeScript 5.9.3** - Type safety
- **Vite 7.3.1** - Build tool and dev server
- **Tailwind CSS 3.4.0** - Utility-first CSS framework
- **React Router 7.12.0** - Client-side routing

## Requirements

- **Node.js 18+** (tested with v20.19.6)
- **npm 8+** (tested with v10.8.2)

## Getting Started

### Installation

```bash
cd frontend
npm install
```

### Development

Start the dev server with hot module replacement:

```bash
npm run dev
```

The application will be available at http://localhost:5173

### Production Build

Build optimized static files for production:

```bash
npm run build
```

Output will be in the `dist/` directory.

### Preview Production Build

Preview the production build locally:

```bash
npm run preview
```

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   └── Layout.tsx          # Main layout with sidebar and header
│   ├── pages/
│   │   ├── Dashboard.tsx       # Homepage
│   │   ├── Devices.tsx         # Device management
│   │   ├── Plans.tsx           # Plan approval
│   │   └── AuditLog.tsx        # Audit log viewer
│   ├── App.tsx                 # Main app component with routing
│   ├── main.tsx                # Application entry point
│   └── index.css               # Tailwind CSS imports
├── public/                     # Static assets
├── dist/                       # Production build output (gitignored)
├── tailwind.config.js          # Tailwind CSS configuration
├── vite.config.ts              # Vite configuration
└── package.json                # Dependencies and scripts
```

## Routes

- `/` - Dashboard (landing page)
- `/devices` - Device management interface
- `/plans` - Plan approval workflows
- `/audit` - Audit log viewer

## Development Notes

### Tailwind CSS

The project uses Tailwind CSS v3 with PostCSS. Configuration is in `tailwind.config.js`.

To add custom styles, edit `src/index.css` or use Tailwind utility classes directly in components.

### ESLint

ESLint is configured with React and TypeScript rules. Run linting:

```bash
npm run lint
```

### Type Checking

TypeScript type checking is enabled for both app and build scripts:

```bash
# Check types (part of build process)
npm run build
```

## Backend Integration

This UI is designed to integrate with the RouterOS MCP Python backend via:
- REST API endpoints (planned)
- WebSocket connections for real-time updates (planned)
- OAuth/OIDC authentication (planned)

Backend integration is **not yet implemented** - this is scaffolding only.

## Next Steps

- [ ] Connect to RouterOS MCP REST API
- [ ] Implement device management UI
- [ ] Add plan approval workflow
- [ ] Display real-time audit logs
- [ ] Add authentication/authorization
- [ ] Implement WebSocket subscriptions
- [ ] Add error handling and loading states
