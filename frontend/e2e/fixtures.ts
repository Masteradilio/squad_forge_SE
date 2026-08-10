import { test as base, expect } from '@playwright/test';

export const test = base.extend<{ browserConsole: string[] }>({
  browserConsole: async ({ page }, provideFixture, testInfo) => {
    const entries: string[] = [];
    page.on('console', (message) => entries.push(`[console:${message.type()}] ${message.text()}`));
    page.on('pageerror', (error) => entries.push(`[pageerror] ${error.message}`));
    page.on('requestfailed', (request) => entries.push(`[requestfailed] ${request.method()} ${request.url()} ${request.failure()?.errorText ?? ''}`));

    await provideFixture(entries);

    if (testInfo.status !== testInfo.expectedStatus) {
      await testInfo.attach('browser-console.log', {
        body: entries.length > 0 ? entries.join('\n') : 'No browser console entries captured.',
        contentType: 'text/plain',
      });
    }
  },
});

export { expect };
