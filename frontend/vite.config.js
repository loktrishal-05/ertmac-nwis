/* global process */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

import { rewriteApiPath } from './src/services/apiRoutes.js'

// Dev/preview proxy to the backend (NWIS stack: WORKBENCH_API_PROXY=http://127.0.0.1:8011).
// Same origin in the browser, so the SameSite session cookie just works. NWIS routes are mounted
// under /api on the backend and keep the prefix; shared routes (/auth, /health, /audit/verify) live at
// the root and have it stripped — see src/services/apiRoutes.js.
const api = {
  '/api': {
    target: process.env.WORKBENCH_API_PROXY || 'http://localhost:8000',
    changeOrigin: true,
    rewrite: rewriteApiPath,
  },
}

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: api },
  preview: { port: 5173, strictPort: true, proxy: api },
})
