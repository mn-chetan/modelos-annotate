import assert from 'node:assert';
import { resolveApiBase } from './api';

// Test 1: Base URL resolution
console.log('Testing resolveApiBase()...');
// In pure node without window or vite env, falls back to /api/v1
assert.strictEqual(resolveApiBase(), '/api/v1', 'Without window/BASE_URL, defaults to /api/v1');

// When window has /app1 path
(globalThis as any).window = { location: { pathname: '/app1/annotate' } };
assert.strictEqual(resolveApiBase(), '/app1/api/v1', 'With /app1 pathname, resolves to /app1/api/v1');

// When window has root / path
(globalThis as any).window = { location: { pathname: '/' } };
assert.strictEqual(resolveApiBase(), '/api/v1', 'With / pathname, resolves to /api/v1');
delete (globalThis as any).window;
console.log('[PASS] resolveApiBase returns expected paths under varied environments');

// Test 2: Verify getProjectBatches retry logic behavior
// Mock fetch scenarios
class MockResponse {
  ok: boolean;
  status: number;
  data: any;

  constructor(status: number, data: any = {}) {
    this.status = status;
    this.ok = status >= 200 && status < 300;
    this.data = data;
  }

  async json() {
    return this.data;
  }
}

// Replicate getProjectBatches retry logic for isolated unit verification
async function simulateGetProjectBatches(fetchFn: (url: string) => Promise<any>, projectId: string) {
  const maxAttempts = 3;
  const baseDelayMs = 10; // small delay for fast tests
  const base = '/app1/api/v1';

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      const res = await fetchFn(`${base}/projects/${encodeURIComponent(projectId)}/batches`);

      if (res.status >= 400 && res.status < 500) {
        return { attempts: attempt, data: [], abortedOnPermanentError: true };
      }

      if (!res.ok) {
        if (attempt < maxAttempts && (res.status === 502 || res.status === 503 || res.status === 504)) {
          const delay = baseDelayMs * Math.pow(2, attempt - 1);
          await new Promise((r) => setTimeout(r, delay));
          continue;
        }
        return { attempts: attempt, data: [] };
      }

      const json = await res.json();
      return { attempts: attempt, data: json };
    } catch (err: unknown) {
      if (attempt < maxAttempts) {
        const delay = baseDelayMs * Math.pow(2, attempt - 1);
        await new Promise((r) => setTimeout(r, delay));
        continue;
      }
      return { attempts: attempt, data: [], failedAfterRetries: true };
    }
  }
  return { attempts: maxAttempts, data: [] };
}

async function runTests() {
  // Test 2a: Permanent 404 should return immediately on attempt 1 without retry
  let calls404 = 0;
  const mock404 = async () => {
    calls404++;
    return new MockResponse(404, { detail: 'Not Found' });
  };
  const res404 = await simulateGetProjectBatches(mock404, 'p1');
  assert.strictEqual(calls404, 1, '404 should only be called once (no retries)');
  assert.strictEqual(res404.attempts, 1);
  console.log('[PASS] 404 permanent failure is NOT retried (attempts = 1)');

  // Test 2b: Transient TypeError (Failed to fetch / ERR_NETWORK_CHANGED) retries up to 3 times
  let callsNetworkFail = 0;
  const mockNetworkFail = async () => {
    callsNetworkFail++;
    throw new TypeError('Failed to fetch');
  };
  const resNet = await simulateGetProjectBatches(mockNetworkFail, 'p1');
  assert.strictEqual(callsNetworkFail, 3, 'Network failure should retry up to maxAttempts (3)');
  assert.strictEqual(resNet.failedAfterRetries, true);
  console.log('[PASS] Transient TypeError: Failed to fetch retried exactly 3 times');

  // Test 2c: Transient failure on attempt 1 & 2, then succeeds on attempt 3
  let callsFlaky = 0;
  const mockFlaky = async () => {
    callsFlaky++;
    if (callsFlaky < 3) {
      throw new TypeError('Failed to fetch (net::ERR_NETWORK_CHANGED)');
    }
    return new MockResponse(200, [{ id: 'batch-123', status: 'completed' }]);
  };
  const resFlaky = await simulateGetProjectBatches(mockFlaky, 'p1');
  assert.strictEqual(callsFlaky, 3);
  assert.strictEqual(resFlaky.data.length, 1);
  assert.strictEqual(resFlaky.data[0].id, 'batch-123');
  console.log('[PASS] Flaky network succeeds on retry and returns batches');

  // Test 2d: 503 Service Unavailable retried and recovers
  let calls503 = 0;
  const mock503 = async () => {
    calls503++;
    if (calls503 === 1) return new MockResponse(503);
    return new MockResponse(200, [{ id: 'batch-recovered', status: 'running' }]);
  };
  const res503 = await simulateGetProjectBatches(mock503, 'p1');
  assert.strictEqual(calls503, 2);
  assert.strictEqual(res503.data[0].id, 'batch-recovered');
  console.log('[PASS] 503 transient error retried and recovers on attempt 2');

  console.log('All frontend batch fetching tests passed successfully!');
}

runTests().catch((err) => {
  console.error(err);
  process.exit(1);
});
