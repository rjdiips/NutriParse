/* NutriParse — server-driven AI timeouts.
   Both pages load this before their feature code and read the effective
   per-feature timeouts once at startup, along with the provider and model they
   belong to. Every client wait is the server timeout plus a margin, so the
   server's own error reaches the browser instead of the client aborting first.
   If the config call fails, the page keeps working with a generous safety net. */

(function (global) {
  const ENDPOINT = '/api/config';
  const MARGIN_MS = 10000;
  const FALLBACK_MS = 300000;
  const FETCH_TIMEOUT_MS = 5000;

  function milliseconds(value) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? Math.round(number) : null;
  }

  function timeoutChannel(serverMs) {
    return serverMs === null
      ? { serverMs: null, waitMs: FALLBACK_MS }
      : { serverMs, waitMs: serverMs + MARGIN_MS };
  }

  function channelFor(config, kind) {
    return (config && config[kind]) || { serverMs: null, waitMs: FALLBACK_MS };
  }

  /** @returns {ClientConfig} */
  function fromPayload(payload) {
    const body = payload && typeof payload === 'object' ? payload : {};
    const parse = milliseconds(body.parse_timeout_ms);
    const cook = milliseconds(body.cook_timeout_ms);
    const image = milliseconds(body.image_timeout_ms);
    if (parse === null || cook === null || image === null) {
      return fallback(new Error('the server returned incomplete timeouts'));
    }
    return {
      source: 'server',
      error: null,
      provider: typeof body.provider === 'string' ? body.provider : '',
      model: typeof body.model === 'string' ? body.model : '',
      parse: timeoutChannel(parse),
      cook: timeoutChannel(cook),
      image: timeoutChannel(image),
    };
  }

  function describeFallback(config) {
    const reason = config && config.error ? ` (${config.error})` : '';
    return `The server's timeout settings could not be read${reason}. `
      + `AI calls will wait up to ${FALLBACK_MS / 1000} seconds; the journal still works.`;
  }

  /** @returns {ClientConfig} */
  function fallback(error) {
    const reason = error instanceof Error ? error.message : String(error || 'unknown error');
    return {
      source: 'fallback',
      error: reason,
      provider: '',
      model: '',
      parse: { serverMs: null, waitMs: FALLBACK_MS },
      cook: { serverMs: null, waitMs: FALLBACK_MS },
      image: { serverMs: null, waitMs: FALLBACK_MS },
    };
  }

  /**
   * @param {typeof fetch} [fetchImpl]
   * @returns {Promise<ClientConfig>}
   */
  async function load(fetchImpl) {
    const doFetch = fetchImpl || global.fetch;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      const response = await doFetch(ENDPOINT, {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return fromPayload(await response.json());
    } catch (error) {
      const reason = error && error.name === 'AbortError'
        ? new Error('config request timed out')
        : error;
      return fallback(reason);
    } finally {
      clearTimeout(timer);
    }
  }

  global.Config = {
    FALLBACK_MS,
    load,
    fromPayload,
    fallback,
    channelFor,
    describeFallback,
  };
})(typeof window !== 'undefined' ? window : globalThis);
