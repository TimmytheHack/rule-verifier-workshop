import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

const backendTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8001';

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': backendTarget,
      '/datasets': backendTarget,
      '/workbench': backendTarget,
      '/settings': backendTarget,
    },
  },
});
