import { defineConfig } from "@playwright/test";

// E2E_PORT: dev server port (default 5173). E2E_API: backend URL passed to Vite as VITE_API_URL.
const port = Number(process.env.E2E_PORT ?? 5173);
const viewports = { desktop: [1440, 900], laptop: [1024, 768], mobile: [390, 844] } as const;

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:${port}` },
  projects: Object.entries(viewports).map(([name, [width, height]]) => ({
    name,
    use: { browserName: "chromium", viewport: { width, height } },
  })),
  webServer: {
    command: `npm run dev -- --port ${port} --strictPort`,
    url: `http://localhost:${port}`,
    reuseExistingServer: true,
    env: { VITE_API_URL: process.env.E2E_API ?? "http://localhost:8000" },
  },
});
