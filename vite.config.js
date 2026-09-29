import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// host: true → the portal is reachable from other devices on the Wi-Fi
// (http://<laptop-ip>:5173), not just this laptop.
export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173, strictPort: true },
  preview: { host: true, port: 5173, strictPort: true },
})
