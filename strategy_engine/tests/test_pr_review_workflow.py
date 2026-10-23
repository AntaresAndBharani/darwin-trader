"""Deterministic contract & behavioral tests for .github/workflows/pr-review.yml."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PR_REVIEW_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-review.yml"
MERGE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "merge.yml"


@pytest.fixture(scope="module")
def workflow_raw() -> str:
    assert PR_REVIEW_WORKFLOW.exists(), f"Missing {PR_REVIEW_WORKFLOW}"
    return PR_REVIEW_WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow_doc(workflow_raw: str) -> dict[str, Any]:
    doc = yaml.safe_load(workflow_raw)
    assert isinstance(doc, dict)
    return doc


def _get_steps(workflow_doc: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = workflow_doc.get("jobs", {})
    assert "pr-review" in jobs
    steps = jobs["pr-review"].get("steps", [])
    assert isinstance(steps, list)
    return steps


def _get_step_by_id(workflow_doc: dict[str, Any], step_id: str) -> dict[str, Any]:
    for step in _get_steps(workflow_doc):
        if step.get("id") == step_id:
            return step
    raise AssertionError(f"Step with id={step_id!r} not found in pr-review.yml")


def test_us1_concurrency_disables_self_cancellation(workflow_doc: dict[str, Any]) -> None:
    """FR-001: Per-PR concurrency group must set cancel-in-progress: false."""
    concurrency = workflow_doc.get("concurrency", {})
    assert concurrency.get("cancel-in-progress") is False
    group = str(concurrency.get("group", ""))
    assert "pr-review-" in group
    assert "pull_request.number" in group


def test_us1_self_healing_labels_and_story_closure(workflow_doc: dict[str, Any]) -> None:
    """FR-003, FR-004, FR-007: Workflow idempotently ensures labels and closes parent stories."""
    meta_step = _get_step_by_id(workflow_doc, "meta")
    meta_run = meta_step.get("run", "")
    assert 'gh label create "status:needs-po-input"' in meta_run
    assert "--force" in meta_run

    verdict_step = _get_step_by_id(workflow_doc, "verdict_step")
    verdict_run = verdict_step.get("run", "")
    assert "def ensure_label(" in verdict_run
    assert "'gh', 'label', 'create'" in verdict_run
    assert "'--force'" in verdict_run
    assert "followup_backlog_issues" in verdict_run

    story_step = _get_step_by_id(workflow_doc, "close_story_step")
    story_run = story_step.get("run", "")
    assert 'gh label create "status:done"' in story_run
    assert "OPEN_SIBLINGS" in story_run
    assert 'gh issue close "$STORY"' in story_run


def test_us1_verdict_python_helper_creates_labels_and_followups(tmp_path: Path) -> None:
    """FR-003, FR-004: Inline verdict helper ensures labels before applying verdict and filing issues."""
    output_json = tmp_path / "pr_review_output.json"
    github_output = tmp_path / "github_output.txt"
    payload = {
        "verdict": "APPROVED",
        "fixes_applied": True,
        "summary": "Fixed edge cases.",
        "pr_comment_markdown": "### Detailed Review\nAll tests pass.",
        "blocking_issues": [],
        "followup_backlog_issues": [
            {
                "title": "Refactor pagination cursor",
                "body": "Add keyset pagination.",
                "labels": ["tech-debt", "enhancement"],
            }
        ],
    }
    output_json.write_text(json.dumps(payload), encoding="utf-8")

    recorded_cmds: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool = False, **kwargs: Any) -> Any:
        recorded_cmds.append(list(cmd))

        class _Result:
            returncode = 0

        return _Result()

    env = {
        "REPO": "AntaresAndBharani/darwin-trader",
        "PR_NUMBER": "138",
        "FIX_PUSHED": "true",
        "CURRENT_SHA": "32dde4e7b04883e0c759301e3cc0adb4b0e6dcbb",
        "PR_REVIEW_OUTPUT_PATH": str(output_json),
        "GITHUB_OUTPUT": str(github_output),
    }

    verdict_step = _get_step_by_id(
        yaml.safe_load(PR_REVIEW_WORKFLOW.read_text(encoding="utf-8")),
        "verdict_step",
    )
    run_script = verdict_step["run"]
    marker_start = "python3 - <<'PY'"
    marker_end = "\nPY"
    assert marker_start in run_script and marker_end in run_script
    py_code = run_script.split(marker_start, 1)[1].split(marker_end, 1)[0]

    with patch("subprocess.run", side_effect=fake_run), patch.dict("os.environ", env, clear=False):
        exec(compile(py_code, "<verdict_step_py>", "exec"), {})

    label_creates = [c for c in recorded_cmds if c[:3] == ["gh", "label", "create"]]
    created_label_names = [c[3] for c in label_creates]
    assert "review:approved" in created_label_names
    assert "tech-debt" in created_label_names
    assert "enhancement" in created_label_names

    pr_edits = [c for c in recorded_cmds if c[:3] == ["gh", "pr", "edit"] and "--add-label" in c]
    assert any("review:approved" in c for c in pr_edits)

    issue_creates = [c for c in recorded_cmds if c[:3] == ["gh", "issue", "create"]]
    assert len(issue_creates) == 1
    assert "Refactor pagination cursor" in issue_creates[0]


def test_us2_merge_only_fast_path_routing_and_step_guards(workflow_doc: dict[str, Any]) -> None:
    """FR-002, SC-002: [skip pr-review] with APPROVED verdict triggers merge_only fast-path."""
    meta_step = _get_step_by_id(workflow_doc, "meta")
    meta_run = meta_step.get("run", "")
    assert "[skip pr-review]" in meta_run
    assert "merge_only=true" in meta_run
    assert "merge_only=false" in meta_run

    guarded_step_names = {
        "Checkout PR branch",
        "Set up Python 3.11",
        "Install Python dependencies",
        "Set up Node.js 20",
        "Install Frontend dependencies",
        "Fetch PR context",
        "Run PR Review & Auto-Fix (Claude Opus 5.5 High)",
    }
    steps = _get_steps(workflow_doc)
    matched_names = set()
    for step in steps:
        name = step.get("name", "")
        if name in guarded_step_names:
            matched_names.add(name)
            cond = str(step.get("if", ""))
            assert "steps.meta.outputs.skip != 'true'" in cond
            assert "steps.meta.outputs.merge_only != 'true'" in cond

    assert matched_names == guarded_step_names

    verdict_step = _get_step_by_id(workflow_doc, "verdict_step")
    verdict_cond = str(verdict_step.get("if", ""))
    assert "steps.meta.outputs.merge_only == 'true'" in verdict_cond


def test_us3_exact_sha_ci_polling_failure_fallback_and_merge_yml_retired(
    workflow_doc: dict[str, Any],
) -> None:
    """FR-005, FR-006, FR-008, SC-003, SC-004: Exact-SHA CI gate, failure transition, and retired merge.yml."""
    assert not MERGE_WORKFLOW.exists(), ".github/workflows/merge.yml must be deleted (FR-008)"

    merge_step = _get_step_by_id(workflow_doc, "merge_step")
    merge_run = merge_step.get("run", "")
    assert '--commit "$CURRENT_SHA"' in merge_run
    assert "seq 1 60" in merge_run
    assert 'CI_PASSED="true"' in merge_run
    assert 'if [ "$CI_PASSED" != "true" ]; then' in merge_run
    assert "review:changes-requested" in merge_run
    assert 'gh pr merge "$PR_NUMBER" -R "$REPO" --squash --delete-branch' in merge_run


def test_us2_merge_only_requires_exact_approved_verdict_header(workflow_doc: dict[str, Any]) -> None:
    """FR-002: A CHANGES_REQUESTED review whose body mentions 'APPROVED' must not enter merge_only."""
    meta_run = _get_step_by_id(workflow_doc, "meta").get("run", "")
    assert '== *"PR Review Verdict: **APPROVED**"*' in meta_run
    assert '== *"APPROVED"*' not in meta_run

    verdict_run = _get_step_by_id(workflow_doc, "verdict_step").get("run", "")
    assert "### PR Review Verdict: **{verdict}**" in verdict_run


def _ci_status_jq(workflow_doc: dict[str, Any]) -> str:
    merge_run = _get_step_by_id(workflow_doc, "merge_step").get("run", "")
    prefix = "CI_STATUS_JQ='"
    assert prefix in merge_run
    return merge_run.split(prefix, 1)[1].split("'\n", 1)[0]


@pytest.mark.parametrize(
    ("runs", "expected"),
    [
        ([], ""),
        ([{"status": "in_progress", "conclusion": ""}], "in_progress"),
        ([{"status": "completed", "conclusion": "success"}], "completed:success"),
        (
            [
                {"status": "completed", "conclusion": "success"},
                {"status": "queued", "conclusion": ""},
            ],
            "in_progress",
        ),
        (
            [
                {"status": "completed", "conclusion": "success"},
                {"status": "completed", "conclusion": "failure"},
            ],
            "completed:failure",
        ),
        ([{"status": "completed", "conclusion": "startup_failure"}], "completed:startup_failure"),
    ],
)
def test_us3_ci_status_aggregates_every_run_for_commit(
    workflow_doc: dict[str, Any], runs: list[dict[str, str]], expected: str
) -> None:
    """FR-005: push + pull_request CI runs on the same SHA must all succeed before merging."""
    jq_bin = shutil.which("jq")
    if jq_bin is None:
        pytest.skip("jq not installed")
    result = subprocess.run(
        [jq_bin, "-r", _ci_status_jq(workflow_doc)],
        input=json.dumps(runs),
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == expected


def test_us3_merge_guards_against_unreviewed_head_commits(workflow_doc: dict[str, Any]) -> None:
    """FR-006: With cancel-in-progress disabled, merge only the exact reviewed & CI-verified SHA."""
    merge_step = _get_step_by_id(workflow_doc, "merge_step")
    merge_run = merge_step.get("run", "")
    assert '--match-head-commit "$CURRENT_SHA"' in merge_run
    assert '[ "$PR_HEAD_SHA" != "$CURRENT_SHA" ]' in merge_run
    assert "merged=true" in merge_run
    assert "merged=false" in merge_run

    story_cond = str(_get_step_by_id(workflow_doc, "close_story_step").get("if", ""))
    assert "steps.merge_step.outputs.merged == 'true'" in story_cond
