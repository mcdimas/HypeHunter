import {defineConfig,devices} from '@playwright/test';
export default defineConfig({testDir:'tests/e2e',testMatch:'production.spec.mjs',workers:1,
  use:{baseURL:'https://hypehunter.ru',...devices['Desktop Chrome'],trace:'retain-on-failure',screenshot:'only-on-failure'},
  reporter:[['list'],['html',{open:'never'}]]});
