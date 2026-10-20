# Release policy

FactoryTwin is pre-alpha, software-only simulator code. Release metadata must not be interpreted as plant validation, hardware compatibility, industrial safety certification, or production readiness.

The repository-level release audit is documented in `docs/RELEASE_CHECKLIST.md`. Passing that checklist establishes software-release evidence only.

## Current release

The current approved software release is `0.1.0` (`v0.1.0` when tagged).

On 2026-10-20 the project owner explicitly authorized promotion of the validated software line to `main`, use of the non-development version `0.1.0`, and creation of the `v0.1.0` Git tag / GitHub release. Package-registry publication was not authorized as part of this release.

## Version source

`factorytwin/_version.py` is the single source of truth. `pyproject.toml` reads that value dynamically when building distributions. The package root does not export `__version__`, so the FT-021 public API contract is unchanged.

## Version format

FactoryTwin uses PEP 440-compatible versions:

- `X.Y.Z.devN` identifies development builds that are not releases.
- `X.Y.Z` identifies an explicitly approved software release that passed the release-readiness checklist.
- Git tags use `vX.Y.Z` for approved tagged releases.

A non-development version does not mean industrial maturity or stable plant-control suitability. The project remains pre-alpha research/demo software until its documentation explicitly says otherwise.

## Python support

Package metadata requires Python 3.11 or newer. The CI support matrix validates the complete source suite, wheel build and isolated wheel installation on Python 3.11 and Python 3.12. Newer interpreter minors may satisfy package metadata, but they are not described as CI-tested until they are added to that matrix and pass it.

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
9. Promotion to `main`, tagging, GitHub release creation, or package publication requires explicit project-owner approval for that action.

No PyPI publication is approved or automated for v0.1.0.
