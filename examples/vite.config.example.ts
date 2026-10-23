// A Vite config that works both at the site root and under a gateway path.
//
//   npm run dev                                         -> http://localhost:5173/
//   VITE_BASE_PATH=/prajna/ npm run dev -- --host 127.0.0.1 --port 8200 --strictPort
//                                                       -> http://<tailscale-ip>:8280/prajna/
//
// You can also skip this file change entirely and pass --base /prajna/ on the command line.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // '/' unless the environment says otherwise; must start and end with a slash
  base: process.env.VITE_BASE_PATH ?? '/',
  server: {
    host: '127.0.0.1',   // only the gateway can reach the dev server
    strictPort: true,
    // Do not set hmr.port: hot reload then connects back through the gateway port.
    // If the browser console shows WebSocket errors, add: hmr: { clientPort: 8280 }
  },
  preview: {
    host: '127.0.0.1',
    strictPort: true,
  },
})
