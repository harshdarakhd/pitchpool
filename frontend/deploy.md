# Frontend deployment

Production uses **same-origin** hosting: the root `Dockerfile` builds this app with `VITE_API_URL=` (empty) and copies `dist/` into the FastAPI container as `./static`.

## Production (Render)

No separate frontend host. See [../docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md).

- Build: `npm run build` (runs inside Docker stage 1)
- Output: `dist/` → served by FastAPI at `/`
- API: relative paths `/api/v1/…`
- WebSocket: `wss://<host>/ws` (see `src/hooks/useRealtime.ts`)

## Local development

```bash
npm install
npm run dev
```

Vite proxies `/api` and `/ws` to the backend (default port 8001 in `vite.config.ts`).

## Optional split hosting (not recommended for Render Free)

If you deploy the API elsewhere and static files on CDN:

- Build command: `npm run build`
- Output directory: `dist`
- Set `VITE_API_URL=https://your-api.example.com` at build time
- Configure API `CORS_ORIGINS` and cookie domain accordingly (cross-origin auth is harder than same-origin)
