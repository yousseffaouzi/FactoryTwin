# Changelog

FactoryTwin is pre-alpha software. This file records software-release readiness changes; it does not imply industrial validation or production readiness.

## Unreleased

### Changed
- Development resumed after v0.1.0 on version line `0.2.0.dev0`; this development version is not an approved release, tag, or package-registry publication.
- Release-history guardrails now distinguish the immutable v0.1.0 software release from subsequent development commits.

No simulator behavior or physical-integration scope changes are introduced by this checkpoint.

## 0.1.0 - 2026-10-20

First approved software-only pre-alpha release.

### Added
- Installable PEP 517/621 package metadata and isolated wheel validation.
- Explicit public Python API compatibility documentation and regression coverage.
- Packaged zero-build dashboard asset and `factorytwin` console entry point.
- Python 3.11/3.12 support matrix with full source, wheel and installed-package gates.
- Bounded long-run replay and SQLite reopen/recovery validation.
- Environment-tagged synthetic performance/resource reporting with no speed threshold.
- Keyboard-accessible read-only workpiece genealogy inspector in the browser demo.
- Software release-readiness checklist and repository-level guardrail tests.

### Changed
- Simulator internals were separated into deterministic engine, genealogy/fault layers, and explicit runtime composition while preserving the documented public import surface.
- GitHub Actions now use Node-24-era action majors and validate a built wheel in a clean virtual environment.
- README documents trusted-checkout installation, validation boundaries, and explicit release approval gates.

### Release boundary
- v0.1.0 remains pre-alpha research/demo software and is not a production-ready industrial digital twin, PLC/SCADA controller, safety system, or wire-compatible OPC UA server.
- Package-registry publication is not part of this release.
