'use strict';

const { app, BrowserWindow, dialog, ipcMain, Notification, shell } = require('electron');
const path = require('node:path');
const { WorkerManager } = require('./workerManager.cjs');
const { registerMediaScheme, installMediaProtocol } = require('./protocol.cjs');
const bootstrap = require('./bootstrap.cjs');
const paths = require('./paths.cjs');

const AUDIO_EXTENSIONS = ['mp3', 'wav', 'flac', 'm4a', 'aac', 'ogg', 'opus', 'wma', 'aiff', 'aif'];

registerMediaScheme(); // строго до app.whenReady()

const IS_SMOKE = process.argv.includes('--smoke-test');
const IS_SETUP = process.argv.includes('--setup');
const IS_DEV = process.argv.includes('--dev');
const DEV_UI_URL = 'http://127.0.0.1:3520';

const wm = new WorkerManager({
  workerDir: paths.workerDir(),
  // Готовое окружение — только в установленном приложении. В разработке всегда
  // `uv run` по рабочему дереву: окружение из установщика держит СВОЮ копию
  // исходников, и dev молча проверял бы вчерашний снимок вместо текущего кода.
  pythonBin: paths.packaged() ? paths.venvPython() : null,
  ffmpegDir: paths.ffmpegDir(),
  log: (line) => console.log(line),
});

let mainWindow = null;
/** Состояние доустановки компонентов: его же читает UI через worker:info. */
let setup = { active: false, pct: 0, text_ru: '', error_ru: null };

/** Обновления: тихо проверяем, ставим при следующем запуске. Никогда не мешаем. */
function checkForUpdates() {
  if (!app.isPackaged) return;
  try {
    const { autoUpdater } = require('electron-updater');
    autoUpdater.autoDownload = true;
    autoUpdater.on('error', (err) => console.error('updater:', String(err)));
    autoUpdater.checkForUpdatesAndNotify().catch((err) => console.error('updater:', String(err)));
  } catch (err) {
    console.error('updater unavailable:', String(err));
  }
}

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

/**
 * Режим `--setup`: доустановка компонентов без окна.
 *
 * Нужен двум сторонам: проверке первого запуска на чистой машине и самому
 * пользователю — если движок не собрался, эту команду можно выполнить
 * повторно, не открывая приложение.
 */
async function runSetupOnly() {
  try {
    if (bootstrap.isReady()) {
      console.log('SETUP_RESULT ' + JSON.stringify({ ok: true, skipped: true }));
      app.exit(0);
      return;
    }
    let last = '';
    const started = Date.now();
    await bootstrap.ensure((p) => {
      if (p.text === last) return;
      last = p.text;
      console.log(`SETUP ${Math.round(p.pct * 100)}% ${p.text}`);
    });
    console.log('SETUP_RESULT ' + JSON.stringify({
      ok: true, skipped: false, seconds: Math.round((Date.now() - started) / 1000),
    }));
    app.exit(0);
  } catch (err) {
    console.error('SETUP_RESULT ' + JSON.stringify({
      ok: false, error_ru: err.messageRu || String(err), detail: err.detail || '',
    }));
    app.exit(1);
  }
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

if (!IS_SMOKE && !IS_SETUP && !app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  ipcMain.handle('worker:info', () => ({ ...wm.info(), setup }));

  ipcMain.handle('dialog:pickFiles', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: 'Выберите музыку',
      properties: ['openFile', 'multiSelections'],
      filters: [{ name: 'Аудио', extensions: AUDIO_EXTENSIONS }],
    });
    return result.canceled ? [] : result.filePaths;
  });

  ipcMain.handle('shell:showInFolder', (_event, target) => {
    if (typeof target === 'string' && target) shell.showItemInFolder(path.normalize(target));
  });

  // Уведомление о готовности. Молчим, когда окно и так на экране: показывать
  // системное сообщение поверх того, что пользователь и так видит, — шум.
  ipcMain.handle('notify:done', (_event, payload) => {
    if (!Notification.isSupported()) return false;
    if (mainWindow && mainWindow.isVisible() && mainWindow.isFocused()) return false;
    const { title, body } = payload || {};
    const notification = new Notification({
      title: typeof title === 'string' && title ? title : 'MixPilot',
      body: typeof body === 'string' ? body : '',
      silent: false,
    });
    notification.on('click', () => {
      if (!mainWindow) return;
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    });
    notification.show();
    return true;
  });

  app.whenReady().then(async () => {
    if (IS_SETUP) {
      await runSetupOnly();
      return;
    }
    if (IS_SMOKE) {
      await runSmokeTest();
      return;
    }
    installMediaProtocol();
    createWindow();

    // Первый запуск (и первый после обновления зависимостей) доустанавливает
    // Python и библиотеки. Окно уже открыто — пользователь видит, что идёт.
    // В разработке окружением занимается `uv run`, доустановка не нужна.
    if (paths.packaged() && !bootstrap.isReady()) {
      setup = { active: true, pct: 0, text_ru: 'Готовим движок…', error_ru: null };
      try {
        await bootstrap.ensure((p) => {
          setup = { active: true, pct: p.pct, text_ru: p.text, error_ru: null };
        });
        setup = { active: false, pct: 1, text_ru: 'Готово', error_ru: null };
      } catch (err) {
        console.error('bootstrap failed:', err.detail || err);
        setup = {
          active: false, pct: 0, text_ru: '',
          error_ru: err.messageRu || 'Не удалось подготовить движок',
        };
        return; // без окружения worker не запустится — показываем ошибку
      }
    }

    try {
      await wm.start();
    } catch (err) {
      console.error('worker start failed:', err);
      // UI покажет статус offline; авторестарт-стратегия — M2.
    }
    checkForUpdates();
  });

  app.on('window-all-closed', () => app.quit());

  let quitting = false;
  app.on('before-quit', (event) => {
    if (quitting || IS_SMOKE || IS_SETUP) return;
    event.preventDefault();
    quitting = true;
    wm.stop().finally(() => app.quit());
  });
}
