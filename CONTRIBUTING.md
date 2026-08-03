# Contributing to tickerflow

Thanks for considering a contribution! This guide will get you set up.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/FaustoS88/tickerflow.git
cd tickerflow

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install with all dev dependencies
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

All tests use mocked HTTP responses — no API keys or network access needed.

## Code Style

We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
ruff check .
ruff format .
```

Rules:
- **Type hints everywhere** — the package ships `py.typed`
- **Line length**: 100 characters
- **Docstrings**: required for public functions and classes

## Adding a New Provider

The provider architecture makes this straightforward. Here's the pattern:

### 1. Create `src/tickerflow/providers/your_provider.py`

```python
from __future__ import annotations
import logging
from tickerflow.models import Candle
from tickerflow.providers.base import OHLCVProvider

logger = logging.getLogger(__name__)

class YourProvider(OHLCVProvider):
    name = "your_provider"

    def supports(self, symbol: str) -> bool:
        # Return True if this provider can handle the symbol
        ...

    async def fetch(self, symbol: str, interval: str, limit: int) -> list[Candle] | None:
        # Fetch candles from the API
        # Return list[Candle] on success, None on failure
        ...
```

### 2. Wire it into the registry

In `src/tickerflow/registry.py`:
- Add a lazy getter function (`_get_your_provider()`)
- Add the provider to the appropriate chain(s) in `pick()`

### 3. Add tests

Create `tests/test_your_provider.py` with mocked HTTP responses using `aioresponses`.

### 4. Update docs

- Add the provider to the routing table in `README.md`
- Add a changelog entry

## Pull Request Process

1. Fork the repo and create a feature branch
2. Make your changes with tests
3. Run `pytest tests/ -v` and `ruff check .`
4. Open a PR with a clear description of what changed and why

## Good First Issues

Look for issues labelled [`good first issue`](https://github.com/FaustoS88/tickerflow/labels/good%20first%20issue) — these are specifically scoped for new contributors.
