---
name: Bug Report
about: Report a bug or unexpected behaviour
title: "[Bug] "
labels: bug
assignees: ''
---

## Description

A clear description of what the bug is.

## Steps to Reproduce

```python
# Minimal code to reproduce the issue
from tickerflow import fetch
import asyncio

async def main():
    result = await fetch("SYMBOL", interval="1d", limit=10)
    print(result)

asyncio.run(main())
```

## Expected Behaviour

What you expected to happen.

## Actual Behaviour

What actually happened. Include any error messages or tracebacks.

## Environment

- **tickerflow version**: (e.g. `0.2.0`)
- **Python version**: (e.g. `3.12`)
- **OS**: (e.g. macOS 15, Ubuntu 24.04)
- **Provider affected**: (e.g. Binance, yfinance, all)

## Additional Context

Any other context — logs, screenshots, related issues.
