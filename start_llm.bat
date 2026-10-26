@echo off
setlocal
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

rem ---- optional override from .env ------------------------------------------
rem Only LLM_MODEL_FILE is read here: it is a convenience for pointing at a GGUF
rem outside models\ and D:\models\, and .env is the one place the repo keeps it.
if exist ".env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
    if /i "%%a"=="LLM_MODEL_FILE" set "LLM_MODEL_FILE=%%b"
  )
)

rem ---- locate the server ----------------------------------------------------
rem Prefer the modern `llama serve` CLI, but only accept it when it really is
rem llama.cpp: an unrelated tool called llama.exe on PATH must not shadow the
rem pinned server. Otherwise fall back to a standalone llama-server.exe.
set "LLAMA_CLI="
for /f "delims=" %%f in ('where llama.exe 2^>nul') do if not defined LLAMA_CLI (
  "%%f" --version 2>nul | findstr /i /c:"version:" >nul && set "LLAMA_CLI=%%f"
)
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
if defined MODEL set "MODEL=%MODEL:"=%"
if defined MODEL if not exist "%MODEL%" (
  echo LLM_MODEL_FILE points at a file that does not exist:
  echo   %MODEL%
  pause
  exit /b 1
)
if not defined MODEL call :find_model "models\%MODEL_NAME%"
if not defined MODEL call :find_model "D:\models\%MODEL_NAME%"
if not defined MODEL call :find_model "models"
if not defined MODEL (
  echo No .gguf file found for "%MODEL_NAME%".
  echo Looked in models\%MODEL_NAME%\, D:\models\%MODEL_NAME%\, and models\.
  echo Download a GGUF ^(Q4_K_M is a good default^) to one of those folders,
  echo or set LLM_MODEL_FILE to the full path of the model before running this
  echo script.
  pause
  exit /b 1
)

rem ---- check the port -------------------------------------------------------
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo Port %PORT% is already in use. Stop the server that owns it, or change
  echo PORT here and LLM_BASE_URL in .env to a matching port.
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
