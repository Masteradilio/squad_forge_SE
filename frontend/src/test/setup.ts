import { vi } from 'vitest';

Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: vi.fn(),
});

class TestEventSource {
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readonly url: string;

  constructor(url: string) {
    this.url = url;
  }

  addEventListener(): void {
    // The component tests cover rendering/reconnection; live SSE is tested by
    // the integration suite against the API rather than by jsdom.
  }

  close(): void {}
}

Object.defineProperty(globalThis, 'EventSource', {
  configurable: true,
  value: TestEventSource,
});
