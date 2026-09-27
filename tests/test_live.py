"""An optional smoke test against the real API. Runs only when URLPIPE_API_KEY
is set; it spends at most one credit (none on a cache hit)."""

from __future__ import annotations

import os

import pytest

import urlpipe

pytestmark = pytest.mark.skipif(
    not os.environ.get("URLPIPE_API_KEY"), reason="set URLPIPE_API_KEY to run the live test"
)


def test_markdown_of_example_com() -> None:
    with urlpipe.Client() as client:
        response = client.markdown("https://example.com")
    assert response.status == "completed"
    assert "Example Domain" in (response.data or "")
    assert response.token
