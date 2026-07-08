import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Where the dev server proxies /api/* to. Defaults to the local host API on
// :8000 (uvicorn); override to point at another backend, e.g. the offline
// deploy lab on :8100:
//   PULSEGRAPH_API_PROXY=http://localhost:8100 npm run dev
const apiTarget = process.env.PULSEGRAPH_API_PROXY ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [tailwindcss(), react()],
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
