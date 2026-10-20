# Software validation scope

FactoryTwin validation is for the software-only simulator. It is not an industrial uptime certification, hardware-in-the-loop qualification, safety validation, or evidence of physical-plant reliability.

## Continuous checks

The normal GitHub Actions Linux matrix runs on Python 3.11 and 3.12 and includes the complete unit suite, wheel build, and installed-package smoke checks. A Windows Python 3.12 source-test job covers filesystem and SQLite portability.

Long-run regression coverage includes:

- a 10,002-step default-line workpiece-identifier/conservation test;
- a 1,200-tick deterministic run with pause and multiple-station fault windows, followed by full trace replay and continued execution equivalence;
- a 400-tick persisted multi-fault session recovered through four separate SQLite reopen cycles, with exact trace equality and genealogy/conservation audits after every reopen.

These scenarios are intentionally deterministic and bounded so failures are reproducible. They exercise state drift, interlock recovery, trace replay, genealogy integrity, workpiece conservation, and persistence/restart behavior without introducing wall-clock performance thresholds.

## Automated local acceptance harness

`python -m factorytwin.acceptance` runs an end-to-end software acceptance scenario using only the Python standard library. The harness launches the real `python -m factorytwin` CLI in a child process, requests an OS-assigned loopback port with `--port 0`, and uses a temporary SQLite database by default.

The acceptance scenario verifies that:

- the server binds only to `127.0.0.1` and reports a healthy simulation source;
- workpieces progress and completed/default-good counts increase;
- a completed workpiece exposes all-GOOD genealogy through the read-only API;
- pause freezes productive processing while observation ticks continue;
- a synthetic station fault interlocks productive processing and `resume` does not bypass it;
- clearing a fault does not override an independent pause;
- both child server processes stop cleanly by interrupt;
- restarting the CLI against the same SQLite file recovers the previous session before the next observation tick;
- completed/good counters and selected genealogy do not regress across restart; and
- productive processing continues after recovery.

Pass `--database PATH` to retain the acceptance database for inspection. The default temporary database is removed after a successful or failed run. The harness does not automate a graphical browser, open a non-loopback listener, or exercise PLC/SCADA/robotics/physical-device interfaces.

The same acceptance scenario is part of `python -m unittest discover -s tests -v`, so it runs in the supported CI source-test jobs, including Windows Python 3.12.

## What this does not establish

Passing these checks does not establish plant availability, real-time deadlines, protocol interoperability, industrial cybersecurity, hardware reliability, or safe control behavior. Performance/resource characterization is tracked separately from correctness validation.
