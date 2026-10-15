# FT-011 — Local Server-Sent Events streaming

FactoryTwin now exposes `GET /api/stream` as a localhost-only Server-Sent Events (SSE) transport. The stream is supplemental: it does **not** change the long-standing contract that `GET /api/snapshot` advances one observation tick.

## Why SSE

SSE uses the Python standard library HTTP server, needs no WebSocket dependency, and is sufficient for one-way local simulation updates. Every successful snapshot step and control response publishes a detached state frame to a bounded in-memory hub. Publishing is O(1) and never waits for clients.

## Event IDs, reconnect and resync

Transport event IDs are monotonically increasing integers independent of simulation event `seq`, operation `seq`, `tick`, and persisted session identity. Clients may reconnect with the standard `Last-Event-ID` header:

- if missed frames are still in the 64-frame buffer, only newer frames are replayed;
- if the cursor is older than retained history, invalidly in the future, or absent on a fresh connection, the server sends one `event: resync` containing a full current snapshot;
- normal retained updates use `event: snapshot`;
- the resync snapshot is read-only and does not call `step()`.

The server emits periodic SSE comments as keep-alives. Comments are not simulation events.

## Backpressure and bounded resources

Each SSE connection runs in the existing `ThreadingHTTPServer` request thread. A slow or disconnected client may block or terminate only its own writer thread; simulation publishers append to the bounded hub and notify waiters without writing to client sockets. Because the replay buffer is bounded, a sufficiently slow client eventually receives a full resync rather than unbounded queued history.

This is suitable for the localhost demo, not an Internet-scale broker. There is no authenticated remote subscription, external message bus, cloud relay or delivery guarantee.

## Dashboard/fallback contract

The existing polling path remains supported and continues to drive synthetic observation ticks. A browser can use SSE for faster cross-request state updates while retaining `/api/snapshot` polling as the compatibility/fallback mechanism. This avoids making simulation speed depend on the number of connected stream clients.

## Security and persistence

The HTTP server remains bound to `127.0.0.1:8766`. SSE transport frames are not persisted and are not a source of deterministic truth; SQLite operation/event journals and simulation traces remain authoritative for replay. No physical machine or actuator traffic is involved.
