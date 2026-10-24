import { defineConfig } from 'vite';
import solidPlugin from 'vite-plugin-solid';

export default defineConfig({
  plugins: [solidPlugin()],
  // GitHub Pages: descomenta y ajusta al publicar en https://<user>.github.io/<repo>/
  // base: '/<repo>/',
  server: {
    port: 3000,
  },
  build: {
    outDir: 'dist',
  },
});
