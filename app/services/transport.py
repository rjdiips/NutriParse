"""One asynchronous HTTP client for every provider call.

The application lifespan creates a single :class:`httpx.AsyncClient` and wraps
it in :class:`ProviderTransport`. Model and image calls share that client, so
connections are reused and cancelling a request aborts the upstream call.

Two semaphores bound how much provider work can be in flight: three model calls
and one image generation. A slow image job therefore cannot occupy a model slot,
and concurrent Cook runs cannot starve the rest of the app.
"""

import asyncio

import httpx

LLM_CONCURRENCY = 3
IMAGE_CONCURRENCY = 1
# The initial attempt plus one retry per delay; a transient failure gets three
# total attempts with 0.5 s and then 1.5 s between them.
RETRY_DELAYS = (0.5, 1.5)


def is_retryable_status(status_code: int) -> bool:
    """429 and every 5xx are transient; any other 4xx is final."""
    return status_code == 429 or 500 <= status_code <= 599


class ProviderTransport:
    """A shared async client, two concurrency slots, and one retry policy."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        retry_delays=RETRY_DELAYS,
        sleep=asyncio.sleep,
    ):
        self.client = client
        self._retry_delays = tuple(retry_delays)
        self._sleep = sleep
        self._llm_slots = asyncio.Semaphore(LLM_CONCURRENCY)
        self._image_slots = asyncio.Semaphore(IMAGE_CONCURRENCY)

    async def close(self):
        """Close the shared client on application shutdown."""
        await self.client.aclose()

    async def post_llm(self, url, *, json, headers=None, timeout):
        """POST a model call inside one of the three model slots."""
        async with self._llm_slots:
            return await self._post_with_retries(
                url, json=json, headers=headers, timeout=timeout
            )

    async def post_image(self, url, *, json, headers=None, timeout):
        """POST an image call inside the single image slot."""
        async with self._image_slots:
            return await self._post_with_retries(
                url, json=json, headers=headers, timeout=timeout
            )

    async def _post_with_retries(self, url, *, json, headers, timeout):
        """POST JSON, retrying 429/5xx with the configured backoff.

        The caller holds a concurrency slot for the whole cycle, so only one
        attempt per logical call is ever active. Transport errors and other 4xx
        responses are returned or raised immediately: only 429/5xx are retried.
        """
        response = await self.client.post(
            url, json=json, headers=headers, timeout=timeout
        )
        for delay in self._retry_delays:
            if not is_retryable_status(response.status_code):
                break
            await self._sleep(delay)
            response = await self.client.post(
                url, json=json, headers=headers, timeout=timeout
            )
        return response
