@echo off
echo Installing PixelMirror dependencies...
echo.

pip install -r requirements.txt

echo.
echo Testing installation...
python test_setup.py

echo.
pause