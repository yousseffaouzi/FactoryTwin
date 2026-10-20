# Changelog

FactoryTwin is pre-alpha software. This file records software-release readiness changes; it does not imply industrial validation or a production release.

## Unreleased

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
- README now documents trusted-checkout installation, validation boundaries, and the explicit release-decision gate.

## 0.1.0.dev0

Current development version. No stable public release or PyPI publication is claimed for this version.
