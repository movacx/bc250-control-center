from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_static_analysis_tools_are_declared_for_development():
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "ruff>=" in requirements
    assert "bandit>=" in requirements
    assert "radon>=" in requirements
