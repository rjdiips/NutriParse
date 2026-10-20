@echo off
setlocal
cd /d "%~dp0"

if not exist ".image-tools" (
  echo Run setup_image_generator.bat first.
  pause
  exit /b 1
)

set "SD_SERVER="
if exist ".image-tools\sd-cuda\sd-server.exe" set "SD_SERVER=.image-tools\sd-cuda\sd-server.exe"
if not defined SD_SERVER for /f "delims=" %%f in ('dir /s /b ".image-tools\sd-server.exe" 2^>nul') do if not defined SD_SERVER set "SD_SERVER=%%f"
set "MODEL=models\sdxl-turbo\sd_xl_turbo_1.0_fp16.safetensors"

if not defined SD_SERVER (
  echo Run setup_image_generator.bat first.
  pause
  exit /b 1
)
if not exist "%MODEL%" (
  echo Run setup_image_generator.bat first.
  pause
  exit /b 1
)

echo Starting SDXL-Turbo on http://127.0.0.1:7860 ...
"%SD_SERVER%" -m "%MODEL%" --listen-ip 127.0.0.1 --listen-port 7860 --steps 6 --cfg-scale 1 --sampling-method euler_a --vae-tiling
pause
