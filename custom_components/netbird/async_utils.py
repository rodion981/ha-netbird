"""Lifetime management for bounded batches of NetBird requests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable


async def async_gather_cancel_on_error[T](
    *requests: Awaitable[T],
) -> list[T]:
    """Cancel and drain siblings before propagating failure or cancellation."""
    tasks = [asyncio.ensure_future(request) for request in requests]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
