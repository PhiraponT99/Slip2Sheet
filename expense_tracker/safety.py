from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any


REQUIRED_GITIGNORE_ENTRIES = [
    ".env",
    "credentials/",
    "exports/",
    "incoming/",
    "processed/",
    "failed/",
    ".venv/",
    "__pycache__/",
]
RUNTIME_PREFIXES = ("exports/", "incoming/", "processed/", "failed/")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def run_precommit_check(project_root: Path | str = ".") -> tuple[dict[str, Any], int]:
    root = Path(project_root)
    checks = {
        "tests": check_unit_tests(root),
        "env_not_tracked": check_env_not_tracked(root),
        "credentials_not_tracked": check_credentials_not_tracked(root),
        "runtime_folders_not_tracked": check_runtime_folders_not_tracked(root),
        "gitignore_required_entries": check_gitignore_required_entries(root),
        "sample_images_documented": check_sample_images_documented(root),
    }
    status = "PASS" if all(check["status"] == "PASS" for check in checks.values()) else "FAIL"
    output = {
        "status": status,
        "checks": {
            name: check["status"] if check["status"] == "PASS" else check
            for name, check in checks.items()
        },
    }
    return output, 0 if status == "PASS" else 1


def check_unit_tests(project_root: Path) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return {"status": "PASS"}

    reason = (result.stderr or result.stdout or "Unit tests failed.").strip()
    return {"status": "FAIL", "reason": reason}


def check_env_not_tracked(project_root: Path) -> dict[str, Any]:
    tracked = tracked_paths(project_root)
    matches = [path for path in tracked if path == ".env"]
    return _path_check(matches, ".env is tracked or staged.")


def check_credentials_not_tracked(project_root: Path) -> dict[str, Any]:
    tracked = tracked_paths(project_root)
    matches = [
        path
        for path in tracked
        if path.startswith("credentials/")
        or _looks_like_service_account_json(path)
    ]
    return _path_check(matches, "Credential or service account JSON files are tracked or staged.")


def check_runtime_folders_not_tracked(project_root: Path) -> dict[str, Any]:
    tracked = tracked_paths(project_root)
    matches = [
        path
        for path in tracked
        if path.startswith(RUNTIME_PREFIXES)
    ]
    return _path_check(matches, "Runtime folder files are tracked or staged.")


def check_gitignore_required_entries(project_root: Path) -> dict[str, Any]:
    gitignore_path = project_root / ".gitignore"
    if not gitignore_path.exists():
        return {"status": "FAIL", "reason": ".gitignore is missing."}

    entries = {
        line.strip()
        for line in gitignore_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    missing = [
        entry
        for entry in REQUIRED_GITIGNORE_ENTRIES
        if entry not in entries
    ]
    if not missing:
        return {"status": "PASS"}
    return {
        "status": "FAIL",
        "reason": f".gitignore is missing required entries: {', '.join(missing)}",
    }


def check_sample_images_documented(project_root: Path) -> dict[str, Any]:
    tracked_sample_images = [
        path
        for path in tracked_paths(project_root)
        if path.startswith("samples/")
        and Path(path).suffix.lower() in IMAGE_EXTENSIONS
    ]
    if not tracked_sample_images:
        return {"status": "PASS"}

    readme_path = project_root / "README.md"
    if not readme_path.exists():
        return {"status": "FAIL", "reason": "Tracked sample images require README documentation."}

    readme = readme_path.read_text(encoding="utf-8").lower()
    if "sample/test slips" in readme:
        return {"status": "PASS"}
    return {
        "status": "FAIL",
        "reason": "Tracked sample images are allowed only when README clearly says they are sample/test slips.",
    }


def tracked_paths(project_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [
        path.replace("\\", "/")
        for path in result.stdout.splitlines()
        if path.strip()
    ]


def _path_check(matches: list[str], reason: str) -> dict[str, Any]:
    if not matches:
        return {"status": "PASS"}
    return {
        "status": "FAIL",
        "reason": reason,
        "paths": matches,
    }


def _looks_like_service_account_json(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith(".json") and (
        "service-account" in lowered
        or "service_account" in lowered
        or "credentials/" in lowered
    )
