# Release policy

FactoryTwin is currently pre-alpha, software-only simulator code. Release metadata must not be interpreted as plant validation, hardware compatibility, or production-readiness.

The repository-level release audit is documented in `docs/RELEASE_CHECKLIST.md`. A green checklist means the development branch is technically prepared for a separate release decision; it does not authorize a merge, tag, publication, or physical integration.

## Version source

`factorytwin/_version.py` is the single source of truth. `pyproject.toml` reads that value dynamically when building distributions. The package root does not export `__version__`, so the FT-021 public API contract is unchanged.

The current development version is `0.1.0.dev0`.

## Version format

FactoryTwin uses PEP 440-compatible versions. During the pre-alpha period:

- `X.Y.Z.devN` identifies development builds that are not public releases.
- `X.Y.Z` is reserved for an explicitly approved release candidate that has passed the release-readiness checklist.
- Git tags should use `vX.Y.Z` only for approved releases.

## Python support

Package metadata requires Python 3.11 or newer. The CI support matrix currently validates the complete source suite, wheel build and isolated wheel installation on Python 3.11 and Python 3.12. Newer interpreter minors may satisfy package metadata, but they are not described as CI-tested until they are added to that matrix and pass it.

## Release gates

Before an approved release:

1. The complete unit suite must be green.
2. Wheel build and isolated installation checks must be green.
3. The documented public API contract must remain green.
4. Bounded long-run/recovery validation must remain green.
5. Synthetic performance reporting must remain informational and must not become an industrial or real-time claim.
6. The changelog must describe the candidate.
7. Simulator scope and safety wording must remain accurate.
8. FT-016 physical integration work must remain separated behind its safety-review gate.
9. Promotion to `main`, tagging, or publication requires explicit project-owner approval.

No PyPI publication is currently claimed or automated.
