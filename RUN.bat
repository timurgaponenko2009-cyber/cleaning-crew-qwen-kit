@echo off
chcp 65001 >nul
if "%~1"=="" (echo Drag a build_*.py file onto RUN.bat & pause & exit /b)
python "%~dp0libun_qwen.py" "%~1"
explorer "%~dp0out"
pause
