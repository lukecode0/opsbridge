from __future__ import annotations


ISSUE_TITLES = {
    3: "Improve asset import validation errors for malformed multipart requests",
    2: "Run focused Ruff/code-quality cleanup for the asset import/export API module",
    1: "Clarify Python requests-style multipart uploads for asset import",
}


def build_devin_prompt(repo_url: str, issue_number: int, issue_title: str | None = None) -> str:
    title = issue_title or ISSUE_TITLES.get(issue_number, "Remediate the selected GitHub issue")
    return f"""You are working in my fork of Apache Superset:
{repo_url}

Please remediate GitHub issue #{issue_number}: {title}

Constraints:
- Keep the change minimal and focused on the issue.
- Prefer the narrowest relevant files and tests.
- Do not perform broad refactors or unrelated cleanup.
- If repository setup, permissions, or tests block progress, stop and report the blocker clearly.
- Open a pull request against my fork when a code or documentation change is ready.
- Do not merge the pull request or close the GitHub issue.

For issue #{issue_number}, start by inspecting these likely areas:
- superset/importexport/api.py
- tests/unit_tests/importexport/api_test.py
- relevant import/export documentation only if needed

Run the narrowest relevant test or lint command for the files changed.

In your final response, include:
- summary
- files_changed
- commands_run
- tests_passed
- pr_url
- blockers
"""
