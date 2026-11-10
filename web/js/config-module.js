/* ES-module interface to the shared config client.

   config-client.js is plain classic JavaScript because Food Journal loads it
   with a <script> tag and the Node test requires it directly. A file without
   import or export statements is also a valid ES module, so Compose imports it
   for its side effect and reads the named export below instead of a global. */

import './config-client.js';

/** @type {ConfigGlobal} */
export const Config = window.Config;
