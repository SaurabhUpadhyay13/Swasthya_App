"""Run the same checks as the GitHub CI "lint" and "test" jobs, on your own machine.

    python scripts/check.py

Run it before you push. It stops at the first failing step and exits non-zero, which is
also what lets the pre-push hook (.githooks/pre-push) block a push that would fail CI.
"""

import subprocess
import sys

STEPS = [
    ("Lint (ruff)", [sys.executable, "-m", "ruff", "check", "."]),
    ("Frontend wiring", [sys.executable, "scripts/check_frontend.py"]),
    ("Tests (pytest)", [sys.executable, "-m", "pytest", "-q"]),
]

for number, (name, command) in enumerate(STEPS, start=1):
    print(f"\n=== [{number}/{len(STEPS)}] {name} ===", flush=True)
    if subprocess.run(command).returncode != 0:
        print(f"\nFAILED at step {number}: {name}. Fix it, then run this again.")
        sys.exit(1)

print("\nAll checks passed. Safe to push.")
