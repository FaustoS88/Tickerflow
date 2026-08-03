# VHS terminal recording — generates assets/demo.gif
# Install: brew install charmbracelet/tap/vhs
# Run:     vhs demo.tape
# Output:  assets/demo.gif

Output assets/demo.gif

Set Shell "zsh"
Set Theme "Dracula"
Set FontFamily "JetBrains Mono"
Set FontSize 14
Set Width 1200
Set Height 600
Set Padding 20

Type "# tickerflow — one call, any ticker, any asset class"
Enter
Sleep 1s

Type "tickerflow fetch BTCUSDT 1d 5"
Enter
Sleep 3s

Type "tickerflow fetch AAPL 1d 5"
Enter
Sleep 3s

Type "tickerflow fetch EURUSD 1d 5"
Enter
Sleep 3s

Type "# Terminal chart — screenshot-worthy output"
Enter
Sleep 500ms

Type "tickerflow chart BTCUSDT 1d 30"
Enter
Sleep 4s

Type "# Self-hosted API — one command"
Enter
Sleep 500ms

Type "tickerflow serve --port 8000 &"
Enter
Sleep 2s

Type "curl -s localhost:8000/ohlcv/BTCUSDT?interval=1d\\&limit=3 | python -m json.tool"
Enter
Sleep 3s

Type "curl -s localhost:8000/providers/BTCUSDT | python -m json.tool"
Enter
Sleep 2s

Type "kill %1"
Enter
Sleep 500ms
