import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  base: "/jsl-greensteel-foundation/",   // 👈 critical for GitHub Pages
})
