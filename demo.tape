# Records assets/demo.gif from real tickerflow commands.
# GitHub: Actions → Demo → Run workflow, then download the demo-gif artifact.
# Locally: vhs demo.tape (needs tickerflow[serve] installed).

Output assets/demo.gif

Set Shell "bash"
Set Theme "Dracula"
Set FontFamily "JetBrains Mono"
Set FontSize 14
Set Width 1200
Set Height 700
Set Padding 20

Type "tickerflow fetch BTCUSDT 1d 5"
Enter
Wait@30s
Sleep 2.5s

Type "tickerflow fetch AAPL 1d 5"
Enter
Wait@30s
Sleep 2.5s

Type "tickerflow fetch EURUSD 1d 5"
Enter
Wait@30s
Sleep 2.5s

Ctrl+L
Type "tickerflow chart BTCUSDT 1d 30"
Enter
Wait@30s
Sleep 4s

Ctrl+L
Type "tickerflow serve --port 8000 &> /dev/null &"
Enter
Sleep 5s

Type "curl -s localhost:8000/providers/BTCUSDT; echo"
Enter
Wait@30s
Sleep 2s

Type "curl -s 'localhost:8000/ohlcv/BTCUSDT?interval=1d&limit=2' | python -m json.tool"
Enter
Wait@30s
Sleep 4s

