# 04: Cacheable recipe images

**What to build:** A generated recipe image is written once under a content hash and served from a cacheable URL. The image endpoint returns a small JSON body with an image URL and a cached flag instead of a multi-megabyte base64 string. Repeat Cook runs for the same recipe reuse the stored file, and both pages render the URL.

**Blocked by:** 03 — Non-blocking AI and image transport

**Status:** done

**Decisions locked:**
- Hash the normalized prompt plus width, height, and steps with SHA-256.
- Store one PNG per hash in a gitignored cache directory.
- The image endpoint returns an image URL and a cached flag.
- Serve cached images with a one-year immutable cache header.
- No automatic eviction in this version; document that deleting the cache directory clears it.

- [x] The first request generates and stores an image; a second request for the same recipe and dimensions returns `cached: true` without generating again.
- [x] The POST response is small JSON with an image URL and cached flag; it contains no base64 image data.
- [x] The image URL serves the PNG with the immutable cache header and the correct image content type.
- [x] Both Compose and Food Journal render images from the returned URL.
- [x] An unknown hash returns 404; disabled image generation still returns 503.
- [x] The cache directory is ignored by Git, and clearing it is documented.
- [x] Tests cover cache hit, cache miss, headers, and unknown hash; the full suite and lint pass.
