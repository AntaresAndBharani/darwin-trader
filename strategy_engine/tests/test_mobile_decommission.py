"""
Unit and integration tests for Issue #98: Codebase & Script Deletion.

Verifies the complete decommissioning and removal of legacy Android mobile app,
Maestro E2E tests, local test APK build directories, and obsolete mobile CI scripts.
"""
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]


class TestMobileDecommission:
    """Acceptance criteria tests for Issue #98: Codebase & Script Deletion."""

    def test_android_directory_removed_from_disk(self):
        """Scenario 1: Directory android/ no longer exists on disk."""
        android_dir = REPO_ROOT / "android"
        assert not android_dir.exists(), f"android/ directory should not exist at {android_dir}"

    def test_e2e_directory_removed_from_disk(self):
        """Scenario 1: Directory e2e/ no longer exists on disk."""
        e2e_dir = REPO_ROOT / "e2e"
        assert not e2e_dir.exists(), f"e2e/ directory should not exist at {e2e_dir}"

    def test_local_test_directory_removed_from_disk(self):
        """Scenario 1: Directory local_test/ no longer exists on disk."""
        local_test_dir = REPO_ROOT / "local_test"
        assert not local_test_dir.exists(), f"local_test/ directory should not exist at {local_test_dir}"

    def test_run_e2e_tests_script_removed(self):
        """Scenario 1: scripts/run-e2e-tests.ps1 is removed."""
        script_path = REPO_ROOT / "scripts" / "run-e2e-tests.ps1"
        assert not script_path.exists(), f"run-e2e-tests.ps1 should not exist at {script_path}"

    def test_post_e2e_evidence_script_removed(self):
        """Scenario 1: scripts/post-e2e-evidence.ps1 is removed."""
        script_path = REPO_ROOT / "scripts" / "post-e2e-evidence.ps1"
        assert not script_path.exists(), f"post-e2e-evidence.ps1 should not exist at {script_path}"

    def test_summarize_unit_tests_script_removed(self):
        """Scenario 1: scripts/summarize-unit-tests.ps1 is removed."""
        script_path = REPO_ROOT / "scripts" / "summarize-unit-tests.ps1"
        assert not script_path.exists(), f"summarize-unit-tests.ps1 should not exist at {script_path}"

    def test_release_workflow_removed(self):
        """Scenario 1: .github/workflows/release.yml is deleted."""
        workflow_path = REPO_ROOT / ".github" / "workflows" / "release.yml"
        assert not workflow_path.exists(), f"release.yml should not exist at {workflow_path}"

    def test_git_tracking_clean_for_decommissioned_targets(self):
        """Scenario 1: No deleted files remain in git index tracking."""
        targets = [
            "android",
            "e2e",
            "local_test",
            "scripts/run-e2e-tests.ps1",
            "scripts/post-e2e-evidence.ps1",
            "scripts/summarize-unit-tests.ps1",
            ".github/workflows/release.yml",
        ]
        cmd = ["git", "ls-files"] + targets
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"git ls-files failed: {result.stderr}"
        tracked = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
        assert tracked == [], f"Found tracked files that should have been deleted: {tracked}"

    def test_tui_and_gateway_zero_regression(self):
        """Scenario 4: TUI and API Gateway run independently without mobile dependencies."""
        import api_gateway.main  # noqa: F401
        import tui.app  # noqa: F401
        assert hasattr(api_gateway.main, "app")
        assert hasattr(tui.app, "DarwinTraderApp")
