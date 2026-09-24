"""
Unit and integration tests for Issue #99: Pipeline, Workflow, Agent Governance, Prompts & Documentation Alignment.

Verifies:
- Script and build pipeline alignment (run-three-amigos-and-dev-test.ps1, build.yml, dev-test.yml)
- Clean docstrings in api_gateway/main.py
- Documentation & gitignore modernization
- Agent rules, prompts, tasks, and issue template alignment
- Preserved TUI launcher & backend health
- Zero-dangling-mobile cleanliness gate (Scenario 7)
"""
from pathlib import Path
import subprocess
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


class TestPipelineGovernanceAlignment:
    """Acceptance criteria tests for Issue #99."""

    def test_local_pipeline_synopsis_and_runner_python_suites(self):
        """Scenario 2: run-three-amigos-and-dev-test.ps1 runs Python & TUI suites only."""
        script_path = REPO_ROOT / "scripts" / "local-pipeline" / "run-three-amigos-and-dev-test.ps1"
        assert script_path.exists(), f"Script not found at {script_path}"
        content = script_path.read_text(encoding="utf-8")

        # Synopsis references Python backend and TUI test suites
        assert "Runs Python backend and TUI test suites." in content

        # Pytest invocation includes tui/tests
        assert "api_gateway/tests" in content and "strategy_engine/tests" in content and "tui/tests" in content

        # Android variables and invocations removed
        assert "$android" + "Gradle" not in content
        assert "$android" + "Dir" not in content
        assert "$android" + "Tests" not in content

        # Exit code check only inspects pythonTests
        assert "$pythonTests.ExitCode -ne 0" in content
        assert ("Android: $(" + "$androidTests") not in content

    def test_build_workflow_contract(self):
        """Scenario 3: .github/workflows/build.yml is hard-gated Python CI preserving names."""
        build_yml = REPO_ROOT / ".github" / "workflows" / "build.yml"
        assert build_yml.exists()
        content = build_yml.read_text(encoding="utf-8")

        # Preserves branch protection names
        assert "name: Build APK & CI" in content
        assert "jobs:\n  build:" in content or "jobs:\r\n  build:" in content

        # Python 3.11 setup
        assert "actions/setup-python@v5" in content
        assert "python-version: '3.11'" in content

        # Hard gated pytest (no continue-on-error)
        assert "continue-on-error" not in content
        assert "pytest api_gateway/tests strategy_engine/tests tui/tests" in content

        # No JDK, Gradle, or APK packaging steps
        assert "actions/setup-java" not in content
        assert ("grad" + "le") not in content.lower()
        assert "assemble" not in content.lower()

    def test_dev_test_workflow_no_jdk_step(self):
        """Scenario 3: .github/workflows/dev-test.yml has no obsolete JDK setup."""
        dev_test_yml = REPO_ROOT / ".github" / "workflows" / "dev-test.yml"
        assert dev_test_yml.exists()
        content = dev_test_yml.read_text(encoding="utf-8")

        assert "actions/setup-java" not in content
        assert "JDK" not in content

    def test_api_gateway_main_docstrings_cleaned(self):
        """api_gateway/main.py docstrings and comments cleaned of legacy mobile references."""
        main_py = REPO_ROOT / "api_gateway" / "main.py"
        assert main_py.exists()
        content = main_py.read_text(encoding="utf-8")

        # Lines 16, 20, 47 cleaned
        assert "Android Mobile App" not in content
        assert "Android App" not in content
        assert "FastAPI Bridge connecting Python MT5 Strategy Engine" in content

    def test_tui_launcher_exists(self):
        """Scenario 4: TUI launcher script exists."""
        launcher = REPO_ROOT / "scripts" / "run-tui.ps1"
        assert launcher.exists(), f"run-tui.ps1 should exist at {launcher}"

    def test_documentation_and_gitignore_alignment(self):
        """Scenario 5: README, GEMINI, architecture, and gitignore aligned to Python TUI."""
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        gemini = (REPO_ROOT / "GEMINI.md").read_text(encoding="utf-8")
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        arch = (REPO_ROOT / ".graph" / "architecture.md").read_text(encoding="utf-8")

        # gitignore has no obsolete Android or local test ignore rules
        assert ("android/" + "app/build/") not in gitignore
        assert ("local_" + "test/") not in gitignore
        assert ("*.apk") not in gitignore
        assert ("*.keystore") not in gitignore

        # README and GEMINI reflect pure Python TUI and pytest
        forbidden_in_docs = [
            "".join(["grad", "lew"]),
            "".join(["mae", "stro"]),
            "".join(["local_", "test"]),
            "".join(["post-", "e2e-evidence"]),
            "".join(["run-", "e2e-tests"]),
        ]
        for term in forbidden_in_docs:
            assert term not in readme.lower(), f"Forbidden term '{term}' found in README.md"
            assert term not in gemini.lower(), f"Forbidden term '{term}' found in GEMINI.md"
            assert term not in arch.lower(), f"Forbidden term '{term}' found in architecture.md"

    def test_agent_rules_and_prompts_alignment(self):
        """Scenario 6: Agent rules, tasks, CI prompts, and templates free of mobile commands."""
        files_to_check = [
            REPO_ROOT / ".antigravity" / "rules.md",
            REPO_ROOT / ".antigravity" / "agents" / "developer.md",
            REPO_ROOT / ".antigravity" / "agents" / "tester.md",
            REPO_ROOT / ".antigravity" / "tasks" / "backlog-triage.md",
            REPO_ROOT / ".antigravity" / "tasks" / "dev-test-fixup.md",
            REPO_ROOT / ".antigravity" / "tasks" / "dev-test-implement.md",
            REPO_ROOT / ".antigravity" / "tasks" / "dev-test.md",
            REPO_ROOT / ".antigravity" / "tasks" / "three-amigos.md",
            REPO_ROOT / ".github" / "workflows" / "prompts" / "dev-test-implement.md",
            REPO_ROOT / ".github" / "workflows" / "prompts" / "dev-test-fixup.md",
            REPO_ROOT / ".github" / "workflows" / "prompts" / "architect-decompose.md",
            REPO_ROOT / ".github" / "workflows" / "prompts" / "pr-review.md",
            REPO_ROOT / ".github" / "workflows" / "prompts" / "three-amigos.md",
            REPO_ROOT / ".claude" / "tasks" / "architect-decompose.md",
            REPO_ROOT / ".claude" / "tasks" / "architect-restructure.md",
            REPO_ROOT / ".claude" / "tasks" / "pr-review.md",
            REPO_ROOT / ".claude" / "tasks" / "three-amigos-judge.md",
            REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "subtask.yml",
            REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "user-story.yml",
        ]

        forbidden = [
            "".join(["grad", "lew"]),
            "".join(["mae", "stro"]),
            "".join(["run-", "e2e-tests"]),
            "".join(["post-", "e2e-evidence"]),
            "".join(["summarize-", "unit-tests"]),
            "/".join(["android", "app"]),
            "".join(["local_", "test"]),
        ]

        for file_path in files_to_check:
            assert file_path.exists(), f"File missing: {file_path}"
            content = file_path.read_text(encoding="utf-8").lower()
            for term in forbidden:
                assert term not in content, f"Forbidden pattern '{term}' found in {file_path.name}"

    def test_repo_wide_cleanliness_gate_scenario_7(self):
        """Scenario 7: Objective repo-wide zero-dangling-mobile cleanliness gate."""
        pattern_parts = [
            "".join(["grad", "lew"]),
            "".join(["mae", "stro"]),
            "".join(["run-", "e2e-tests"]),
            "".join(["post-", "e2e-evidence"]),
            "".join(["summarize-", "unit-tests"]),
            "/".join(["android", "app"]),
            "".join(["local_", "test"]),
        ]
        pattern = "|".join(pattern_parts)
        cmd = [
            "git",
            "grep",
            "-i",
            "-E",
            pattern,
            "--",
            ":^CHANGELOG.md",
            ":^docs/draft-requisites/archive",
            ":^docs/draft-requisites/implementation-plan.md",
        ]
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        assert result.returncode == 1, (
            f"Scenario 7 gate failed! Expected returncode 1 (0 matches), got {result.returncode}.\n"
            f"Matches found:\n{result.stdout}"
        )
