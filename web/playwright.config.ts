import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  outputDir: '../build/browser-test-results',
  use: {
    baseURL: 'http://127.0.0.1:18766',
    viewport: { width: 1440, height: 1000 },
    colorScheme: 'light',
    launchOptions: { executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' },
  },
  webServer: {
    command: '../.venv/bin/python ../scripts/run_ui_server.py',
    url: 'http://127.0.0.1:18766/health',
    reuseExistingServer: false,
    timeout: 20_000,
  },
})
