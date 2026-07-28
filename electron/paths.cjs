'use strict';

/**
 * Где что лежит в двух разных мирах: репозиторий разработчика и установленное
 * приложение. Всё, что приложение пишет само (окружение Python, кеш, веса,
 * база), живёт в %LOCALAPPDATA%\MixPilot — Program Files только для чтения.
 */

const { app } = require('electron');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const DEV_UV = 'C:\\TheIceBoys\\TOOLS\\uv\\uv.exe';
const DEV_FFMPEG = 'C:\\TheIceBoys\\TOOLS\\ffmpeg\\bin';

function packaged() {
  return app.isPackaged;
}

/** Папка с ресурсами: resources/ в установленном приложении, корень в dev. */
function resourcesRoot() {
  return packaged() ? process.resourcesPath : app.getAppPath();
}

function workerDir() {
  return path.join(resourcesRoot(), 'worker');
}

/**
 * Данные пользователя. Читаем LOCALAPPDATA напрямую — ровно как это делает
 * config.data_dir() воркера, поэтому обе стороны всегда сходятся. Плюс
 * app.getPath('localAppData') недоступен до app.whenReady(), а пути нужны
 * раньше — при создании WorkerManager.
 *
 * MIXPILOT_DATA_DIR понимает и воркер: с ним проверки идут в стороне и не
 * трогают настоящую библиотеку и проекты пользователя.
 */
function dataDir() {
  const override = process.env.MIXPILOT_DATA_DIR;
  if (override) return path.resolve(override);
  const local = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local');
  return path.join(local, 'MixPilot');
}

/** Всё, что доустанавливается при первом запуске. */
function runtimeDir() {
  return path.join(dataDir(), 'runtime');
}

function venvDir() {
  return path.join(runtimeDir(), 'venv');
}

function venvPython() {
  return path.join(venvDir(), 'Scripts', 'python.exe');
}

function pythonInstallDir() {
  return path.join(runtimeDir(), 'python');
}

function uvCacheDir() {
  return path.join(runtimeDir(), 'uv-cache');
}

function readyMarker() {
  return path.join(runtimeDir(), 'ready.json');
}

function exists(p) {
  try {
    return fs.existsSync(p);
  } catch {
    return false;
  }
}

/** uv: из ресурсов установленного приложения, иначе из воркспейса, иначе PATH. */
function uvBin() {
  const candidates = [
    process.env.MIXPILOT_UV,
    path.join(resourcesRoot(), 'bin', 'uv.exe'),
    DEV_UV,
  ].filter(Boolean);
  for (const c of candidates) if (exists(c)) return c;
  return 'uv';
}

/** Папка с ffmpeg.exe и ffprobe.exe — отдаётся воркеру через MIXPILOT_FFMPEG_DIR. */
function ffmpegDir() {
  const candidates = [
    process.env.MIXPILOT_FFMPEG_DIR,
    path.join(resourcesRoot(), 'bin', 'ffmpeg'),
    DEV_FFMPEG,
  ].filter(Boolean);
  for (const c of candidates) {
    if (exists(path.join(c, 'ffmpeg.exe')) && exists(path.join(c, 'ffprobe.exe'))) return c;
  }
  return null;
}

module.exports = {
  packaged, resourcesRoot, workerDir, dataDir, runtimeDir,
  venvDir, venvPython, pythonInstallDir, uvCacheDir, readyMarker,
  uvBin, ffmpegDir, exists,
};
