import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { codecovVitePlugin } from '@codecov/vite-plugin'

export default defineConfig({
  plugins: [
    react(),
    // Sube el tamaño del bundle a Codecov solo donde hay CODECOV_TOKEN (el CI); si la subida falla, el build sigue.
    codecovVitePlugin({
      enableBundleAnalysis: Boolean(process.env.CODECOV_TOKEN),
      bundleName: 'frontend',
      uploadToken: process.env.CODECOV_TOKEN,
      telemetry: false,
    }),
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:9494',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // El bundle de la app ronda los 500 kB; sin esto Vite 8 avisa por unos pocos kB.
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        // Vite 8 (Rolldown) solo admite manualChunks como función.
        manualChunks(id) {
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) return 'react'
        },
      },
    },
  },
})
