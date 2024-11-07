import time
from datetime import datetime, timedelta
from decimal import Decimal

from freezegun import freeze_time
import pytest

from storage import save_quotes, load_quotes, get_latest_quote, get_quote_at, drop_obsolete_quotes
from .conftest import SAMPLE_QUOTES


@pytest.mark.asyncio
async def test_save_quotes(redis):
    with freeze_time() as frozen:
        first = time.time()
        await save_quotes(redis, SAMPLE_QUOTES)

        frozen.tick(10)
        second = time.time()
        await save_quotes(redis, SAMPLE_QUOTES)

    # Verify each quote is stored with the correct price and timestamp
    for item in SAMPLE_QUOTES:
        assert await load_quotes(redis, item["symbol"]) == [
            (item["price"], first),
            (item["price"], second),
        ]


@pytest.mark.asyncio
@freeze_time()
async def test_get_latest_quote(redis):
    symbol, price = "BTCUSDT", Decimal("45320.000000")
    assert await get_latest_quote(redis, symbol) is None

    await save_quotes(redis, [{"symbol": symbol, "price": price}])
    assert await get_latest_quote(redis, symbol) == (price, time.time())


@pytest.mark.asyncio
async def test_get_quote_at(redis):
    symbol, price = "BTCUSDT", Decimal("45320.000000")
    now = time.time()

    assert await get_quote_at(redis, symbol, now - 60 * 3) is None

    # Fill in last 5 minutes, price looses 1 every second
    for ago in range(1, 5 * 60, 30):
        await save_quotes(redis, [{"symbol": symbol, "price": price + ago}], now - ago)

    data = await load_quotes(redis, symbol)
    saved_price, saved_stamp = await get_quote_at(redis, symbol, now - 60 * 3)
    assert saved_price == price + 60 * 3 + 1

    # This is out of our period
    assert await get_quote_at(redis, symbol, now - 60 * 6) is None


@pytest.mark.asyncio
@freeze_time()
async def test_drop_obsolete_quotes(redis):
    max_age = 1000
    now = time.time()

    # Write obsolete and then new quotes
    with freeze_time(datetime.now() - timedelta(seconds=max_age + 1)):
        await save_quotes(redis, SAMPLE_QUOTES)
    await save_quotes(redis, SAMPLE_QUOTES) # These are new

    await drop_obsolete_quotes(redis, max_age)

    # Verify only recent quotes remain
    for item in SAMPLE_QUOTES:
        assert await load_quotes(redis, item["symbol"]) == [(item["price"], now)]


