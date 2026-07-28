'use strict';

/**
 * Собирает stage/ — то, что electron-builder положит в resources установленного
 * приложения (см. build.extraResources в package.json):
 *
 *   stage/worker — исходники worker'а и uv.lock; окружение Python собирается
 *                  из них при первом запуске (electron/bootstrap.cjs);
 *   stage/bin    — uv и ffmpeg: без первого не собрать окружение, без второго
 *                  не открыть ни один аудиофайл.
 *
 * Отдельным шагом, а не через filter в electron-builder: в worker/ во время
 * разработки лежат .venv (гигабайты), кеши и тесты, и любой промах фильтра
 * молча раздул бы установщик.
 */

const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const STAGE = path.join(ROOT, 'stage');

const DEV_UV = 'C:\\TheIceBoys\\TOOLS\\uv\\uv.exe';
const DEV_FFMPEG = 'C:\\TheIceBoys\\TOOLS\\ffmpeg\\bin';

// Из worker/ берём только то, без чего не собрать окружение и не запустить движок.
const WORKER_INCLUDE = ['src', 'pyproject.toml', 'uv.lock', 'README.md'];
// ffplay не нужен: воспроизведением занимается сам интерфейс.
const FFMPEG_BINARIES = ['ffmpeg.exe', 'ffprobe.exe'];

function rmrf(target) {
  fs.rmSync(target, { recursive: true, force: true });
}

function copyDir(from, to, skip = () => false) {
  fs.mkdirSync(to, { recursive: true });
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    const src = path.join(from, entry.name);
    const dst = path.join(to, entry.name);
    if (skip(entry.name)) continue;
    if (entry.isDirectory()) copyDir(src, dst, skip);
    else if (entry.isFile()) fs.copyFileSync(src, dst);
  }
}

function sizeMb(target) {
  let total = 0;
  const walk = (p) => {
    const stat = fs.statSync(p);
    if (stat.isDirectory()) for (const n of fs.readdirSync(p)) walk(path.join(p, n));
    else total += stat.size;
  };
  if (fs.existsSync(target)) walk(target);
  return (total / 1024 ** 2).toFixed(1);
}

function need(candidates, what) {
  for (const c of candidates) if (c && fs.existsSync(c)) return c;
  throw new Error(
    `не найден ${what}. Укажите путь переменной окружения или положите рядом: ${candidates.join(', ')}`,
  );
}

function main() {
  rmrf(STAGE);

  // --- worker: только исходники, без .venv, кешей и мусора сборки ---
  const workerFrom = path.join(ROOT, 'worker');
  const workerTo = path.join(STAGE, 'worker');
  fs.mkdirSync(workerTo, { recursive: true });
  const skip = (name) =>
    name === '__pycache__' || name === '.pytest_cache' || name.endsWith('.pyc');
  for (const item of WORKER_INCLUDE) {
    const src = path.join(workerFrom, item);
    if (!fs.existsSync(src)) continue;
    const dst = path.join(workerTo, item);
    if (fs.statSync(src).isDirectory()) copyDir(src, dst, skip);
    else fs.copyFileSync(src, dst);
  }
  if (!fs.existsSync(path.join(workerTo, 'uv.lock'))) {
    throw new Error('worker/uv.lock обязателен: без него первый запуск не соберёт окружение');
  }

  // --- uv ---
  const binTo = path.join(STAGE, 'bin');
  fs.mkdirSync(binTo, { recursive: true });
  const uv = need([process.env.MIXPILOT_UV, DEV_UV], 'uv.exe');
  fs.copyFileSync(uv, path.join(binTo, 'uv.exe'));

  // --- ffmpeg ---
  const ffmpegFrom = need([process.env.MIXPILOT_FFMPEG_DIR, DEV_FFMPEG], 'каталог ffmpeg');
  const ffmpegTo = path.join(binTo, 'ffmpeg');
  fs.mkdirSync(ffmpegTo, { recursive: true });
  for (const exe of FFMPEG_BINARIES) {
    const src = path.join(ffmpegFrom, exe);
    if (!fs.existsSync(src)) throw new Error(`в ${ffmpegFrom} нет ${exe}`);
    fs.copyFileSync(src, path.join(ffmpegTo, exe));
  }
  // ffmpeg собран под GPL (нужен фильтр rubberband) — лицензию кладём рядом.
  const licenseSrc = path.join(ROOT, 'build', 'FFMPEG-LICENSE.txt');
  if (fs.existsSync(licenseSrc)) {
    fs.copyFileSync(licenseSrc, path.join(ffmpegTo, 'LICENSE.txt'));
  }

  console.log(`stage/worker  ${sizeMb(workerTo)} МБ`);
  console.log(`stage/bin     ${sizeMb(binTo)} МБ`);
}

main();
