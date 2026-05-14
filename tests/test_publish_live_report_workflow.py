from pathlib import Path

WORKFLOW_PATH = Path(".github/workflows/publish-live-report.yml")


def test_publish_workflow_updates_tracked_public_report() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "contents: write" in workflow
    assert "git add data/public/v1/latest.json" in workflow
    assert "git push" in workflow
