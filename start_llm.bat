@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

rem ---- settings -------------------------------------------------------------
rem Port the app expects. Keep in sync with LLM_BASE_URL in .env.
set "PORT=8080"
rem Model folder name, also used as the alias shown in the inspector and logs.
rem Keep equal to LLM_MODEL in .env.
set "MODEL_NAME=qwen3.5-9b"
rem Context window. These prompts are small; 8192 leaves room for the reply.
set "CTX=8192"
rem Layers to offload to the GPU: 99 = all, 0 = CPU only.
set "NGL=99"

rem ---- locate the server ----------------------------------------------------
rem Prefer the modern `llama serve` CLI; fall back to a standalone llama-server.
set "LLAMA_CLI="
for /f "delims=" %%f in ('where llama.exe 2^>nul') do if not defined LLAMA_CLI set "LLAMA_CLI=%%f"
set "LLAMA_SERVER="
if exist ".llm-tools\llama-server.exe" set "LLAMA_SERVER=.llm-tools\llama-server.exe"
if not defined LLAMA_SERVER for /f "delims=" %%f in ('where llama-server.exe 2^>nul') do if not defined LLAMA_SERVER set "LLAMA_SERVER=%%f"
if not defined LLAMA_CLI if not defined LLAMA_SERVER (
  echo Neither the llama CLI nor llama-server.exe was found.
  echo Install the CLI with:  irm https://llama.app/install.ps1 ^| iex
  echo or download a build from https://github.com/ggml-org/llama.cpp/releases
  echo and extract it to .llm-tools\ ^(or add it to PATH^).
  pause
  exit /b 1
)

rem ---- locate the model -----------------------------------------------------
rem Priority: LLM_MODEL_FILE, models\<name>, D:\models\<name>, then any model
rem in the repo-local models\ folder.
set "MODEL=%LLM_MODEL_FILE%"
if not defined MODEL call :find_model "models\%MODEL_NAME%"
if not defined MODEL call :find_model "D:\models\%MODEL_NAME%"
if not defined MODEL call :find_model "models"
if not defined MODEL (
  echo No .gguf file found for "%MODEL_NAME%".
  echo Looked in models\%MODEL_NAME%\ and D:\models\%MODEL_NAME%\.
  echo Download a GGUF ^(Q4_K_M is a good default^), or set LLM_MODEL_FILE
  echo to the full path of the model before running this script.
  pause
  exit /b 1
)

rem ---- run ------------------------------------------------------------------
echo Starting llama.cpp on http://127.0.0.1:%PORT%/v1
echo Model: %MODEL%
echo Alias: %MODEL_NAME%
if defined LLAMA_CLI (
  "%LLAMA_CLI%" serve -m "%MODEL%" --alias "%MODEL_NAME%" -c %CTX% -ngl %NGL% --host 127.0.0.1 --port %PORT% --jinja --reasoning off
) else (
  "%LLAMA_SERVER%" -m "%MODEL%" --alias "%MODEL_NAME%" -c %CTX% -ngl %NGL% --host 127.0.0.1 --port %PORT% --jinja --reasoning off
)
pause
exit /b 0

:find_model
if not exist "%~1" exit /b 0
for /f "delims=" %%f in ('dir /s /b "%~1\*.gguf" 2^>nul') do (
  echo %%~nxf | findstr /i "mmproj" >nul
  if errorlevel 1 if not defined MODEL set "MODEL=%%f"
)
exit /b 0
