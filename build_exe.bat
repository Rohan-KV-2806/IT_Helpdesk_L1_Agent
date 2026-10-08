@echo off
setlocal
python -m pip install -r requirements.txt
python -m PyInstaller --clean --noconfirm L1Agent.spec
if errorlevel 1 (
    echo.
    echo Build failed.
    exit /b 1
)
echo.
echo Build complete. See dist\L1Agent\L1Agent.exe
endlocal
