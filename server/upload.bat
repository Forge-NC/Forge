@echo off
cd /d "C:\Users\theup\Desktop\Forge\server"
"C:\Program Files (x86)\WinSCP\WinSCP.com" /ini=nul /script=upload_all.txt
echo EXIT CODE: %ERRORLEVEL%
