# 05: JavaScript type-checking prefactor

**What to build:** A private Node package manifest, a TypeScript configuration that checks JavaScript, and a `check:js` script that runs the type checker without emitting files. The command passes against the current frontend by declaring the shared globals, with no runtime or browser behavior change. This gives the module conversion a mechanical verification step.

**Blocked by:** None (can start immediately)

**Status:** done

**Decisions locked:**
- Add TypeScript as a dev dependency only.
- Use `allowJs`, `checkJs`, `noEmit`, ES2022 target and module, bundler resolution, and non-strict mode initially.
- Declare the current shared globals in a type declaration file.
- Commit the lockfile for reproducible installs.

- [x] A fresh install followed by `npm run check:js` succeeds from the repository root.
- [x] The checker passes on the current frontend with the shared-globals declaration.
- [x] No browser runtime behavior changes.
- [x] The development docs mention the command.
- [x] The Node tooling is dev-only; the Python runtime is unaffected.
- [x] The lockfile is committed.
