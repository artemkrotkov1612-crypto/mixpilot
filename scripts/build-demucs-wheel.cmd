@echo off
rem Rebuilds worker\wheels\demucs-*.whl from the pinned commit.
rem
rem Why the wheel exists at all: demucs 4.0.1 from PyPI has no demucs.api
rem (progress callback and cancellation appeared in 4.1.0a), so we need commit
rem b9ab48c. A git dependency would require Git ON THE USER MACHINE - on clean
rem Windows the first run died with "Git executable not found" and the engine
rem never installed. So the wheel is built here, once, and shipped inside the
rem installer.
rem
rem Run this only when the pinned commit changes.
setlocal
call "%~dp0env.cmd"
set "COMMIT=b9ab48cad45976ba42b2ff17b229c071f0df9390"
set "WORK=%TEMP%\mixpilot-demucs-wheel"

if exist "%WORK%" rmdir /s /q "%WORK%"
git clone -q https://github.com/adefossez/demucs "%WORK%" || goto :fail
pushd "%WORK%"
git checkout -q %COMMIT% || goto :fail
"%MIXPILOT_UV%" build --wheel -o "%WORK%\dist" || goto :fail
popd

copy /y "%WORK%\dist\demucs-*.whl" "%~dp0..\worker\wheels\" || goto :fail
echo.
echo Wheel updated. Now run: uv lock  (in worker\) and re-run the tests.
exit /b 0

:fail
echo FAILED to build demucs wheel
exit /b 1
