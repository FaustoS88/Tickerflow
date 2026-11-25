# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

The project was called `ohlcv-hub` from 2026-02-22 (repository and import name), `ohlcv-router` from 2026-03-14 (on PyPI as 0.1.0 to 0.1.2) and `tickerflow` from 2026-08-03 (on PyPI from 0.2.0).

---

## [Unreleased]

### Added
- `fetch` takes `start` and `end` for a date range. Binance and KuCoin page back from the newest bar, yfinance asks Yahoo for the range, and Kraken serves ranges inside its last 720 bars. On Binance and KuCoin a `limit` above one request's cap is paged too.
- `fetch_df` returns a pandas DataFrame, with the provider that served it in `df.attrs["provider"]`.
- `fetch` returns `Candles`, a list whose `provider` attribute names the provider that served it; the server's `/ohlcv` answer has a `provider` field.
- `providers=` tries the named providers in that order; `timeout=` (30 seconds) bounds the whole chain, yfinance included.
- `tickerflow.INTERVALS` lists the intervals `fetch` accepts.

### Changed
- When no provider serves the bars, `fetch` raises `NoDataError` with each provider's reason in its message and in `.reasons`, instead of returning `None`. The CLI and the server show that message.
- Providers raise `ProviderError` with the reason (HTTP status, API error, unsupported interval or range) instead of returning `None`, which now means no bars. Finnhub errors show `***` in place of the API key.
- An unknown interval or provider, a `limit` below 1 or an empty range raise `ValueError` before any request.
- `tickerflow serve` listens on 127.0.0.1 by default; `--host 0.0.0.0` opens it to the network.
- The `dev` extra installs mypy, and a test type-checks the first README example.

### Removed
- `fetch(..., as_dataframe=True)`: use `fetch_df`.

## [0.2.6] — 2026-11-25

### Added
- Python 3.14: CI runs the tests on Python 3.11 to 3.14 and the classifiers list 3.14.
- A weekly job makes a real request to each provider that needs no key and fails when ETHBTC is not priced in BTC.

### Fixed
- Binance opens one HTTP session per request, so a second `asyncio.run` in the same process is served by Binance again instead of falling through to another provider.
- CoinGecko prices each pair in its quote currency (stablecoins in USD), serves only `4h` (its free API has no daily bars) and stamps candles at their open time, like the exchanges.
- Every aiohttp provider stops waiting after 10 seconds, so a silent upstream hands over to the next one.
- yfinance and Tiingo download a window sized for weekends, holidays and trading hours, so stocks and forex return the `limit` bars asked for, up to Yahoo's intraday look-back (AAPL `1h` with limit 100 gave 26 bars, now 100). yfinance intraday requests stay inside that look-back.

### Changed
- `teardown()` has nothing left to close and is kept as a no-op for compatibility.
- Releases are published from a version tag by GitHub Actions, only after the tests pass, through PyPI trusted publishing; the tag must match the package version.
- aiohttp has no upper bound any more (was `<3.11.0`), so tickerflow installs next to ccxt 4.5.94 and litellm 1.111.0, which need aiohttp 3.14. The tests run against a local aiohttp server instead of aioresponses, which is gone from the `dev` extra.

## [0.2.5] — 2026-08-04

### Changed
- `tickerflow chart` draws ANSI candlesticks with the standard library instead of plotext, so the `chart` extra installs nothing and is kept for compatibility. `--no-color` prints the chart without colours.

### Fixed
- Install hints quote the extras (`pip install "tickerflow[serve]"`), so they work in zsh.

## [0.2.4] — 2026-08-03

### Fixed
- `teardown()` closes only the providers that were created, so a crypto-only run no longer imports yfinance at shutdown.

## [0.2.3] — 2026-08-03

### Changed
- Providers are built only when the fallback chain reaches them, and `registry.pick()` returns provider names instead of provider instances.

### Fixed
- A provider that cannot be imported or built, or that raises while fetching, hands over to the next one instead of stopping `fetch`.
- `tickerflow fetch --provider` ignores case, and `tickerflow serve` reports the installed version instead of 0.2.0.

## [0.2.2] — 2026-08-03

### Fixed
- README images use absolute URLs, so they show on PyPI.
- Stock symbols follow one pattern, `^\^?[A-Z]{1,5}$`, in every provider and in the registry: Tiingo now accepts index symbols such as `^GSPC`, and yfinance, Finnhub and the registry accept index symbols of up to five letters after the caret (before, any length).
- `teardown()` closes the HTTP session of every provider, not only Binance's.

