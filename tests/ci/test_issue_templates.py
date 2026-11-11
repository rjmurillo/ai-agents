"""Keep public issue forms useful for reproducible, actionable reports."""

from pathlib import Path

import pytest
import yaml

TEMPLATES = Path(__file__).resolve().parents[2] / ".github" / "ISSUE_TEMPLATE"


@pytest.mark.parametrize(
    ("filename", "required_fields"),
    [
        ("bug-report.yml", {"component", "environment", "reproduction", "expected", "actual"}),
        ("feature-request.yml", {"problem", "component", "proposal", "alternatives", "acceptance"}),
    ],
)
def test_issue_forms_require_actionable_information(filename, required_fields):
    form = yaml.safe_load((TEMPLATES / filename).read_text(encoding="utf-8"))

    assert form["name"]
    assert form["description"]
    fields = [field for field in form["body"] if field["type"] != "markdown"]
    ids = [field["id"] for field in fields]
    assert len(ids) == len(set(ids))
    by_id = {field["id"]: field for field in fields}
    assert required_fields <= by_id.keys()
    for field_id in required_fields:
        field = by_id[field_id]
        assert field["type"] in {"input", "textarea", "dropdown", "checkboxes"}
        assert field["attributes"]["label"]
        assert field["attributes"]["description"]
        assert field["validations"]["required"] is True


def test_bug_form_routes_vulnerabilities_to_private_reporting():
    form = yaml.safe_load((TEMPLATES / "bug-report.yml").read_text(encoding="utf-8"))
    guidance = "\n".join(
        field["attributes"]["value"] for field in form["body"] if field["type"] == "markdown"
    )
    assert "https://github.com/rjmurillo/ai-agents/security/advisories/new" in guidance
    assert "Remove secrets, personal data, and private prompts" in guidance
    logs = next(field for field in form["body"] if field.get("id") == "logs")
    assert logs["attributes"]["render"] == "text"
    assert logs.get("validations", {}).get("required", False) is False
