import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Carga variables desde archivo .env local
  const env = loadEnv(mode, (process as any).cwd(), '');

  return {
    plugins: [react()],
    build: {
      target: 'esnext' // IMPORTANTE: Esto permite "Top-level await" y soluciona el error de build
    },
    define: {
      // INTELIGENTE:
      // 1. Intenta leer 'env.API_KEY' (Tu archivo .env local)
      // 2. Si no existe, lee 'process.env.API_KEY' (La configuración de Netlify en la nube)
      'process.env.API_KEY': JSON.stringify(env.API_KEY || process.env.API_KEY)
    }
  }
})