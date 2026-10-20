# Software validation scope

FactoryTwin validation is for the software-only simulator. It is not an industrial uptime certification, hardware-in-the-loop qualification, safety validation, or evidence of physical-plant reliability.

## Continuous checks

The normal GitHub Actions matrix runs on Python 3.11 and 3.12 and includes the complete unit suite, wheel build, and installed-package smoke checks.

Long-run regression coverage includes:

- a 10,002-step default-line workpiece-identifier/conservation test;
- a 1,200-tick deterministic run with pause and multiple-station fault windows, followed by full trace replay and continued execution equivalence;
- a 400-tick persisted multi-fault session recovered through four separate SQLite reopen cycles, with exact trace equality and genealogy/conservation audits after every reopen.

These scenarios are intentionally deterministic and bounded so failures are reproducible. They exercise state drift, interlock recovery, trace replay, genealogy integrity, workpiece conservation, and persistence/restart behavior without introducing wall-clock performance thresholds.

## What this does not establish

Passing these checks does not establish plant availability, real-time deadlines, protocol interoperability, industrial cybersecurity, hardware reliability, or safe control behavior. Performance/resource characterization is tracked separately from correctness validation.
