import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests-browser',
  timeout: 30000,
  use: {
    baseURL: process.env.PLAYGROUND_URL || 'http://127.0.0.1:8766',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: process.env.PLAYGROUND_URL ? undefined : {
    command: 'python3 -m http.server 8766 --bind 127.0.0.1 --directory docs',
    url: 'http://127.0.0.1:8766',
    reuseExistingServer: !process.env.CI,
  },
});
