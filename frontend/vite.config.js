import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
const env = loadEnv(mode, process.cwd(), '')
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': env.APP_BASE_URL,
      '/upload': env.APP_BASE_URL,
    },
  },
  envDir: "../"
})
