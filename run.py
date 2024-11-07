#!/usr/bin/env python3
from __future__ import annotations
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
import json
import os
import sys
import time
import posixpath

import aiohttp
import asyncio
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings
from redis.exceptions import RedisError
import redis.asyncio as aioredis
import uvicorn

from storage import save_quotes, get_latest_quote, get_quote_at, drop_obsolete_quotes, PricePair


class Settings(BaseSettings):
    binance_base_url: str = "https://api.binance.com"
    tickers: list[str] | None = None
    redis_url: str = "redis://localhost:6379"
    save_interval: int = 30
    quote_obsolete_days: int = 7
    quote_fresh_seconds: int = 60

    model_config = ConfigDict(env_file=".env")

    @property
    def quote_obsolete_seconds(self):
        return self.quote_obsolete_days * 24 * 3600

    @property
    def price_url(self):
        return posixpath.join(self.binance_base_url, "api/v3/ticker/price")

settings = Settings()
redis = aioredis.from_url(settings.redis_url, decode_responses=True)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"api", "consumer"}:
        print("Usage: python run.py [api|consumer]")
        sys.exit(1)

    if sys.argv[1] == "api":
        print("Starting API...")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    elif sys.argv[1] == "consumer":
        print("Starting Quote Consumer...")
        asyncio.run(quote_consumer())


# API

RATE_QUANT = Decimal('1.000000000000')
AMOUNT_QUANT = Decimal('1.000000')

app = FastAPI()


@app.middleware("http")
async def handle_redis_failure(request, call_next):
    try:
        return await call_next(request)
    except RedisError as e:  # May choose something more specific
        print("Redis connection failed: %s" % e)
        return JSONResponse(status_code=503, content={"detail": "temporary_unavailable"})


class Result(BaseModel):
    amount: Decimal
    rate: Decimal


@app.get("/")
async def convert(
    amount: Decimal = Query(..., gt=0),
    from_: str = Query(..., min_length=1, max_length=10, alias="from", description="Currency ticker to convert from."),
    to: str = Query(..., min_length=1, max_length=10, description="Currency ticker to convert to."),
    at: float = Query(None, description="Timestamp to fetch the quote for.")
) -> Result:
    symbol = f"{from_}{to}"
    if at is not None:
        pair = await get_quote_at(redis, symbol, at)
        if pair is None:
            raise HTTPException(status_code=404, detail="quote_not_found")

        quote, _ = pair
    else:
        pair = await get_latest_quote(redis, symbol)
        if pair is None:
            raise HTTPException(status_code=404, detail="currency_pair_not_found")

        quote, timestamp = pair
        if timestamp < time.time() - settings.quote_fresh_seconds:
            raise HTTPException(status_code=410, detail="quotes_outdated")

    rate = quote.quantize(RATE_QUANT, rounding=ROUND_DOWN)
    result_amount = (amount * rate).quantize(AMOUNT_QUANT, rounding=ROUND_DOWN)

    return Result(amount=result_amount, rate=rate)


# Quote consumer

async def quote_consumer():
    # async with aioredis.from_url(settings.redis_url, decode_responses=True) as redis:
    while True:
        try:
            start = time.time()
            await fetch_quotes(redis)
            await drop_obsolete_quotes(redis, settings.quote_obsolete_seconds)

            # Wait the remaining part of the interval
            await asyncio.sleep(settings.save_interval - (time.time() - start))

        except (asyncio.CancelledError, KeyboardInterrupt):
            print("Shutting down quote consumer...")
            break


async def fetch_quotes(redis):
    async with aiohttp.ClientSession() as session:
        params = {}
        # Limit the request to only the tickers we are interested in,
        if settings.tickers:
            # NOTE: we need to use separators= because binance won't accept spaces there.
            params = {"symbols": json.dumps(settings.tickers, separators=(",", ":"))}

        async with session.get(settings.price_url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                await save_quotes(redis, data)
                print(f"Fetched and saved quotes for {len(data)} symbols at {datetime.now()}")
            else:
                print(f"Failed to fetch: {response.status}\n\n" + await response.text())


if __name__ == "__main__":
    main()
