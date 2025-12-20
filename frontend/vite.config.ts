import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// import { VitePWA } from 'vite-plugin-pwa'  // Disabled temporarily until Phase 8

export default defineConfig({
  plugins: [
    react(),
    // PWA plugin disabled temporarily - will be enabled in Phase 8 (PWA Features)
    // VitePWA({
    //   registerType: 'autoUpdate',
    //   includeAssets: ['favicon.ico', 'robots.txt', 'apple-touch-icon.png'],
    //   manifest: {
    //     name: 'GTFS Editor',
    //     short_name: 'GTFS Editor',
    //     description: 'Multi-agency GTFS data editor with real-time collaboration',
    //     theme_color: '#ffffff',
    //     icons: [
    //       {
    //         src: 'pwa-192x192.png',
    //         sizes: '192x192',
    //         type: 'image/png',
    //       },
    //       {
    //         src: 'pwa-512x512.png',
    //         sizes: '512x512',
    //         type: 'image/png',
    //       },
    //     ],
    //   },
    //   workbox: {
    //     globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
    //     runtimeCaching: [
    //       {
    //         urlPattern: /^https:\/\/api\.mapbox\.com\/.*/i,
    //         handler: 'CacheFirst',
    //         options: {
    //           cacheName: 'mapbox-cache',
    //           expiration: {
    //             maxEntries: 10,
    //             maxAgeSeconds: 60 * 60 * 24 * 7, // 1 week
    //           },
    //           cacheableResponse: {
    //             statuses: [0, 200],
    //           },
    //         },
    //       },
    //     ],
    //   },
    // }),
  ],
  server: {
    host: true,
    port: 5173,
    allowedHosts: true,  // Allow all hosts (team subdomains)
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
