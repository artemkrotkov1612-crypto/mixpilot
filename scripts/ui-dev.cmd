@echo off
rem Vite dev server only (for browser preview without Electron window).
call "%~dp0env.cmd"
cd /d "%~dp0.."
npm run ui:dev
