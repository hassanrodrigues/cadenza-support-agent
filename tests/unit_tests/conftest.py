from types import SimpleNamespace

import pytest

from cadenza.context import Context, parse_now


@pytest.fixture
def at():
    """Build the tool runtime for a fixed reference time, as the graph injects it."""

    def runtime_at(iso: str) -> SimpleNamespace:
        return SimpleNamespace(context=Context(now=parse_now(iso)))

    return runtime_at
