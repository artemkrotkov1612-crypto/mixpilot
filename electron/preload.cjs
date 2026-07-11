'use strict';

const { contextBridge, ipcRenderer, webUtils } = require('electron');

// Единственная поверхность renderer -> main. Расширяется по мере майлстоунов.
contextBridge.exposeInMainWorld('mixpilot', {
  /** Статус Python-worker: { status, port, meta } */
  workerInfo: () => ipcRenderer.invoke('worker:info'),
  /** Системный диалог выбора аудиофайлов -> массив путей. */
  pickFiles: () => ipcRenderer.invoke('dialog:pickFiles'),
  /** Показать файл в Проводнике. */
  showInFolder: (targetPath) => ipcRenderer.invoke('shell:showInFolder', targetPath),
  /** Абсолютный путь File из drag&drop (File.path убран в новых Electron). */
  getPathForFile: (file) => webUtils.getPathForFile(file),
});
