import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // GitHub Pages: descomenta y ajusta al publicar en https://<user>.github.io/<repo>/
  // base: '/<repo>/',
  server: {
    port: 3000,
  },
  build: {
    outDir: 'dist',
  },
});
