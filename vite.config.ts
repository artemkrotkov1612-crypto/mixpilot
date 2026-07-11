import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    target: 'chrome120',
  },
  server: {
    // Явный IPv4: Node 24 резолвит localhost в ::1, а Electron/wait-on ждут 127.0.0.1.
    host: '127.0.0.1',
    port: 3520,
    strictPort: true,
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
