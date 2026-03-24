# Vercel + Cloudflare tunnel — connect frontend to backend

## Current Cloudflare tunnel (quick tunnel)

- **API base URL (HTTPS):** `https://demand-machine-funk-leslie.trycloudflare.com`
- This URL is created by `cloudflared tunnel --url http://127.0.0.1:5000` on the server. **It will change** if the tunnel process restarts (e.g. server reboot). For a stable URL, use a [named Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps) or your own domain in Cloudflare.

## 1. Vercel environment variables

In **Vercel** → your project (360feedbackfe) → **Settings** → **Environment Variables**, set:

| Name | Value | Environment |
|------|--------|-------------|
| `VITE_API_BASE_URL` | `https://demand-machine-funk-leslie.trycloudflare.com` | Production (and Preview if needed) |
| `VITE_USE_MOCK` | `false` | Production (and Preview if needed) |

Then **redeploy** the frontend (Deployments → … → Redeploy) so the build picks up the new env.

## 2. Backend CORS (on server)

The API must allow requests from the Vercel origin. On the server, in `backend/.env`, set:

```bash
CORS_ORIGINS=https://360feedbackfe.vercel.app
```

If you use a custom domain for the frontend, add it too (comma-separated). Then restart the API:

```bash
ssh root@164.52.215.113 "cd /opt/360-feedback && set -a && . backend/.env; set +a; docker compose restart api"
```

## 3. Check that Vercel is connecting to the server

1. Open https://360feedbackfe.vercel.app and sign in (or try sign in).
2. If login works and you see data, the frontend is talking to the backend.
3. If you see network errors or “CORS” in the browser console, confirm `CORS_ORIGINS` on the server includes `https://360feedbackfe.vercel.app` and that `VITE_API_BASE_URL` is set in Vercel and the app was redeployed.

## 4. If the Cloudflare URL changed

If the tunnel was restarted, get the new URL from the server:

```bash
ssh root@164.52.215.113 "grep -oE 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' /tmp/cf-tunnel.log | tail -1"
```

Update `VITE_API_BASE_URL` in Vercel to that URL and redeploy. To keep the tunnel running across reboots, run cloudflared as a systemd service or use a named tunnel with a fixed hostname.
