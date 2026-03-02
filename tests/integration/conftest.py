"""Fixtures for integration stress tests.

Provides OllamaStub, StressHarness, engine, and StateVerifier
fixtures used by all scenario test files.

Two modes:
  - Stub mode (default): OllamaStub serves scripted responses
  - Live mode (--live):  Engine talks to real Ollama at localhost:11434
    Tests marked @pytest.mark.stub_only are skipped in live mode.
"""

import pytest
from pathlib import Path

from tests.integration.ollama_stub import OllamaStub
from tests.integration.harness import StressHarness
from tests.integration.state_verifier import StateVerifier

_REAL_OLLAMA_URL = "http://localhost:11434"


def pytest_addoption(parser):
    """Add --live flag for tests requiring a real Ollama instance."""
    parser.addoption(
        "--live", action="store_true", default=False,
        help="Run tests against a real Ollama instance",
    )
    parser.addoption(
        "--live-model", default="qwen2.5-coder:14b",
        help="Model to use in live mode (default: qwen2.5-coder:14b)",
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "live: requires a running Ollama instance")
    config.addinivalue_line(
        "markers", "stub_only: requires scripted stub responses, skipped in live mode")


def pytest_collection_modifyitems(config, items):
    """Handle test filtering for live/stub modes."""
    is_live = config.getoption("--live")

    if is_live:
        # Live mode: skip stub_only tests
        skip_stub = pytest.mark.skip(
            reason="Test requires scripted stub responses (stub_only)")
        for item in items:
            if "stub_only" in item.keywords:
                item.add_marker(skip_stub)
    else:
        # Stub mode: skip live-only tests
        skip_live = pytest.mark.skip(reason="Requires --live flag")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


@pytest.fixture
def is_live(request):
    """Whether we're running in live mode."""
    return request.config.getoption("--live")


@pytest.fixture
def ollama_stub(is_live):
    """Start an OllamaStub HTTP server and yield it.

    In live mode, the stub still starts (some fixtures reference it)
    but the engine won't point at it.
    """
    stub = OllamaStub()
    stub.start()
    yield stub
    stub.stop()


@pytest.fixture
def harness(ollama_stub, tmp_path, monkeypatch, is_live, request):
    """Create a StressHarness wired to stub or real Ollama."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    live_model = request.config.getoption("--live-model")
    h = StressHarness(
        stub=ollama_stub,
        tmp_path=tmp_path,
        live=is_live,
        live_model=live_model,
    )
    return h


@pytest.fixture
def engine(harness):
    """Create and return a ready-to-use ForgeEngine from the harness."""
    return harness.create_engine()


@pytest.fixture
def verifier(engine, harness):
    """Create a StateVerifier for post-scenario integrity checks."""
    return StateVerifier(engine=engine, harness=harness)
