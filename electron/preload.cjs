'use strict';

const { contextBridge, ipcRenderer } = require('electron');

// Единственная поверхность renderer -> main. Расширяется по мере майлстоунов.
contextBridge.exposeInMainWorld('mixpilot', {
  /** Статус Python-worker: { status, port, meta } */
  workerInfo: () => ipcRenderer.invoke('worker:info'),
});
