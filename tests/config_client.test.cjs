/* Client-side timeout rules, run by tests/test_client_config.py with Node. */

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

require(path.join(__dirname, '..', 'web', 'js', 'config-client.js'));
const Config = globalThis.Config;

function response(body, ok = true, status = 200) {
  return { ok, status, json: async () => body };
}

test('server timeouts gain a ten-second client margin', () => {
  const config = Config.fromPayload({
    provider: 'local',
    model: 'qwen-test',
    parse_timeout_ms: 180000,
    cook_timeout_ms: 180000,
    image_timeout_ms: 240000,
  });

  assert.equal(config.source, 'server');
  assert.equal(config.provider, 'local');
  assert.equal(config.model, 'qwen-test');
  assert.deepEqual(config.parse, { serverMs: 180000, waitMs: 190000 });
  assert.deepEqual(config.cook, { serverMs: 180000, waitMs: 190000 });
  assert.deepEqual(config.image, { serverMs: 240000, waitMs: 250000 });
});

test('a missing or malformed timeout uses the overall safety net', () => {
  const config = Config.fromPayload({
    provider: 'local',
    parse_timeout_ms: 'slow',
    cook_timeout_ms: 0,
  });

  assert.equal(config.source, 'fallback');
  assert.match(config.error, /incomplete timeouts/);
  for (const kind of ['parse', 'cook', 'image']) {
    assert.equal(config[kind].serverMs, null);
    assert.equal(config[kind].waitMs, Config.FALLBACK_MS);
  }
});

test('the fallback description names the safety net', () => {
  const config = Config.fallback(new Error('offline'));
  assert.match(Config.describeFallback(config), /offline/);
  assert.match(Config.describeFallback(config), /300 seconds/);
});

test('a failed config request returns the 300-second safety net', async () => {
  const config = await Config.load(async () => {
    throw new Error('offline');
  });

  assert.equal(config.source, 'fallback');
  assert.match(config.error, /offline/);
  for (const kind of ['parse', 'cook', 'image']) {
    assert.equal(config[kind].serverMs, null);
    assert.equal(config[kind].waitMs, 300000);
  }
});

test('a timed-out config request reports a clear reason', async () => {
  const aborted = new Error('aborted');
  aborted.name = 'AbortError';
  const config = await Config.load(async () => {
    throw aborted;
  });
  assert.equal(config.source, 'fallback');
  assert.match(config.error, /timed out/);
});

test('a non-ok config response also uses the safety net', async () => {
  const config = await Config.load(async () => response({}, false, 503));
  assert.equal(config.source, 'fallback');
  assert.match(config.error, /503/);
  assert.equal(config.parse.waitMs, 300000);
});

test('a good response is requested without caching and accepted', async () => {
  const config = await Config.load(async (endpoint, options) => {
    assert.equal(endpoint, '/api/config');
    assert.equal(options.cache, 'no-store');
    return response({
      provider: 'openrouter',
      model: 'openrouter/free',
      parse_timeout_ms: 30000,
      cook_timeout_ms: 45000,
      image_timeout_ms: 240000,
    });
  });

  assert.equal(config.source, 'server');
  assert.equal(config.parse.waitMs, 40000);
  assert.equal(config.cook.waitMs, 55000);
  assert.equal(config.image.waitMs, 250000);
});
