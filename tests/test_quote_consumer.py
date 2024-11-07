from functools import partial
import json
import time

from aiohttp import web
from freezegun import freeze_time
import pytest

from run import fetch_quotes
from storage import load_quotes
from .conftest import SAMPLE_QUOTES


@pytest.mark.asyncio
@freeze_time()
async def test_fetch_quotes(monkeypatch, redis, aiohttp_client):
    # Use aiohttp_client to simulate Binance API
    async def handler(request):
        return web.json_response(SAMPLE_QUOTES, dumps=partial(json.dumps, default=str))
    
    app = web.Application()
    app.router.add_get("/price", handler)
    client = await aiohttp_client(app)

    monkeypatch.setattr("run.Settings.price_url", client.make_url("/price"))

    await fetch_quotes(redis)

    # Verify that quotes were saved in Redis
    now = time.time()  # Frozen
    for item in SAMPLE_QUOTES:
        assert await load_quotes(redis, item["symbol"]) == [(item["price"], now)]
