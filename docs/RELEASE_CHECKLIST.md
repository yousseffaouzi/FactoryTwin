# Software release-readiness checklist

This checklist audits the **software-only FactoryTwin simulator**. Passing it does not establish industrial safety, physical digital-twin validation, PLC/SCADA interoperability, hardware compatibility, real-time behavior, or plant readiness.

## Current checkpoint

The approved software release is `0.1.0` / `v0.1.0`. The active development line is `0.2.0.dev0`, which is not an approved release and must not be represented as one. The v0.1.0 approvals recorded below apply only to that released checkpoint; they do not authorize a future v0.2.0 release, package-registry publication, or FT-016 physical integration work.

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
- [x] `CHANGELOG.md` records v0.1.0 release history and the post-release development line.
- [x] `README.md` states pre-alpha, loopback-only, synthetic-data and non-industrial-control boundaries.
- [x] Runtime dependency metadata remains empty; the simulator/server runtime stays standard-library oriented.
- [x] FT-016 physical PLC/SCADA/robotics/plant integration remains `ON HOLD` pending a separate safety review.

## Historical v0.1.0 manual approvals

- [x] Explicit project-owner approval to promote or merge into `main`: **approved 2026-10-20**.
- [x] Explicit approval of non-development version `0.1.0`: **approved 2026-10-20**.
- [x] Explicit approval to create Git tag / GitHub release `v0.1.0`: **approved 2026-10-20**.
- [ ] Package-registry publication: **not part of v0.1.0; separate approval required**.
- [ ] Separate safety/security review before any FT-016 physical integration work.

Future releases, package publication, or physical integration work require their own explicit approvals. FactoryTwin v0.1.0 and the `0.2.0.dev0` development line must not be represented as production-ready industrial digital twins.

## Evidence to record for future release candidates

Record the candidate commit SHA, both supported Python job results, exact test count, wheel filename, installed-wheel smoke result, changelog entry, version/tag decision, and confirmation that scope/safety wording still matches executable capabilities.
