from pathlib import Path

import pytest

from assara.config import CONFIG_NAME, DEFAULT_CONFIG, Config


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """A minimal library (config file and folders), independent of `assara init`."""
    root = tmp_path / "library"
    for sub in ("sources", "synthesis", "inbox"):
        (root / sub).mkdir(parents=True)
    (root / CONFIG_NAME).write_text(DEFAULT_CONFIG, encoding="utf-8")
    return root


@pytest.fixture
def cfg(library: Path) -> Config:
    return Config.load(library)
