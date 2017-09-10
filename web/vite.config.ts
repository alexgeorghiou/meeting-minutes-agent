import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// During development the Vite server proxies /api to the FastAPI backend.
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
