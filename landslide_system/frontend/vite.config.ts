import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    // Exclude maplibre-gl from Vite's dependency pre-bundling.
    // MapLibre uses web workers that Vite's esbuild optimizer corrupts when bundled.
    exclude: ['maplibre-gl'],
  },
})
