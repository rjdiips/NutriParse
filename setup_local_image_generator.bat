@echo off
setlocal
cd /d "%~dp0"
if not exist ".python-runtime\python.exe" py install --target=.python-runtime 3.10.6
if errorlevel 1 goto failed
".python-runtime\python.exe" -m venv .image-env
if errorlevel 1 goto failed
".image-env\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".image-env\Scripts\python.exe" -m pip install openvino-genai huggingface_hub pillow
if errorlevel 1 goto failed
set HF_HUB_DISABLE_XET=1
".image-env\Scripts\python.exe" -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='OpenVINO/stable-diffusion-v1-5-int8-ov', local_dir='models/stable-diffusion-v1-5-int8-ov')"
if errorlevel 1 goto failed
echo Setup complete. Start the image service with start_local_image_generator.bat.
pause
exit /b 0

:failed
echo Setup did not complete. Review the error above and rerun this script.
pause
exit /b 1
