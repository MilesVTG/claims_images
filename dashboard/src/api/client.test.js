import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Must import after mocking fetch
let api;

describe('api.upload', () => {
  const originalFetch = globalThis.fetch;
  const originalSessionStorage = globalThis.sessionStorage;

  let mockFetch;
  let storage = {};

  beforeEach(async () => {
    storage = {};
    Object.defineProperty(globalThis, 'sessionStorage', {
      value: {
        getItem: (key) => storage[key] ?? null,
        setItem: (key, val) => { storage[key] = val; },
        removeItem: (key) => { delete storage[key]; },
      },
      writable: true,
      configurable: true,
    });

    mockFetch = vi.fn();
    globalThis.fetch = mockFetch;

    // Fresh import each test to reset module state
    const mod = await import('./client.js');
    api = mod.default;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    globalThis.sessionStorage = originalSessionStorage;
    vi.restoreAllMocks();
  });

  it('sends FormData without Content-Type header', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ storage_key: 'a/b/photo_001.jpg', status: 'uploaded' }),
    });

    const formData = new FormData();
    formData.append('file', new Blob(['pixels'], { type: 'image/jpeg' }), 'test.jpg');
    formData.append('contract_id', 'CNT-001');
    formData.append('claim_id', 'CLM-001');

    await api.upload('/photos/upload', formData);

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain('/photos/upload');
    expect(options.method).toBe('POST');
    expect(options.body).toBe(formData);
    // Must NOT set Content-Type — browser sets multipart boundary
    expect(options.headers['Content-Type']).toBeUndefined();
  });

  it('includes auth token when present', async () => {
    storage.token = 'test-jwt-token';

    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ storage_key: 'x', status: 'uploaded' }),
    });

    const formData = new FormData();
    await api.upload('/photos/upload', formData);

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers['Authorization']).toBe('Bearer test-jwt-token');
  });

  it('does not include auth header when no token', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ storage_key: 'x', status: 'uploaded' }),
    });

    const formData = new FormData();
    await api.upload('/photos/upload', formData);

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers['Authorization']).toBeUndefined();
  });

  it('throws on non-ok response with detail message', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'File type not allowed' }),
    });

    const formData = new FormData();
    await expect(api.upload('/photos/upload', formData)).rejects.toThrow('File type not allowed');
  });

  it('throws generic message when response has no detail', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error('not json')),
    });

    const formData = new FormData();
    await expect(api.upload('/photos/upload', formData)).rejects.toThrow('Upload failed: 500');
  });

  it('redirects to login on 401', async () => {
    const mockLocation = { href: '' };
    Object.defineProperty(globalThis, 'window', {
      value: { location: mockLocation },
      writable: true,
      configurable: true,
    });

    storage.token = 'expired-token';

    mockFetch.mockResolvedValue({
      ok: false,
      status: 401,
    });

    const formData = new FormData();
    await expect(api.upload('/photos/upload', formData)).rejects.toThrow('Unauthorized');
    expect(storage.token).toBeUndefined();
    expect(mockLocation.href).toBe('/login');
  });

  it('returns parsed JSON on success', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ storage_key: 'CNT/CLM/photo_001.jpg', status: 'uploaded' }),
    });

    const formData = new FormData();
    const result = await api.upload('/photos/upload', formData);
    expect(result).toEqual({ storage_key: 'CNT/CLM/photo_001.jpg', status: 'uploaded' });
  });
});
