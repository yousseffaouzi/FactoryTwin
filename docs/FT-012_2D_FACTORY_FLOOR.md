# FT-012 — Accessible 2D factory floor

FT-012 replaces the card-only dashboard with a responsive **2D** representation of the validated linear production route. The visualization remains a browser view over synthetic simulator state; it does not represent measured physical geometry and does not control equipment.

## Layout

The primary factory-floor panel renders stations in blueprint order from material entry to finished output. Desktop layouts use a horizontal route with explicit arrows; small screens reflow to a vertical route. Every station shows its name, textual state, current synthetic workpiece, and cycle progress. The same snapshot also drives KPI cards, metrics, recent genealogy and event feed.

3D is intentionally deferred. The existing product requirement makes 3D optional, and adding WebGL/Three.js would add weight without improving the current linear-route simulation or accessibility baseline.

## Accessibility

The page uses semantic `header`, `main`, `section`, `aside` and `footer` landmarks; a skip link targets the factory floor; native buttons/selects remain keyboard-operable; the station selector has a programmatic label; focus-visible styles are explicit; line/connection status uses live regions; and state is always printed as text rather than communicated by color alone. Cycle indicators expose `role=progressbar` with ARIA values. `prefers-reduced-motion` is respected.

OEE-related fields display an em dash when the backend returns `null`; the visualization never converts undefined denominators into zero percent.

## Streaming and fallback

The browser subscribes to `/api/stream` for low-latency display updates, but `/api/snapshot` continues polling every 1.5 seconds. Polling is deliberately retained because it is the established observation-tick driver and serves as the fallback if `EventSource` is unavailable or disconnected. SSE events only render state and never create extra ticks.

## Security/performance boundary

The dashboard loads no external scripts, fonts, images or CDNs. Snapshot-derived values used in dynamic HTML are escaped. There is no canvas, WebGL or 3D runtime. The server stays loopback-only.

## Visual review

`docs/assets/ft012-floor-desktop.png` is a reproducible Chromium capture of the real `web/index.html` with a fixed synthetic snapshot injected only for rendering review. It demonstrates the desktop route, status text, cycle progress, KPI cards and simulation boundary notice. The capture is documentation evidence, not a physical-factory screenshot.

Static contract tests in `tests/test_web_ui.py` check landmarks, labels, responsive/reduced-motion CSS, polling/SSE fallback, undefined OEE rendering, escaping hooks, local-only frontend resources and absence of a 3D runtime.
