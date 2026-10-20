# Security

FactoryTwin is pre-alpha software intended for execution on a trusted development workstation over loopback only. The HTTP server binds to `127.0.0.1`; no authentication, TLS termination, remote-access security model, or industrial safety interlocks are implemented.

**Do not expose the HTTP server to the public internet, forward it through an untrusted proxy, or connect it to real industrial equipment.** Do not use this prototype to drive actuators or make safety-critical operational decisions.

## Local HTTP boundary

The loopback server applies defensive request and response handling without changing its trusted-local security model:

- `POST /api/control` accepts `application/json` only.
- Control requests require exactly one positive `Content-Length` and are limited to 4096 bytes.
- Transfer-encoded control requests are rejected; the endpoint does not implement chunked request decoding.
- Malformed framing or JSON is rejected before simulator control state is mutated.
- HTTP responses include passive browser hardening headers for MIME sniffing, referrers, framing, cross-origin resource use, base URIs and embedded objects.
- The server does not opt into cross-origin resource sharing.

These checks reduce accidental or browser-originated misuse of the local demo API. They are **not** authentication, authorization, network isolation, TLS, CSRF protection for an internet-facing service, or evidence that the simulator is safe to expose beyond the trusted loopback environment.

For security reports, use a GitHub security advisory when private vulnerability reporting is available. Avoid publishing exploit details before a fix.
