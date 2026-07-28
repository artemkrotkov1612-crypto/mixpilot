'use strict';

/**
 * Первый запуск: доустановка того, что нельзя положить в установщик.
 *
 * ТЗ §2: пользователь не ставит Python, библиотеки и CUDA руками. В
 * установщике лежат uv и ffmpeg, а Python и ~3 ГБ библиотек (torch с CUDA,
 * demucs, seed-vc) скачиваются один раз при первом запуске — класть их в
 * установщик значило бы раздать его на 4 ГБ и качать заново при каждом
 * обновлении приложения.
 *
 * Всё пишется в %LOCALAPPDATA%\MixPilot\runtime: Program Files доступен
 * только на чтение, и окружение там создать нельзя.
 */

const { spawn } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const paths = require('./paths.cjs');

// Измерено на чистой сборке: окружение занимает 5.2 ГБ (venv + кеш + Python),
// дальше подтягиваются веса моделей. 8 ГБ — минимум, при котором первый запуск
// не упрётся в диск на середине.
const NEEDED_FREE_GB = 8;

/** Отпечаток набора зависимостей: сменился uv.lock — надо пересобрать окружение. */
function lockFingerprint() {
  const lock = path.join(paths.workerDir(), 'uv.lock');
  try {
    return crypto.createHash('sha256').update(fs.readFileSync(lock)).digest('hex').slice(0, 16);
  } catch {
    return '';
  }
}

function readMarker() {
  try {
    return JSON.parse(fs.readFileSync(paths.readyMarker(), 'utf8'));
  } catch {
    return null;
  }
}

/** Готово ли окружение: есть python и отпечаток совпадает с текущим uv.lock. */
function isReady() {
  if (!paths.exists(paths.venvPython())) return false;
  const marker = readMarker();
  return Boolean(marker && marker.lock && marker.lock === lockFingerprint());
}

function freeGb(dir) {
  try {
    const stat = fs.statfsSync(dir);
    return (stat.bavail * stat.bsize) / 1024 ** 3;
  } catch {
    return Number.POSITIVE_INFINITY; // не смогли измерить — не мешаем установке
  }
}

/** Человеческий текст по строке вывода uv. Технические детали остаются в логе. */
function humanize(line) {
  if (/Using CPython|Installing CPython|Downloading cpython/i.test(line)) {
    return { pct: 0.1, text: 'Готовим Python…' };
  }
  const prepared = line.match(/Prepared (\d+) packages?/i);
  if (prepared) return { pct: 0.75, text: `Скачали ${prepared[1]} компонентов` };
  const installed = line.match(/Installed (\d+) packages?/i);
  if (installed) return { pct: 0.95, text: `Устанавливаем ${installed[1]} компонентов…` };
  const resolved = line.match(/Resolved (\d+) packages?/i);
  if (resolved) return { pct: 0.15, text: 'Составляем список компонентов…' };
  if (/Downloading|Fetching/i.test(line)) {
    // Крупная библиотека видна пользователю по размеру, а не по названию.
    const size = line.match(/\(([\d.]+\s*[KMG]i?B)\)/i);
    return { pct: 0.4, text: size ? `Скачиваем компоненты… ${size[1]}` : 'Скачиваем компоненты…' };
  }
  return null;
}

/**
 * Доводит окружение до рабочего состояния.
 * @param {(p: {pct: number, text: string}) => void} onProgress
 */
async function ensure(onProgress = () => {}) {
  if (isReady()) return { ok: true, skipped: true };

  await fsp.mkdir(paths.runtimeDir(), { recursive: true });

  const free = freeGb(paths.runtimeDir());
  if (free < NEEDED_FREE_GB) {
    const err = new Error('not enough disk space');
    err.messageRu =
      `На диске свободно ${free.toFixed(1)} ГБ, а нужно около ${NEEDED_FREE_GB} ГБ. ` +
      'Освободите место и запустите MixPilot снова.';
    throw err;
  }

  onProgress({ pct: 0.02, text: 'Готовим движок к первому запуску…' });

  const env = {
    ...process.env,
    UV_PROJECT_ENVIRONMENT: paths.venvDir(),   // venv вне Program Files
    UV_PYTHON_INSTALL_DIR: paths.pythonInstallDir(),
    UV_CACHE_DIR: paths.uvCacheDir(),
    UV_NO_PROGRESS: '1',                       // проценты рисуем свои, без \r-мусора
  };

  const log = [];
  await new Promise((resolve, reject) => {
    // --frozen: ставим ровно то, что зафиксировано в uv.lock, без пересчёта.
    const child = spawn(paths.uvBin(), ['sync', '--frozen', '--project', paths.workerDir()], {
      cwd: paths.workerDir(),
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });

    const onLine = (chunk) => {
      for (const line of String(chunk).split(/\r?\n/)) {
        if (!line.trim()) continue;
        log.push(line);
        const human = humanize(line);
        if (human) onProgress(human);
      }
    };
    child.stdout.on('data', onLine);
    child.stderr.on('data', onLine);

    child.on('error', reject);
    child.on('exit', (code) => {
      if (code === 0) return resolve();
      const text = log.join('\n');
      const err = new Error(`uv sync exited with ${code}`);
      if (/network|connect|resolve|timed out|dns/i.test(text)) {
        err.messageRu = 'Не удалось скачать компоненты. Проверьте интернет и запустите MixPilot снова.';
      } else if (/WinError 3|filename or extension is too long|path too long/i.test(text)) {
        // Один из компонентов (antlr4 для seed-vc) собирается из исходников, и
        // Windows обрывает сборку, если путь длиннее 260 символов.
        err.messageRu =
          'Слишком длинный путь к папке приложения — Windows не даёт собрать компоненты. ' +
          'Помогает включённый «Режим разработчика» в параметрах Windows (снимает ограничение на длину пути).';
      } else {
        err.messageRu = 'Не удалось подготовить движок. Подробности в журнале приложения.';
      }
      err.detail = log.slice(-25).join('\n');
      reject(err);
    });
  });

  if (!paths.exists(paths.venvPython())) {
    const err = new Error('venv python missing after sync');
    err.messageRu = 'Движок установился не полностью. Запустите MixPilot ещё раз.';
    throw err;
  }

  await fsp.writeFile(
    paths.readyMarker(),
    JSON.stringify({ lock: lockFingerprint(), at: new Date().toISOString() }, null, 2),
    'utf8',
  );
  onProgress({ pct: 1, text: 'Готово' });
  return { ok: true, skipped: false };
}

module.exports = { ensure, isReady, lockFingerprint, freeGb, humanize, NEEDED_FREE_GB };
