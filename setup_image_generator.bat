@echo off
setlocal
cd /d "%~dp0"

set "RELEASE=master-982-0518b34"
set "SD_ZIP=sd-master-0518b34-bin-win-cuda12-x64.zip"
set "CUDART_ZIP=cudart-sd-bin-win-cu12-x64.zip"
set "MODEL_URL=https://huggingface.co/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0_fp16.safetensors"
set "MODEL=models\sdxl-turbo\sd_xl_turbo_1.0_fp16.safetensors"

if not exist ".image-tools" mkdir ".image-tools"
if not exist "models\sdxl-turbo" mkdir "models\sdxl-turbo"

if exist ".image-tools\sd-cuda\sd-server.exe" if exist ".image-tools\sd-cuda\cudart64_12.dll" goto model

echo Downloading stable-diffusion.cpp CUDA build (about 900 MB)...
curl.exe -L --fail --retry 3 -o ".image-tools\%SD_ZIP%" "https://github.com/leejet/stable-diffusion.cpp/releases/download/%RELEASE%/%SD_ZIP%"
if errorlevel 1 goto failed
curl.exe -L --fail --retry 3 -o ".image-tools\%CUDART_ZIP%" "https://github.com/leejet/stable-diffusion.cpp/releases/download/%RELEASE%/%CUDART_ZIP%"
if errorlevel 1 goto failed
if not exist ".image-tools\sd-cuda" mkdir ".image-tools\sd-cuda"
tar.exe -xf ".image-tools\%SD_ZIP%" -C ".image-tools\sd-cuda"
if errorlevel 1 goto failed
tar.exe -xf ".image-tools\%CUDART_ZIP%" -C ".image-tools\sd-cuda"
if errorlevel 1 goto failed
del ".image-tools\%SD_ZIP%" ".image-tools\%CUDART_ZIP%"
if not exist ".image-tools\sd-cuda\sd-server.exe" goto failed

:model
if not exist "%MODEL%" goto download_model
for %%A in ("%MODEL%") do set "MODEL_BYTES=%%~zA"
if "%MODEL_BYTES%"=="6938081905" goto done

:download_model
echo Downloading the SDXL-Turbo checkpoint (6.9 GB)...
curl.exe -L --fail --retry 3 -C - -o "%MODEL%" "%MODEL_URL%"
if errorlevel 1 goto failed

:done
echo Setup complete. Run start_image_generator.bat before using the Leftover Alchemist.
pause
exit /b 0

:failed
echo Setup did not complete. Check your internet connection and free disk space, then rerun.
pause
exit /b 1
