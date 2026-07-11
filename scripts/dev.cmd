@echo off
rem Start MixPilot in dev mode: vite (3520) + electron + python worker.
call "%~dp0env.cmd"
cd /d "%~dp0.."
npm run dev
