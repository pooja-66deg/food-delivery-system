# Tiffin — Customer Web App

React + TypeScript (Vite) frontend for the Food Delivery Platform. This first
slice covers the **auth + account** flow, matching the backend's users domain:
register, password login, OTP login, profile editing, and delivery addresses.

## Stack

- React 18 + TypeScript
- Vite 5 (dev server + build)
- React Router 6
- Framer Motion (motion/animation)
- Plain CSS design system (`src/index.css`, `src/layout.css`) — Fraunces + Instrument Sans

## Running locally

```bash
npm install
npm run dev        # http://localhost:5173
```

The dev server proxies `/api/*` to the FastAPI backend at `http://localhost:8000`
(see `vite.config.ts`), so start the backend first:

```bash
# from the repo root
uvicorn src.main:app --reload   # needs Postgres + Redis running
```

## Configuration

- `VITE_API_URL` — override the API base (default `/api`, which the dev proxy
  forwards to the backend). Set it for production builds pointing at a real API
  origin. See `.env.example`.
- `VITE_STRIPE_PUBLISHABLE_KEY` — enables card payments. With it unset the card
  option is hidden and cash on delivery is the only method, so the app runs with
  no payment configuration at all.

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start the dev server with hot reload |
| `npm run build` | Type-check (`tsc`) and build to `dist/` |
| `npm run preview` | Serve the production build locally |

## Structure

```
src/
  api/        # typed bindings to the backend (client.ts, auth.ts)
  auth/       # AuthContext: token persistence + current user
  components/ # UI primitives, brand panel, app shell, route guard
  pages/      # LoginPage, RegisterPage, AccountPage
  App.tsx     # routes
  main.tsx    # entry
```
