import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],

  // base: './' makes all built asset paths relative — required for the DSS
  // iframe embedding where the app is served from a non-root path.
  base: './',

  // Expose ENABLE_* flags to the frontend (alongside the default VITE_* prefix).
  // This means one line per flag in app.env controls both backend and frontend —
  // no separate VITE_ENABLE_* duplicates needed.
  envPrefix: ['VITE_', 'ENABLE_'],

  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // Proxy /api calls to the FastAPI backend in local dev.
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },

  build: {
    outDir: 'dist',
    // Single-bundle output — code splitting breaks DSS resource loading.
    rollupOptions: {
      output: {
        entryFileNames: 'assets/index.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/index.[ext]',
      },
    },
  },

  resolve: {
    // Keep a single Vue instance (reka-ui and friends list vue as a peer dep).
    dedupe: ['vue', 'vue-router'],
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
