@echo off
rem Шаг 2: дописать заполненную вручную очередь (*_очередь.xlsx) в баланс.
rem Берёт свежие "..._auto.xlsx" и "..._очередь.xlsx" из excel\ и создаёт "..._ready.xlsx".
rem Перед запуском: заполните в очереди колонку/дату/сумму и поставьте "да" в "Записывать".

setlocal
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" -m pyparser.review %*

echo.
echo Готово. Итоговый файл "..._ready.xlsx" в папке excel.
pause
