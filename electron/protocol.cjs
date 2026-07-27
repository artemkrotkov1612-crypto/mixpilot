'use strict';

const { protocol } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { Readable } = require('node:stream');

// Имена файлов в originals: <hash16>.<ext> — задаёт worker при импорте.
const FILE_RE = /^[a-f0-9]{16}\.[a-z0-9]{2,5}$/;
// Рендеры вариантов: renders/<generation>/variant_<n>.wav
const RENDER_RE = /^[a-f0-9]{32}\/variant_\d+\.wav$/;

const MIME = {
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
  '.flac': 'audio/flac',
  '.m4a': 'audio/mp4',
  '.aac': 'audio/aac',
  '.ogg': 'audio/ogg',
  '.opus': 'audio/ogg',
  '.wma': 'audio/x-ms-wma',
  '.aiff': 'audio/aiff',
  '.aif': 'audio/aiff',
};

/** Хранилище данных — то же соглашение, что в worker/config.py. */
function dataDir() {
  if (process.env.MIXPILOT_DATA_DIR) return process.env.MIXPILOT_DATA_DIR;
  const local = process.env.LOCALAPPDATA || path.join(require('node:os').homedir(), 'AppData', 'Local');
  return path.join(local, 'MixPilot');
}

function originalsDir() {
  return path.join(dataDir(), 'media', 'originals');
}

function rendersDir() {
  return path.join(dataDir(), 'renders');
}

/** Вызывать до app.whenReady(): схема со stream-семантикой для <audio>/wavesurfer. */
function registerMediaScheme() {
  protocol.registerSchemesAsPrivileged([
    { scheme: 'media', privileges: { stream: true, supportFetchAPI: true } },
  ]);
}

/** "bytes=a-b" -> {start,end} | null (некорректный/невыполнимый диапазон). */
function parseRange(header, size) {
  const m = /^bytes=(\d*)-(\d*)$/.exec(header || '');
  if (!m || (m[1] === '' && m[2] === '')) return null;
  let start;
  let end;
  if (m[1] === '') {
    const suffix = Number(m[2]);
    if (suffix === 0) return null;
    start = Math.max(size - suffix, 0);
    end = size - 1;
  } else {
    start = Number(m[1]);
    end = m[2] === '' ? size - 1 : Math.min(Number(m[2]), size - 1);
  }
  if (Number.isNaN(start) || Number.isNaN(end) || start > end || start >= size) return null;
  return { start, end };
}

/** media://originals/<file> — стрим из хранилища с поддержкой Range (перемотка). */
function installMediaProtocol() {
  protocol.handle('media', async (request) => {
    const url = new URL(request.url);
    // media://originals/<hash>.<ext>  или  media://render/<gen>/variant_<n>.wav
    let file;
    if (url.host === 'originals') {
      const name = decodeURIComponent(url.pathname.replace(/^\//, ''));
      if (!FILE_RE.test(name)) return new Response('bad name', { status: 400 });
      file = path.join(originalsDir(), name);
    } else if (url.host === 'render') {
      const rel = decodeURIComponent(url.pathname.replace(/^\//, ''));
      if (!RENDER_RE.test(rel)) return new Response('bad name', { status: 400 });
      file = path.join(rendersDir(), rel);
    } else {
      return new Response('not found', { status: 404 });
    }
    const name = path.basename(file);
    let stat;
    try {
      stat = await fs.promises.stat(file);
    } catch {
      return new Response('not found', { status: 404 });
    }

    const headers = {
      'Content-Type': MIME[path.extname(name)] || 'application/octet-stream',
      'Accept-Ranges': 'bytes',
      // содержимое неизменно (имя = хеш) — агрессивный кеш ускоряет перемотку
      'Cache-Control': 'public, max-age=31536000, immutable',
    };

    const rangeHeader = request.headers.get('range');
    if (rangeHeader) {
      const range = parseRange(rangeHeader, stat.size);
      if (!range) {
        return new Response('range not satisfiable', {
          status: 416,
          headers: { 'Content-Range': `bytes */${stat.size}` },
        });
      }
      headers['Content-Range'] = `bytes ${range.start}-${range.end}/${stat.size}`;
      headers['Content-Length'] = String(range.end - range.start + 1);
      const stream = fs.createReadStream(file, { start: range.start, end: range.end });
      return new Response(Readable.toWeb(stream), { status: 206, headers });
    }

    headers['Content-Length'] = String(stat.size);
    return new Response(Readable.toWeb(fs.createReadStream(file)), { status: 200, headers });
  });
}

module.exports = { registerMediaScheme, installMediaProtocol, dataDir, originalsDir, parseRange };
