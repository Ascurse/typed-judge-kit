"""Версия объявлена в одном месте — pyproject. Дубль в __init__ уже разъезжался молча (бид jnk)."""
from importlib.metadata import version

import typed_judge


def test_package_version_matches_installed_metadata():
    assert typed_judge.__version__ == version("typed-judge")
