# tc-ui

Engineering TC — **Personal Engineering AI / Engineering Command Center** frontend.

Step 5, Phase 5.1: design system foundation. This is a **client** of the
existing orchestrator (Steps 3/4). The browser never executes shell commands,
never reaches the Rust daemon directly, and never stores secrets/API keys.

## Visual identity

A distinctive **green / mint / teal** identity — not a dark hacker terminal,
not a blue corporate dashboard. Light, premium, futuristic foundation.

- TC Green `#35E58C` · Deep Emerald `#0B8F62` · Mint `#8FFFD0` · Teal `#25C7B5`
- Background `#F4FBF7` (warm off-white / pale mint) · Surface `#FFFFFF` · Text `#10231B`
- Gradients are reserved for small identity elements and the **TC Orb** only.

## Stack (lightweight)

Next.js 14 (app router) · React 18 · Tailwind CSS · Radix primitives (Dialog,
Tooltip) · Lucide icons · Framer Motion. **No Three.js / WebGL.**

## Structure

```
src/
  app/                  layout (fonts, metadata, PWA), home (design-system showcase), globals.css
  design/tokens.ts      typed token mirror (motion, orb colors)
  lib/
    api/orchestrator.ts  typed client mapping the REAL backend routes (no fakes)
    api/demo-data.ts     DEMO fixtures (clearly labeled; not production state)
    cn.ts, motion.ts     utilities + motion presets (reduced-motion aware)
  components/
    primitives/         Button, Input, Textarea, Badge, StatusPill, IconButton,
                        Card, Modal, Sheet, Skeleton, Spinner, Divider, Tooltip
    signature/          TCOrb, ActivityTimeline, ToolCallCard, ApprovalCard,
                        TaskRow, ConnectionIndicator
public/
  manifest.webmanifest   PWA manifest (Engineering TC / TC / standalone / green theme)
  icons/                 placeholder SVG icons (green identity)
```

## Design tokens

CSS variables in `src/app/globals.css` (single source of truth) mapped into
Tailwind via `tailwind.config.ts`: colors, radii, shadows, spacing, typography,
motion (durations + spring/smooth easings), and z-index.

## TC Orb

The signature identity visualization (`signature/TCOrb.tsx`). Pure SVG + CSS
(no WebGL). Six states — `idle` (breathing), `thinking` (rotating structures),
`executing` (directional energy), `waiting` (amber/green pulse), `success`
(energetic confirmation), `error` (restrained red). Decorative motion is fully
suppressed under `prefers-reduced-motion`; state changes remain instant.

## Accessibility & responsiveness

WCAG 2.1 AA-oriented: semantic HTML, keyboard navigation, visible focus rings,
aria labels, 44px+ touch targets (`tap-target`), reduced-motion support.
Mobile-first: primary 390×844, min 360×640, scales to 1440+. Safe-area insets,
no horizontal overflow, keyboard-safe composer areas.

## Backend integration

`OrchestratorClient` (`lib/api/orchestrator.ts`) maps the real orchestrator
routes (`/health`, `/v1/tasks`, `/v1/tasks/{id}`, `/v1/tasks/{id}/events`,
`/v1/tasks/{id}/pending_approval`, `…/approve`, `…/reject`). The owner token
returned on task creation is kept in memory (React state) for the session —
never persisted to `localStorage`, never logged.

## Development

```bash
npm install
npm run dev        # http://localhost:3000
npm run typecheck  # tsc --noEmit
npm run lint       # next lint
npm run format     # prettier --check .
npm run build      # next build
```

`NEXT_PUBLIC_ORCH_API` sets the orchestrator base URL (e.g. `http://localhost:8080`).

## Status

Phase 5.2 — **VERIFIED**: Command Center + responsive app shell wired to the real
orchestrator. typecheck, lint, prettier, production build, dev-server route
checks (200), and real API integration via the `/api` proxy all pass.

Routes: `/` (Command Center), `/tasks`, `/tasks/[id]`, `/approvals`, `/system`.

Run against the real orchestrator:

```bash
# 1. start the orchestrator (in-memory) + daemon (Step 2)
cd ../tc-orchestrator && PYTHONPATH=src TC_DAEMON_ADDR=127.0.0.1:50051 \
  TC_REQUIRE_APPROVAL=true python -m uvicorn tc_orchestrator.api:create_app \
  --factory --port 8090
# 2. start the UI with the proxy pointed at it
cd ../tc-ui && ORCH_API_URL=http://127.0.0.1:8090 npm run dev
```

### Known limitations (backend gaps, not faked)

- No backend list-tasks endpoint → Tasks shows the current session's tasks.
- No streaming → Phase 5 polling (stops on terminal).
- No global approvals endpoint → Approvals shows the session's pending tasks.
- Brain status not exposed → not shown on System.
- Full success/approval E2E needs a `BRAIN_API_KEY` (set on the orchestrator).
  See `ENGINEERING_TC_STATUS.md` for details.
