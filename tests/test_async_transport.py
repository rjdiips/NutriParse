#!/usr/bin/env python3
"""Shared async transport: retry policy, bounded concurrency, cancellation.

Every test here stubs HTTP with ``httpx.MockTransport``; no provider or image
service is contacted.
"""

import asyncio
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    import httpx
    from fastapi import HTTPException

    from app.services.transport import (
        IMAGE_CONCURRENCY,
        LLM_CONCURRENCY,
        ProviderTransport,
    )
    from app.web.dependencies import cancel_on_disconnect
except Exception as error:  # pragma: no cover - only without dependencies
    ProviderTransport = None
    SKIP_REASON = f"Transport dependencies are unavailable: {error}"


@unittest.skipUnless(ProviderTransport is not None, globals().get("SKIP_REASON", ""))
class TestRetryPolicy(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.aclose()

    def make_transport(self, handler, *, retry_delays=(0.5, 1.5), sleep=None):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.clients.append(client)
        kwargs = {"retry_delays": retry_delays}
        if sleep is not None:
            kwargs["sleep"] = sleep
        return ProviderTransport(client, **kwargs)

    async def post(self, transport):
        return await transport.post_llm(
            "http://provider.test/call", json={}, timeout=5
        )

    async def test_429_and_5xx_retry_with_stated_backoff(self):
        statuses = [500, 429, 200]
        calls = []
        delays = []

        def handler(request):
            calls.append(request.url)
            return httpx.Response(statuses[len(calls) - 1])

        async def sleep(delay):
            delays.append(delay)

        transport = self.make_transport(handler, sleep=sleep)
        response = await self.post(transport)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 3)
        self.assertEqual(delays, [0.5, 1.5])

    async def test_three_total_attempts_then_the_last_response(self):
        statuses = [500, 502, 503]
        calls = []
        delays = []

        def handler(request):
            calls.append(request.url)
            return httpx.Response(statuses[len(calls) - 1])

        async def sleep(delay):
            delays.append(delay)

        transport = self.make_transport(handler, sleep=sleep)
        response = await self.post(transport)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(calls), 3)
        self.assertEqual(delays, [0.5, 1.5])

    async def test_other_4xx_is_never_retried(self):
        calls = []
        delays = []

        def handler(request):
            calls.append(request.url)
            return httpx.Response(400)

        async def sleep(delay):
            delays.append(delay)

        transport = self.make_transport(handler, sleep=sleep)
        response = await self.post(transport)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(calls), 1)
        self.assertEqual(delays, [])

    async def test_transport_errors_are_not_retried(self):
        calls = []

        def handler(request):
            calls.append(request.url)
            raise httpx.ConnectError("provider down")

        transport = self.make_transport(handler)
        with self.assertRaises(httpx.ConnectError):
            await self.post(transport)
        self.assertEqual(len(calls), 1)


@unittest.skipUnless(ProviderTransport is not None, globals().get("SKIP_REASON", ""))
class TestConcurrencyLimits(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clients = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.aclose()

    def make_transport(self, handler):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.clients.append(client)
        return ProviderTransport(client, retry_delays=())

    async def run_concurrently(self, method, count):
        return await asyncio.gather(*(method(
            "http://provider.test/call", json={}, timeout=5
        ) for _ in range(count)))

    async def test_llm_calls_never_exceed_three(self):
        active = 0
        peak = 0
        gate = asyncio.Event()

        async def handler(request):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await gate.wait()
            active -= 1
            return httpx.Response(200)

        transport = self.make_transport(handler)
        task = asyncio.create_task(
            self.run_concurrently(transport.post_llm, LLM_CONCURRENCY + 4)
        )
        await asyncio.sleep(0.05)
        self.assertEqual(peak, LLM_CONCURRENCY)
        gate.set()
        await task
        self.assertEqual(peak, LLM_CONCURRENCY)

    async def test_image_calls_never_exceed_one(self):
        active = 0
        peak = 0
        gate = asyncio.Event()

        async def handler(request):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await gate.wait()
            active -= 1
            return httpx.Response(200)

        transport = self.make_transport(handler)
        task = asyncio.create_task(
            self.run_concurrently(transport.post_image, IMAGE_CONCURRENCY + 3)
        )
        await asyncio.sleep(0.05)
        self.assertEqual(peak, IMAGE_CONCURRENCY)
        gate.set()
        await task
        self.assertEqual(peak, IMAGE_CONCURRENCY)


class _FakeRequest:
    def __init__(self, disconnects):
        self.disconnects = disconnects

    async def receive(self):
        if self.disconnects:
            return {"type": "http.disconnect"}
        await asyncio.Event().wait()


@unittest.skipUnless(ProviderTransport is not None, globals().get("SKIP_REASON", ""))
class TestDisconnectCancellation(unittest.IsolatedAsyncioTestCase):
    async def test_a_disconnect_cancels_the_upstream_operation(self):
        cancelled = asyncio.Event()

        async def operation():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with self.assertRaises(HTTPException) as caught:
            await cancel_on_disconnect(_FakeRequest(disconnects=True), operation)

        self.assertEqual(caught.exception.status_code, 499)
        self.assertTrue(cancelled.is_set())

    async def test_a_finished_operation_returns_without_waiting(self):
        async def operation():
            return 42

        result = await cancel_on_disconnect(_FakeRequest(disconnects=False), operation)

        self.assertEqual(result, 42)


if __name__ == "__main__":
    unittest.main()
