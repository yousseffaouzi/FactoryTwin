# Release policy

FactoryTwin is currently pre-alpha, software-only simulator code. Release metadata must not be interpreted as plant validation, hardware compatibility, or production-readiness.

## Version source

`factorytwin/_version.py` is the single source of truth. `pyproject.toml` reads that value dynamically when building distributions. The package root does not export `__version__`, so the FT-021 public API contract is unchanged.

The current development version is `0.1.0.dev0`.

## Version format

FactoryTwin uses PEP 440-compatible versions. During the pre-alpha period:

- `X.Y.Z.devN` identifies development builds that are not public releases.
- `X.Y.Z` is reserved for an explicitly approved release candidate that has passed the release-readiness checklist.
- Git tags should use `vX.Y.Z` only for approved releases.

## Python support

Package metadata requires Python 3.11 or newer. A version is only described as CI-tested after the workflow actually runs on that interpreter; metadata support and CI coverage are tracked separately.

## Release gates

Before an approved release:

1. The complete unit suite must be green.
2. Wheel build and isolated installation checks must be green.
3. The documented public API contract must remain green.
4. The changelog must describe the candidate.
5. Simulator scope and safety wording must remain accurate.
6. Promotion to `main`, tagging, or publication requires explicit project-owner approval.

No PyPI publication is currently claimed or automated.
