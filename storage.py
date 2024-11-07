from __future__ import annotations
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
import time

if TYPE_CHECKING:
    from redis.asyncio import Redis


type PricePair = tuple[Decimal, float]


async def save_quotes(redis: Redis, quotes, timestamp=None):
    timestamp = time.time() if timestamp is None else timestamp
    async with redis.pipeline(transaction=False) as pipe:  # Don't need atomicity here
        for item in quotes:
            key = _quote_key(item["symbol"])
            pipe.zadd(key, _encode_pair(item["price"], timestamp))
        await pipe.execute()


async def load_quotes(redis: Redis, symbol) -> list[PricePair]:
    key = _quote_key(symbol)
    result = await redis.zrange(key, 0, -1, withscores=True)
    return [_decode_pair(p) for p in result]


async def get_latest_quote(redis: Redis, symbol) -> PricePair | None:
    key = _quote_key(symbol)
    result = await redis.zrevrange(key, 0, 0, withscores=True)
    return _decode_pair(result[0]) if result else None


async def get_quote_at(redis: Redis, symbol, timestamp, maxdev=60) -> PricePair | None:
    key = _quote_key(symbol)
    result = await redis.zrangebyscore(key, timestamp - maxdev, timestamp + maxdev, withscores=True)
    if not result:
        return None
    candidates = [_decode_pair(p) for p in result]
    return min(candidates, key=lambda p: abs(p[1] - timestamp))


async def drop_obsolete_quotes(redis: Redis, max_age: int):
    cutoff = time.time() - max_age

    # Remove quotes from sorted sets where the score (timestamp) is older than expiry
    # NOTE: this might be parallelized more aggressively, i.e. pipelining zremrangebyscore() for
    #       chunks of keys. However, we don't need this, so going for code simplicity instead.
    async for key in redis.scan_iter(_quote_key("*"), count=100):
        removed_count = await redis.zremrangebyscore(key, "-inf", cutoff)
        if removed_count:
            print(f"Removed {removed_count} old quotes from {key}")


# Lower level stuff
# NOTE: use unix timestamp for simplicity of encoding. Will need to be careful with timezones if we
#       will get datetime or any string representation of that in the future.

def _quote_key(symbol):
    return f"quote:{symbol}"

def _encode_pair(price, timestamp):
    key = f"{price}:{timestamp}"  # Add timestamp so that same prices won't overwrite each other
    return {key: timestamp}

def _decode_pair(pair):
    value, timestamp = pair
    price, _ = value.split(":")
    return Decimal(price), timestamp