## [0.2.1] — 2026-08-03

### Changed
- README drops the PyPI downloads badge.

## [0.2.0] — 2026-08-03

### Added
- **pandas DataFrame output** — `await fetch("BTCUSDT", as_dataframe=True)` returns a `pd.DataFrame` with UTC datetime `time` column. Requires `pip install tickerflow[pandas]`
- **`tickerflow serve`** — self-hosted FastAPI market data API. `GET /ohlcv/{symbol}`, `/providers/{symbol}`, `/health`. Requires `pip install tickerflow[serve]`
- **`tickerflow chart`** — terminal chart rendering with price lines and volume subplot via plotext. Requires `pip install tickerflow[chart]`
- **`--json` CLI flag** — output candles as JSON array alongside existing `--csv`
- **Pydantic AI integration example** — `examples/pydantic_ai_agent.py` showing tickerflow as a tool in a Pydantic AI v2 agent
- **`ai`, `serve`, `chart`, `pandas`, `all` optional dependency groups** in pyproject.toml
- **CONTRIBUTING.md** — development setup, provider addition guide, PR process
- **GitHub issue templates** — feature request and bug report
- **VHS demo tape** — `demo.tape` for recording terminal GIF demos

### Changed
- README completely rewritten — new hero section, removed ccxt comparison table, added sections for serve/chart/DataFrame/AI integration, "Why This Exists" story section
- `pyproject.toml` keywords expanded for PyPI/GitHub discoverability
- Development status promoted to Beta
- Python 3.13 added to classifiers
- aiohttp capped below 3.11 (`aiohttp<3.11.0`)

## [0.1.2] — 2026-03-14

### Added
- In-memory TTL cache in `tickerflow.cache` — interval-aware expiry (30s for `1m` up to 24h for `1w`)
- Cache integrated into `registry.fetch()` — hit avoids all provider calls, miss populates on success
- `OHLCV_CACHE_ENABLED=false` env var to disable cache process-wide
- `cache.clear()` and `cache.size()` for testing and CLI tooling
- 26 cache tests covering TTL expiry, eviction, env toggle, and registry integration
- README Caching section with TTL table and usage examples

## [0.1.1] — 2026-03-14

### Changed
- README roadmap: replace GitHub-flavored checkboxes with plain text (renders correctly on PyPI)
- Roadmap updated to reflect current state — all v0.1.0 items complete, new planned items added

---

## [0.1.0] — 2026-03-14

### Added
- `KuCoinProvider` — public REST API, no key, `BASE-QUOTE` symbol normalisation, all intervals, 1500 bars
- `KrakenProvider` — public REST API for crypto OHLCV, no key required; BTC→XBT symbol mapping; all standard intervals
- `CoinGeckoProvider` — crypto OHLCV with no API key; 4h and 1d granularity via auto-detection
- GitHub Actions release workflow — publishes to PyPI on `v*` tag push

### Fixed
- Logging added to registry fallback chain — silent `None` returns now emit `debug`/`warning` diagnostics

---

## [0.0.5] — 2026-03-03

### Added
- CLI tool: `tickerflow fetch SYMBOL INTERVAL LIMIT [--provider] [--csv]` via click
- `examples/basic_fetch.py` and `examples/multi_provider.py`
- GitHub Actions CI — pytest + ruff on Python 3.11 and 3.12

### Fixed
- Session reuse in `BinanceProvider` — single `aiohttp.ClientSession` per instance
- Close session on CLI exit via `registry.teardown()`
- Move `click` to core dependencies (was optional, broke CLI install)

---

## [0.0.4] — 2026-02-25

### Added
- `FinnhubProvider` — US stock candles and forex quotes via OANDA format
- `TiingoProvider` — daily and weekly bars for stocks and ETFs; requires `TIINGO_API_KEY`
- Tiingo and Finnhub wired into `registry.pick()` routing chains

### Fixed
- `build-backend` value in `pyproject.toml` (`setuptools.build_meta`)
- Replace `respx` with `aioresponses` in dev dependencies

---

## [0.0.3] — 2026-02-23

### Added
- `YFinanceProvider` — stocks, forex, and crypto via yfinance
- `py.typed` marker for typed package consumers

---

## [0.0.2] — 2026-02-22

### Added
- `BinanceProvider` — crypto OHLCV via Binance klines endpoint
- `OHLCVProvider` abstract base class and `Candle` model
- Provider registry with asset-class-based routing

---

## [0.0.1] — 2026-02-22

### Added
- Initial project scaffold — `pyproject.toml`, package structure, README
