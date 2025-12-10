import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    base: './', // Use relative paths for assets so it works in subfolder deployment
    build: {
        outDir: '../static/dist', // Build directly to Flask static folder
        emptyOutDir: true,
        assetsDir: 'assets',
        sourcemap: true,
    },
    server: {
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:5000',
                changeOrigin: true,
                secure: false,
            }
        }
    }
})
