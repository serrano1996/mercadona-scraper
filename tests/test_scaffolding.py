"""T1 — verifies the base package layout defined in plan.md exists and is importable."""

import importlib

import pytest

PACKAGES = [
    "app",
    "app.core",
    "app.api",
    "app.api.v1",
    "app.models",
    "app.scrapers",
    "app.services",
    "app.mappers",
]


@pytest.mark.parametrize("package", PACKAGES)
def test_package_is_importable(package: str) -> None:
    importlib.import_module(package)
