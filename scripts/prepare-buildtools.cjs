'use strict';

/**
 * Готовит кеш electron-builder так, чтобы сборка не требовала прав
 * администратора.
 *
 * Проблема: чтобы вписать в MixPilot.exe иконку и свойства файла,
 * electron-builder распаковывает пакет winCodeSign, а внутри него лежат
 * символические ссылки macOS (darwin/**\/lib/*.dylib). Создание симлинков на
 * Windows требует прав администратора или включённого «Режима разработчика»,
 * иначе распаковка падает и сборка обрывается.
 *
 * Решение: распаковать пакет самим с ключом -snl- (ссылки пропустить). Для
 * Windows-сборки darwin-часть не нужна вовсе, а rcedit — нужен, он там же.
 */

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const VERSION = 'winCodeSign-2.6.0';
const MIRROR =
  process.env.ELECTRON_BUILDER_BINARIES_MIRROR ||
  'https://github.com/electron-userland/electron-builder-binaries/releases/download/';

function cacheDir() {
  const base =
    process.env.ELECTRON_BUILDER_CACHE ||
    path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'),
              'electron-builder', 'Cache');
  return path.join(base, 'winCodeSign');
}

function sevenZip() {
  const bin = path.resolve(__dirname, '..', 'node_modules', '7zip-bin', 'win', 'x64', '7za.exe');
  if (!fs.existsSync(bin)) throw new Error(`не найден 7za: ${bin}`);
  return bin;
}

async function fetchArchive(target) {
  const url = `${MIRROR}${VERSION}/${VERSION}.7z`;
  console.log(`скачиваем ${url}`);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  fs.writeFileSync(target, Buffer.from(await res.arrayBuffer()));
}

async function main() {
  const dir = cacheDir();
  const target = path.join(dir, VERSION);
  if (fs.existsSync(path.join(target, 'rcedit-x64.exe'))) {
    console.log(`${VERSION} уже готов`);
    return;
  }

  fs.mkdirSync(dir, { recursive: true });
  // Прошлые неудачные попытки electron-builder оставляют архив со случайным
  // именем — переиспользуем его, чтобы не качать 5 МБ заново.
  const existing = fs.readdirSync(dir)
    .filter((n) => n.endsWith('.7z'))
    .map((n) => path.join(dir, n))
    .sort((a, b) => fs.statSync(b).size - fs.statSync(a).size)[0];

  const archive = existing || path.join(dir, `${VERSION}.7z`);
  if (!existing) await fetchArchive(archive);

  fs.rmSync(target, { recursive: true, force: true });
  execFileSync(sevenZip(), ['x', '-snl-', '-bd', '-y', archive, `-o${target}`], {
    stdio: ['ignore', 'ignore', 'inherit'],
  });

  if (!fs.existsSync(path.join(target, 'rcedit-x64.exe'))) {
    throw new Error(`распаковка не дала rcedit: ${target}`);
  }
  console.log(`${VERSION} распакован без симлинков -> ${target}`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
