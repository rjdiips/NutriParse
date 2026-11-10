/* Classic-script compatibility shim for the shared journal client.

   The implementation lives in journal-store.js as native ES modules, and the
   Compose page imports it directly. Food Journal still loads this file as a
   classic script, so window.JournalStore forwards each call to the module.
   The module load starts alongside the page and every forwarded call waits for
   it, which keeps the classic global's async contract intact. */

(function (global) {
  /* Absolute because the legacy /journal-client.js alias is served from a
     different directory than /assets/js/journal-client.js. */
  // @ts-ignore -- browser-resolved URL, not a path relative to this file
  const store = import('/assets/js/journal-store.js');

  /** @param {'read'|'addEntries'|'updateEntries'|'removeEntry'|'setGoal'|'claimBrowserEntries'} name */
  const forward = (name) => (...args) => store.then((module) => module[name](...args));

  global.JournalStore = {
    read: forward('read'),
    addEntries: forward('addEntries'),
    updateEntries: forward('updateEntries'),
    removeEntry: forward('removeEntry'),
    setGoal: forward('setGoal'),
    claimBrowserEntries: forward('claimBrowserEntries'),
  };
})(window);
