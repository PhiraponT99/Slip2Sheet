from __future__ import annotations

import json
from pathlib import Path
from typing import Any


GOALS_FILE = Path("goals.json")


def goals_report(path: Path | str = GOALS_FILE) -> dict[str, list[dict[str, Any]]]:
    return {"goals": list_goals(path)}


def list_goals(path: Path | str = GOALS_FILE) -> list[dict[str, Any]]:
    goals = load_goals(path)
    normalized = [
        build_goal(name, values)
        for name, values in goals.items()
    ]
    return sorted(
        normalized,
        key=lambda goal: goal["progress_percent"],
        reverse=True,
    )


def add_goal(
    name: str,
    target_amount: float,
    current_amount: float,
    path: Path | str = GOALS_FILE,
) -> dict[str, Any]:
    clean_name = _clean_name(name)
    if target_amount < 0 or current_amount < 0:
        raise ValueError("Goal amounts cannot be negative.")

    goals = load_goals(path)
    goals[clean_name] = {
        "target_amount": _normalize_amount(target_amount),
        "current_amount": _normalize_amount(current_amount),
    }
    save_goals(goals, path)
    return build_goal(clean_name, goals[clean_name])


def update_goal(
    name: str,
    current_amount: float,
    path: Path | str = GOALS_FILE,
) -> dict[str, Any]:
    clean_name = _clean_name(name)
    if current_amount < 0:
        raise ValueError("Goal amount cannot be negative.")

    goals = load_goals(path)
    if clean_name not in goals:
        raise ValueError(f"Goal not found: {clean_name}")

    goals[clean_name]["current_amount"] = _normalize_amount(current_amount)
    save_goals(goals, path)
    return build_goal(clean_name, goals[clean_name])


def load_goals(path: Path | str = GOALS_FILE) -> dict[str, dict[str, float]]:
    goals_path = Path(path)
    if not goals_path.exists():
        return {}

    with goals_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        return {}
    return {
        str(name): {
            "target_amount": _parse_amount(values.get("target_amount")),
            "current_amount": _parse_amount(values.get("current_amount")),
        }
        for name, values in data.items()
        if isinstance(values, dict)
    }


def save_goals(
    goals: dict[str, dict[str, float]],
    path: Path | str = GOALS_FILE,
) -> None:
    goals_path = Path(path)
    with goals_path.open("w", encoding="utf-8") as file:
        json.dump(goals, file, ensure_ascii=False, indent=2)
        file.write("\n")


def build_goal(name: str, values: dict[str, Any]) -> dict[str, Any]:
    target_amount = _parse_amount(values.get("target_amount"))
    current_amount = _parse_amount(values.get("current_amount"))
    return {
        "name": name,
        "target_amount": _normalize_amount(target_amount),
        "current_amount": _normalize_amount(current_amount),
        "progress_percent": calculate_progress_percent(
            target_amount, current_amount
        ),
    }


def calculate_progress_percent(target_amount: float, current_amount: float) -> float:
    if target_amount <= 0:
        return 0.0
    return round((current_amount / target_amount) * 100, 2)


def _clean_name(name: str) -> str:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Goal name is required.")
    return clean_name


def _parse_amount(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _normalize_amount(value: float) -> int | float:
    amount = round(float(value), 2)
    if amount.is_integer():
        return int(amount)
    return amount
