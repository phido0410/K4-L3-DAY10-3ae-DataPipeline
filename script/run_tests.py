from __future__ import annotations

import sys

import pytest


if __name__ == "__main__":
    # One-click test run: config (coverage >= 80%, paths) lives in pyproject.toml.
    sys.exit(pytest.main(sys.argv[1:]))
