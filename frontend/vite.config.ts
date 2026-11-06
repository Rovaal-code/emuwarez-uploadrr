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
    // Las secciones van cada una en su chunk (AppShell): el mayor ronda los 220 kB (React). Que vuelva a avisar si
    // alguno crece mucho, o si una importación estática vuelve a meter una sección en el principal.
    chunkSizeWarningLimit: 300,
    rolldownOptions: {
      output: {
        codeSplitting: {
          // React y su planificador en un chunk propio, que cambia mucho menos que la app.
          groups: [{ name: 'react', test: /[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/ }],
        },
      },
    },
  },
})
