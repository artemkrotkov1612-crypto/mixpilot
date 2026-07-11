'use strict';

const { spawn } = require('node:child_process');
const net = require('node:net');
const fs = require('node:fs');
const path = require('node:path');

const HEALTH_TIMEOUT_MS = 60_000;
const HEALTH_POLL_MS = 400;
const SHUTDOWN_GRACE_MS = 5_000;

/** Свободный TCP-порт на 127.0.0.1 (отдаётся ОС). */
function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

/** Путь к uv: переменная окружения → uv воркспейса → uv из PATH. */
function resolveUv() {
  const candidates = [
    process.env.MIXPILOT_UV,
    'C:\\TheIceBoys\\TOOLS\\uv\\uv.exe',
  ].filter(Boolean);
  for (const c of candidates) {
    try {
      if (fs.existsSync(c)) return c;
    } catch {
      /* проверка следующего кандидата */
    }
  }
  return 'uv';
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Жизненный цикл Python-worker: запуск, health-poll, graceful stop.
 * В dev запускает через `uv run` (само синхронизирует окружение по uv.lock);
 * в упакованном приложении здесь появится встроенный runtime (M8).
 */
class WorkerManager {
  /** @param {{workerDir: string, log?: (line: string) => void}} opts */
  constructor(opts) {
    this.workerDir = opts.workerDir;
    this.log = opts.log ?? (() => {});
    this.child = null;
    this.port = null;
    this.status = 'stopped'; // stopped | starting | online | failed
    this.meta = null;
    this.stopping = false;
  }

  baseUrl() {
    return `http://127.0.0.1:${this.port}`;
  }

  info() {
    return { status: this.status, port: this.port, meta: this.meta };
  }

  async start() {
    if (this.child) return;
    this.status = 'starting';
    this.port = await findFreePort();

    const uv = resolveUv();
    const args = [
      'run', '--project', this.workerDir, '--',
      'uvicorn', 'mixpilot_worker.main:app',
      '--host', '127.0.0.1',
      '--port', String(this.port),
      '--log-level', 'warning',
    ];
    const env = { ...process.env };
    // В dev переиспользуем кеш и managed-Python воркспейса, если они есть
    // (установка в %APPDATA%\uv на этой машине ломается на minor version link).
    if (!env.UV_CACHE_DIR && fs.existsSync('C:\\TheIceBoys\\TOOLS\\uv-cache')) {
      env.UV_CACHE_DIR = 'C:\\TheIceBoys\\TOOLS\\uv-cache';
    }
    if (!env.UV_PYTHON_INSTALL_DIR && fs.existsSync('C:\\TheIceBoys\\TOOLS\\uv-python')) {
      env.UV_PYTHON_INSTALL_DIR = 'C:\\TheIceBoys\\TOOLS\\uv-python';
    }

    this.log(`spawn: ${uv} ${args.join(' ')}`);
    this.child = spawn(uv, args, {
      cwd: this.workerDir,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    this.child.stdout.on('data', (d) => this.log(`[worker] ${String(d).trimEnd()}`));
    this.child.stderr.on('data', (d) => this.log(`[worker] ${String(d).trimEnd()}`));
    this.child.on('exit', (code) => {
      this.log(`[worker] exited with code ${code}`);
      this.child = null;
      if (!this.stopping) this.status = 'failed';
    });

    await this.waitHealthy();
    this.meta = await this.fetchJson('/meta').catch(() => null);
    this.status = 'online';
  }

  async waitHealthy() {
    const deadline = Date.now() + HEALTH_TIMEOUT_MS;
    while (Date.now() < deadline) {
      if (!this.child) throw new Error('worker process exited during startup');
      try {
        const res = await fetch(`${this.baseUrl()}/health`, { signal: AbortSignal.timeout(1500) });
        if (res.ok) return;
      } catch {
        /* ещё не поднялся — ждём следующую попытку */
      }
      await sleep(HEALTH_POLL_MS);
    }
    throw new Error(`worker did not become healthy in ${HEALTH_TIMEOUT_MS} ms`);
  }

  async fetchJson(pathname) {
    const res = await fetch(this.baseUrl() + pathname, { signal: AbortSignal.timeout(3000) });
    if (!res.ok) throw new Error(`${pathname} -> HTTP ${res.status}`);
    return res.json();
  }

  async stop() {
    this.stopping = true;
    const child = this.child;
    if (!child) {
      this.status = 'stopped';
      return;
    }
    try {
      await fetch(`${this.baseUrl()}/shutdown`, {
        method: 'POST',
        signal: AbortSignal.timeout(2000),
      });
    } catch {
      /* worker мог уже упасть — добьём процесс ниже */
    }
    const deadline = Date.now() + SHUTDOWN_GRACE_MS;
    while (this.child && Date.now() < deadline) await sleep(100);
    if (this.child) {
      // Грациозно не вышел — валим всё дерево процессов (uv -> python).
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true });
      this.child = null;
    }
    this.status = 'stopped';
  }
}

module.exports = { WorkerManager, findFreePort, resolveUv };
