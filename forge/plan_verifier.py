"""Plan step verification — run tests/lint after each plan step.

Modes:
  off     — no verification (default)
  report  — warn on failure but continue
  repair  — attempt auto-fix on failure, then re-verify
  strict  — rollback step on verification failure

The verifier auto-detects the project's test framework (pytest, npm test,
cargo test) and optionally runs linters (ruff, flake8).
"""

import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class VerificationCheck:
    """Result of a single verification check."""
    name: str           # "tests", "lint", "typecheck", "git_diff"
    passed: bool
    output: str = ""
    duration_ms: int = 0


@dataclass
class VerificationResult:
    """Full verification result for a plan step."""
    step_number: int
    passed: bool
    checks: list[VerificationCheck] = field(default_factory=list)
    auto_fixed: bool = False
    rolled_back: bool = False
    error_summary: str = ""

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        checks_str = ", ".join(
            f"{c.name}:{'ok' if c.passed else 'FAIL'}"
            for c in self.checks
        )
        return f"Step {self.step_number}: {status} [{checks_str}]"


class PlanVerifier:
    """Verify plan steps by running tests, lint, and sanity checks."""

    def __init__(self, mode: str = "off",
                 run_tests: bool = True,
                 run_lint: bool = False,
                 run_typecheck: bool = False,
                 run_git_diff: bool = True,
                 max_test_time: int = 30,
                 working_dir: str = "."):
        self.mode = mode
        self.run_tests = run_tests
        self.run_lint = run_lint
        self.run_typecheck = run_typecheck
        self.run_git_diff = run_git_diff
        self.max_test_time = max_test_time
        self.working_dir = working_dir
        self._results: list[VerificationResult] = []

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    def verify_step(self, step_number: int) -> VerificationResult:
        """Run all configured verification checks for a plan step."""
        checks = []

        if self.run_tests:
            checks.append(self._check_tests())

        if self.run_lint:
            checks.append(self._check_lint())

        if self.run_typecheck:
            checks.append(self._check_typecheck())

        if self.run_git_diff:
            checks.append(self._check_git_diff())

        passed = all(c.passed for c in checks) if checks else True
        error_summary = ""
        if not passed:
            failures = [c for c in checks if not c.passed]
            error_summary = "; ".join(
                f"{c.name}: {c.output[:100]}" for c in failures)

        result = VerificationResult(
            step_number=step_number,
            passed=passed,
            checks=checks,
            error_summary=error_summary,
        )
        self._results.append(result)
        return result

    def get_repair_prompt(self, result: VerificationResult,
                          step_title: str) -> str:
        """Generate a prompt for the AI to fix verification failures."""
        failures = [c for c in result.checks if not c.passed]
        details = "\n".join(
            f"- {c.name} FAILED:\n{c.output[:500]}" for c in failures)
        return (
            f"[System: Step '{step_title}' failed verification. "
            f"Fix the following issues:\n{details}\n\n"
            f"Fix these issues now, then the step will be re-verified.]"
        )

    def to_audit_dict(self) -> dict:
        """Return a JSON-serializable audit snapshot.

        Stable API contract for the audit exporter.
        """
        from dataclasses import asdict
        return {
            "schema_version": 1,
            "mode": self.mode,
            "results": [asdict(r) for r in self._results],
        }

    def format_result(self, result: VerificationResult) -> str:
        """Format a single verification result for terminal display."""
        from forge.ui.terminal import GREEN, RED, DIM, RESET, BOLD, YELLOW

        if result.passed:
            icon = f"{GREEN}V{RESET}"
            status = f"{GREEN}VERIFIED{RESET}"
        else:
            icon = f"{RED}X{RESET}"
            status = f"{RED}FAILED{RESET}"

        lines = [f"  {icon} Step {result.step_number}: {status}"]
        for check in result.checks:
            c_icon = f"{GREEN}ok{RESET}" if check.passed else f"{RED}FAIL{RESET}"
            time_str = f" ({check.duration_ms}ms)" if check.duration_ms else ""
            lines.append(f"    {c_icon} {check.name}{time_str}")
            if not check.passed and check.output:
                for line in check.output.strip().splitlines()[:3]:
                    lines.append(f"      {DIM}{line[:80]}{RESET}")

        if result.auto_fixed:
            lines.append(f"    {YELLOW}auto-fixed and re-verified{RESET}")
        if result.rolled_back:
            lines.append(f"    {RED}{BOLD}rolled back{RESET}")

        return "\n".join(lines)

    def format_summary(self) -> str:
        """Format a summary of all verification results."""
        from forge.ui.terminal import GREEN, RED, RESET, BOLD

        if not self._results:
            return ""

        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)

        if passed == total:
            color = GREEN
        else:
            color = RED

        return (
            f"\n  {BOLD}Verification:{RESET} "
            f"{color}{passed}/{total} steps verified{RESET}"
        )

    def _run_command(self, cmd: list[str], timeout: int = 30) -> tuple[int, str]:
        """Run a subprocess command and return (exit_code, output)."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_dir,
            )
            output = result.stdout + result.stderr
            return result.returncode, output[-2000:]  # Truncate
        except subprocess.TimeoutExpired:
            return 1, f"Command timed out after {timeout}s"
        except FileNotFoundError:
            return -1, f"Command not found: {cmd[0]}"
        except Exception as e:
            return -1, str(e)

    def _detect_test_command(self) -> Optional[list[str]]:
        """Auto-detect the project's test command."""
        wd = Path(self.working_dir)

        # Python: pytest
        if (wd / "pytest.ini").exists() or (wd / "pyproject.toml").exists() \
                or (wd / "tests").is_dir() or (wd / "test").is_dir():
            return ["python", "-m", "pytest", "-x", "-q", "--tb=short"]

        # Node: npm test
        if (wd / "package.json").exists():
            return ["npm", "test", "--", "--watchAll=false"]

        # Rust: cargo test
        if (wd / "Cargo.toml").exists():
            return ["cargo", "test"]

        # Go: go test
        if (wd / "go.mod").exists():
            return ["go", "test", "./..."]

        return None

    def _check_tests(self) -> VerificationCheck:
        """Run the project's test suite."""
        start = time.time()
        cmd = self._detect_test_command()
        if cmd is None:
            return VerificationCheck(
                name="tests", passed=True,
                output="No test framework detected — skipped")

        code, output = self._run_command(cmd, timeout=self.max_test_time)
        duration_ms = int((time.time() - start) * 1000)

        return VerificationCheck(
            name="tests",
            passed=(code == 0),
            output=output,
            duration_ms=duration_ms,
        )

    def _check_lint(self) -> VerificationCheck:
        """Run a linter (ruff or flake8)."""
        start = time.time()

        # Try ruff first, then flake8
        for cmd in [["ruff", "check", "."], ["flake8", "."]]:
            code, output = self._run_command(cmd, timeout=15)
            if code != -1:  # Command found
                duration_ms = int((time.time() - start) * 1000)
                return VerificationCheck(
                    name="lint",
                    passed=(code == 0),
                    output=output,
                    duration_ms=duration_ms,
                )

        return VerificationCheck(
            name="lint", passed=True,
            output="No linter available — skipped")

    def _check_typecheck(self) -> VerificationCheck:
        """Run type checker (mypy or pyright)."""
        start = time.time()

        for cmd in [["mypy", "."], ["pyright"]]:
            code, output = self._run_command(cmd, timeout=30)
            if code != -1:
                duration_ms = int((time.time() - start) * 1000)
                return VerificationCheck(
                    name="typecheck",
                    passed=(code == 0),
                    output=output,
                    duration_ms=duration_ms,
                )

        return VerificationCheck(
            name="typecheck", passed=True,
            output="No type checker available — skipped")

    def _check_git_diff(self) -> VerificationCheck:
        """Sanity check: flag mass deletions in git diff."""
        start = time.time()
        code, output = self._run_command(
            ["git", "diff", "--stat", "HEAD"], timeout=10)

        if code != 0:
            return VerificationCheck(
                name="git_diff", passed=True,
                output="Not a git repo or no changes — skipped")

        duration_ms = int((time.time() - start) * 1000)

        # Flag if more than 500 lines deleted without similar additions
        deletions = 0
        insertions = 0
        for line in output.splitlines():
            if "insertion" in line and "deletion" in line:
                # Parse summary line: "N files changed, X insertions, Y deletions"
                import re
                ins = re.search(r"(\d+) insertion", line)
                dels = re.search(r"(\d+) deletion", line)
                if ins:
                    insertions = int(ins.group(1))
                if dels:
                    deletions = int(dels.group(1))

        suspicious = deletions > 500 and deletions > insertions * 3
        return VerificationCheck(
            name="git_diff",
            passed=not suspicious,
            output=(f"+{insertions} -{deletions}"
                    + (" (mass deletion detected!)" if suspicious else "")),
            duration_ms=duration_ms,
        )
