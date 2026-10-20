# Changelog

FactoryTwin is pre-alpha software. This file records software-release readiness changes; it does not imply industrial validation or a production release.

## Unreleased

### Added
- Installable PEP 517/621 package metadata and wheel validation.
- Explicit public Python API compatibility documentation and regression coverage.
- Packaged zero-build dashboard asset and `factorytwin` console entry point.

### Changed
- Simulator internals were separated into deterministic engine, genealogy/fault layers, and explicit runtime composition while preserving the documented public import surface.
- GitHub Actions now use Node-24-era action majors and validate a built wheel in a clean virtual environment.

## 0.1.0.dev0

Current development version. No stable public release or PyPI publication is claimed for this version.
