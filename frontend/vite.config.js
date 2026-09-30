import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({mode}) =>{
  const env = loadEnv(mode, "../", ['VITE_', 'APP_'])
  return {
  plugins: [react()],
  server: {
    proxy: {
      '/api': env.APP_BASE_URL,
      '/upload': env.APP_BASE_URL,
    },
  },
  envDir: "../"
}
})
