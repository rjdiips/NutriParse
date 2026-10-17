@echo off
setlocal
cd /d "%~dp0"
if not exist ".image-env\Scripts\python.exe" (
  echo Run setup_local_image_generator.bat first.
  pause
  exit /b 1
)
".image-env\Scripts\python.exe" local_image_service.py
