@echo off
rem Dev environment for MixPilot (workspace portable tools).
rem ASCII only in this file (PowerShell 5.1 / cmd encoding pitfalls).
set "PATH=C:\TheIceBoys\TOOLS\Node-24.18.0;%PATH%"
set "MIXPILOT_UV=C:\TheIceBoys\TOOLS\uv\uv.exe"
set "UV_CACHE_DIR=C:\TheIceBoys\TOOLS\uv-cache"
rem Managed Python in TOOLS: install into %APPDATA%\uv breaks on this machine
rem ("Missing expected target directory for Python minor version link").
set "UV_PYTHON_INSTALL_DIR=C:\TheIceBoys\TOOLS\uv-python"
set "npm_config_cache=C:\TheIceBoys\TOOLS\npm-cache"
