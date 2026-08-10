# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: smoke.spec.ts >> compiled frontend smoke requires the backend contract
- Location: e2e\smoke.spec.ts:26:1

# Error details

```
Error: Backend obrigatório indisponível via FRONTEND_BASE_URL: Error: apiRequestContext.get: connect ECONNREFUSED 127.0.0.1:4173
Call log:
  - → GET http://127.0.0.1:4173/api/projects
    - user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.7922.34 Safari/537.36
    - accept: */*
    - accept-encoding: gzip,deflate,br

```

# Test source

```ts
  1  | import type { APIRequestContext } from '@playwright/test';
  2  | import { expect, test } from './fixtures';
  3  | 
  4  | async function requireBackend(request: APIRequestContext) {
  5  |   let response;
  6  |   try {
  7  |     response = await request.get('/api/projects');
  8  |   } catch (error) {
> 9  |     throw new Error(`Backend obrigatório indisponível via FRONTEND_BASE_URL: ${String(error)}`, { cause: error });
     |           ^ Error: Backend obrigatório indisponível via FRONTEND_BASE_URL: Error: apiRequestContext.get: connect ECONNREFUSED 127.0.0.1:4173
  10 |   }
  11 | 
  12 |   if (!response.ok()) {
  13 |     throw new Error(`Backend obrigatório indisponível: GET /api/projects retornou HTTP ${response.status()}.`);
  14 |   }
  15 | 
  16 |   const payload: unknown = await response.json();
  17 |   if (!Array.isArray(payload)) {
  18 |     throw new Error('Backend obrigatório inválido: GET /api/projects não retornou uma lista.');
  19 |   }
  20 | }
  21 | 
  22 | test.beforeEach(async ({ request }) => {
  23 |   await requireBackend(request);
  24 | });
  25 | 
  26 | test('compiled frontend smoke requires the backend contract', async ({ page }, testInfo) => {
  27 |   const response = await page.goto('/');
  28 |   expect(response?.ok(), 'compiled frontend must return a successful document response').toBeTruthy();
  29 |   await expect(page.getByTestId('app-shell')).toBeVisible();
  30 |   await page.screenshot({ path: testInfo.outputPath('frontend-smoke.png'), fullPage: true });
  31 | });
  32 | 
```