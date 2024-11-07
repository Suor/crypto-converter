from decimal import Decimal

import pytest_asyncio
import redis.asyncio as aioredis

from storage import save_quotes


REDIS_URL = "redis://localhost:6379/13"  # Use db 13 for testing
SAMPLE_QUOTES = [
    {"symbol": "BTCUSDT", "price": Decimal("50000.00")},
    {"symbol": "ETHUSDT", "price": Decimal("3000.00")},
]


@pytest_asyncio.fixture
async def redis():
    async with aioredis.from_url(REDIS_URL, decode_responses=True) as client:
        await client.flushdb()
        yield client
