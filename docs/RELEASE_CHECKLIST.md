# Software release-readiness checklist

This checklist audits the **software-only FactoryTwin simulator**. Passing it does not establish industrial safety, physical digital-twin validation, PLC/SCADA interoperability, hardware compatibility, real-time behavior, or plant readiness.

## Current checkpoint

The development line remains `0.1.0.dev0` pre-alpha software. A green checklist means the development branch is technically prepared for a separate release decision; it is **not** approval to merge `main`, create a release tag, publish a package, or start physical integration work.

## Automated gates

The normal GitHub Actions matrix must keep all of the following green:

- [x] Exact source test command: `python -m unittest discover -s tests -v`.
- [x] Python 3.11 and Python 3.12 jobs.
- [x] Wheel build from the checked-out source.
- [x] Isolated wheel installation from outside the repository checkout.
- [x] Package/public API identity and packaged dashboard smoke checks.
- [x] CLI checks for both `python -m factorytwin` and the `factorytwin` console entry point.
- [x] Bounded long-run deterministic replay and SQLite reopen/recovery validation.
- [x] Synthetic benchmark reporting on Python 3.12 with no throughput pass/fail threshold.

## Repository contract gates

- [x] `docs/PUBLIC_API.md` defines the supported Python import surfaces.
- [x] `docs/VALIDATION.md` defines the bounded software-correctness validation scope.
- [x] `docs/PERFORMANCE.md` defines the synthetic benchmark interpretation boundary.
- [x] `docs/RELEASES.md` defines versioning and approval policy.
- [x] `CHANGELOG.md` records unreleased software changes.
- [x] `README.md` states pre-alpha, loopback-only, synthetic-data and non-industrial-control boundaries.
- [x] Runtime dependency metadata remains empty; the simulator/server runtime stays standard-library oriented.
- [x] FT-016 physical PLC/SCADA/robotics/plant integration remains `ON HOLD` pending a separate safety review.

## Manual release-decision gates

These are deliberately **not** performed by this checklist:

- [ ] Explicit project-owner approval to promote or merge into `main`.
- [ ] Explicit approval of a non-development version number.
- [ ] Explicit approval to create a Git tag or GitHub release.
- [ ] Explicit approval of any package-registry publication.
- [ ] Separate safety/security review before any FT-016 physical integration work.

Until those approvals occur, keep the development version in a PEP 440 development form such as `0.1.0.dev0`, do not advertise a stable public release, and do not represent FactoryTwin as a production-ready industrial digital twin.

## Evidence to record for a release candidate

When a release is explicitly authorized, record the candidate commit SHA, both supported Python job results, exact test count, wheel filename, installed-wheel smoke result, changelog entry, version/tag decision, and a confirmation that scope/safety wording still matches the executable capabilities.
