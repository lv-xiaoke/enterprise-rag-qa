import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1, timeout: 45000,
  outputDir: `./playwright-output/${Date.now()}`, reporter: [['list']],
  use: {baseURL: 'http://127.0.0.1:5177', browserName: 'chromium', channel: 'chromium', screenshot: 'only-on-failure', trace: 'retain-on-failure'},
  webServer: [
    {command: process.platform === 'win32' ? '..\\.venv-v1\\Scripts\\python.exe ..\\tests\\browser_server.py' : 'python ../tests/browser_server.py', url: 'http://127.0.0.1:8017/api/ready', timeout: 60000, reuseExistingServer: false},
    {command: 'npm run dev -- --port 5177 --strictPort', url: 'http://127.0.0.1:5177', timeout: 60000,
      env: {API_PROXY_TARGET:'http://127.0.0.1:8017'}, reuseExistingServer: false},
  ],
});
