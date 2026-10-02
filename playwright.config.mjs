import { defineConfig, devices } from '@playwright/test';
import {resolve} from 'node:path';
const python = process.env.E2E_PYTHON || (process.platform === 'win32' ? resolve('.venv/Scripts/python.exe') : 'python');
export default defineConfig({
  testDir:'tests/e2e', testIgnore:'production.spec.mjs', fullyParallel:false, workers:1,
  timeout:45000, expect:{timeout:10000}, retries:process.env.CI ? 1 : 0,
  reporter:[['list'],['html',{open:'never'}]],
  use:{baseURL:'https://127.0.0.1:4174',ignoreHTTPSErrors:true,trace:'retain-on-failure',screenshot:'only-on-failure'},
  projects:[{name:'chromium',use:{...devices['Desktop Chrome']}},{name:'mobile',use:{...devices['Pixel 7']}}],
  webServer:[
    {command:`"${python}" tests/e2e/server.py`,url:'http://127.0.0.1:8001/api/health',reuseExistingServer:false,timeout:30000},
    {command:'node scripts/dev-server.mjs',url:'https://127.0.0.1:4174',ignoreHTTPSErrors:true,reuseExistingServer:false,env:{PORT:'4174',API_ORIGIN:'http://127.0.0.1:8001',E2E_TLS:'1'}},
  ],
});
