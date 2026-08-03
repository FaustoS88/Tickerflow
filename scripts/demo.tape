# VHS terminal recording — generates assets/demo.gif

Output assets/demo.gif

Set Shell "bash"
Set Theme "Dracula"
Set FontFamily "JetBrains Mono"
Set FontSize 14
Set Width 900
Set Height 500
Set Padding 20
Set TypingSpeed 60ms

# Title
Type "# tickerflow — one call, any ticker, zero API keys"
Enter
Sleep 800ms

# Crypto fetch
Type "tickerflow fetch BTCUSDT 1d 5"
Enter
Sleep 500ms
Hide
Type "./scripts/mock_tickerflow.sh fetch BTCUSDT 1d 5"
Enter
Show
Sleep 2500ms

# Stock fetch
Type "tickerflow fetch AAPL 1d 5"
Enter
Sleep 500ms
Hide
Type "./scripts/mock_tickerflow.sh fetch AAPL 1d 5"
Enter
Show
Sleep 2500ms

# Forex fetch
Type "tickerflow fetch EURUSD 1d 5"
Enter
Sleep 500ms
Hide
Type "./scripts/mock_tickerflow.sh fetch EURUSD 1d 5"
Enter
Show
Sleep 2500ms

Sleep 1s
