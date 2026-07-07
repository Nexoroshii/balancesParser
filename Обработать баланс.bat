@echo off
rem Запуск обработки инвойсов: автоматически берёт свежую поставку и баланс из excel\
rem и создаёт копию "...баланс..._auto.xlsx" рядом с балансом. Оригинал не трогается.

setlocal
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" -m pyparser.phase2 %*

echo.
echo Готово. Проверьте файл "..._auto.xlsx" и отчёт "..._auto_report.csv" в папке excel.
pause
