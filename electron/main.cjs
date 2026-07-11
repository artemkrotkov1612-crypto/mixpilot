'use strict';

const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('node:path');
const { WorkerManager } = require('./workerManager.cjs');

const IS_SMOKE = process.argv.includes('--smoke-test');
const IS_DEV = process.argv.includes('--dev');
const DEV_UI_URL = 'http://127.0.0.1:3520';

const wm = new WorkerManager({
  workerDir: path.join(app.getAppPath(), 'worker'),
  log: (line) => console.log(line),
});

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1200,
    minHeight: 760,
    backgroundColor: '#0A0B10',
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.once('ready-to-show', () => mainWindow.show());
  if (IS_DEV) {
    mainWindow.loadURL(DEV_UI_URL);
  } else {
    mainWindow.loadFile(path.join(app.getAppPath(), 'dist', 'index.html'));
  }
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

/** Смоук-режим: без окна — поднять worker, спросить /meta, погасить, выйти. */
async function runSmokeTest() {
  try {
    await wm.start();
    const meta = await wm.fetchJson('/meta');
    console.log('SMOKE_RESULT ' + JSON.stringify({ ok: true, worker: meta }));
    await wm.stop();
    app.exit(0);
  } catch (err) {
    console.error('SMOKE_RESULT ' + JSON.stringify({ ok: false, error: String(err) }));
    await wm.stop().catch(() => {});
    app.exit(1);
  }
}

if (!IS_SMOKE && !app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  ipcMain.handle('worker:info', () => wm.info());

  app.whenReady().then(async () => {
    if (IS_SMOKE) {
      await runSmokeTest();
      return;
    }
    createWindow();
    try {
      await wm.start();
    } catch (err) {
      console.error('worker start failed:', err);
      // UI покажет статус offline; авторестарт-стратегия — M2.
    }
  });

  app.on('window-all-closed', () => app.quit());

  let quitting = false;
  app.on('before-quit', (event) => {
    if (quitting || IS_SMOKE) return;
    event.preventDefault();
    quitting = true;
    wm.stop().finally(() => app.quit());
  });
}
