/* Compatibility entry point for pages built before the JavaScript split.
   New pages load /assets/js/nutriparse.js followed by the focused modules in
   their own script tags. This loader keeps the old /nutriparse.js URL working:
   it loads the shared core first, then the modules in the order they expect. */
(function () {
  var files = [
    '/assets/js/nutriparse.js',
    '/assets/js/nutriparse/request.js',
    '/assets/js/nutriparse/estimate.js',
    '/assets/js/nutriparse/recipes.js',
    '/assets/js/nutriparse/inspector.js',
    '/assets/js/nutriparse/journal.js',
    '/assets/js/nutriparse/samples.js',
    '/assets/js/nutriparse/boot.js',
  ];
  files.forEach(function (source) {
    var script = document.createElement('script');
    script.src = source;
    script.async = false;
    document.head.appendChild(script);
  });
})();
