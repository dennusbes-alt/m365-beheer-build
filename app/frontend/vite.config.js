import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Ontwikkelen: start de backend met "python backend/run.py --dev --mock" (poort 8765) en daarna "npm run dev".
export default defineConfig({
  plugins: [react()],
  base: './',
  build: { outDir: 'dist', assetsInlineLimit: 0, chunkSizeWarningLimit: 900 },
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true } },
  },
});
