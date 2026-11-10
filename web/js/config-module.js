/* ES-module interface to the shared config client.

   config-client.js is plain classic JavaScript because the Node test requires
   it directly and older pages may still load it with a <script> tag. A file
   without import or export statements is also a valid ES module, so both pages
   import it for its side effect and read the named export below instead of a
   global. */

import './config-client.js';

/** @typedef {{serverMs: number|null, waitMs: number}} TimeoutChannel */
/** @typedef {{source: 'server'|'fallback', error: string|null, provider: string,
 *   model: string, parse: TimeoutChannel, cook: TimeoutChannel,
 *   image: TimeoutChannel}} ClientConfig */
/** @typedef {{FALLBACK_MS: number,
 *   load(fetchImpl?: typeof fetch): Promise<ClientConfig>,
 *   fromPayload(payload: unknown): ClientConfig,
 *   fallback(error: unknown): ClientConfig,
 *   channelFor(config: ClientConfig|null|undefined, kind: string): TimeoutChannel,
 *   describeFallback(config: ClientConfig): string}} ConfigGlobal */

/** @type {Window & {Config?: ConfigGlobal}} */
const scope = window;
if (!scope.Config) throw new Error('config-client.js did not register Config');

export const Config = scope.Config;
