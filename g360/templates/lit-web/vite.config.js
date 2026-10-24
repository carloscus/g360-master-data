import { defineConfig } from 'vite';

export default defineConfig({
  // GitHub Pages: descomenta y ajusta al publicar en https://<user>.github.io/<repo>/
  // base: '/<repo>/',
  server: {
    port: 3000,
  },
  build: {
    outDir: 'dist',
  },
});
