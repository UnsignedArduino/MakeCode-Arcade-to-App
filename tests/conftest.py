from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """
    Mark each test `unit` or `e2e` by its directory, so `-m unit` selects them.

    CI runs `-m unit` and `-m e2e` as separate workflows, so a test outside both
    directories would run in neither; fail collection instead of skipping it quietly.
    """
    for item in items:
        parts = item.path.relative_to(TESTS_DIR).parts
        if len(parts) < 2 or parts[0] not in ("unit", "e2e"):
            raise pytest.UsageError(
                f"{item.nodeid}: tests must live under tests/unit or tests/e2e"
            )
        item.add_marker(parts[0])


@pytest.fixture
def mkcd2app_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point MKCD2APP_HOME at a temp dir, so the test can't touch the real user dirs."""
    home = tmp_path / "mkcd2app-home"
    monkeypatch.setenv("MKCD2APP_HOME", str(home))
    return home
