# VHS terminal recording — generates assets/fallback.gif

Output assets/fallback.gif

Set Shell "bash"
Set Theme "Dracula"
Set FontFamily "JetBrains Mono"
Set FontSize 14
Set Width 900
Set Height 400
Set Padding 20
Set TypingSpeed 60ms

Type "# What happens when Binance is down?"
Enter
Sleep 600ms

Type "tickerflow fetch BTCUSDT 1d 3"
Enter
Sleep 500ms
Hide
Type "./scripts/mock_fallback.sh"
Enter
Show
Sleep 3s
