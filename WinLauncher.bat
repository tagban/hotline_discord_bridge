@echo off
:start
python hl_bridge.py
echo Bot crashed or stopped. Restarting...
timeout /t 3
goto start
