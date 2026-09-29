#!/usr/bin/env python3
"""
LEDGER-ORBIT: Run all unit and integration tests.

Usage:
    python scripts/run_tests.py            # all tests
    python scripts/run_tests.py --unit     # unit tests only
    python scripts/run_tests.py --int      # integration tests only
    python scripts/run_tests.py --cov      # with coverage report
"""

import subprocess
import sys
import os


def main() -> None:
    args = sys.argv[1:]

    # Set PYTHONPATH to project root so packages can be imported
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["ORBIT_ENVIRONMENT"] = "test"
    env["ORBIT_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    pytest_args = ["python", "-m", "pytest", "-v", "--tb=short"]

    if "--unit" in args:
        pytest_args.append("tests/unit/")
    elif "--int" in args:
        pytest_args.append("tests/integration/")
    else:
        pytest_args.append("tests/")

    if "--cov" in args:
        pytest_args.extend([
            "--cov=packages",
            "--cov=apps",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
        ])

    print(f"Running: {' '.join(pytest_args)}")
    result = subprocess.run(pytest_args, env=env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
