import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8001',
      '/datasets': 'http://127.0.0.1:8001',
      '/workbench': 'http://127.0.0.1:8001',
    },
  },
});
