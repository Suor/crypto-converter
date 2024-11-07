# Crypto Converter

This project provides an API that performs currency conversions using live exchange rates stored in Redis. The exchange rates are retrieved from an external service (e.g., Binance) by a separate "Quote Consumer" process, which fetches quotes periodically and stores them to be used by API daemon. By default the conversion is done based on the latest available quotes, but it is also possible to specify a timestamp to use a quote closest to it.


## Running

The easiest way is to use docker:

```bash
docker compose up  # will start redis, api server and quote consumer
```

Alternatively one may set up a working copy and run it directly:

```bash
mkvirtualenv crypto -p python3.12  # or create and active virtualenv any other way
pip install -r req.txt
./run.py api &
./run.py consumer &
```

#### Configuration

It is possible to pass configuration via env vars or `.env` file:

```bash
# save only every minute, drop quotes older than 2 weeks
SAVE_INTERVAL=60 QUOTE_OBSOLETE_DAYS=14 ./run.py consumer

cp .env.sample .env
<edit> .env  # put your stuff, i.e. custom BINANCE_BASE_URL
```

#### Testing

Once a working copy is set up:

```bash
pip install -r req_dev.txt
pytest
```

## Using

Convert `ETH` to `BTC` using latest quote:

```bash
GET /?amount=25&from=ETH&to=BTC
{"amount": "0.940750", "rate": "0.037630000000"}
```

Same but use a timestamp in the past:

```bash
GET /?amount=25&from=ETH&to=BTC&at=1730986820
{"amount": "0.940750", "rate": "0.037630000000"}
```


## Design Decisions and Notes

1. Python 3.12, because why not.
2. FastAPI to implement API: needed something simple plus pydantic solves ENV vars as bonus.
3. Use Redis as storage, it's a good fit with its Sorted Sets. Easy to use, no setup required.
4. Split storage stuff into separate file to not mix in Redis lower level things.
5. Keep the rest together: small enough, won't need a separate settings.py with `Settings` to avoid circular imports and assignment said "Some common stuff like logging configuration, etc, on must be implemented in this file. [run.py]".

The rate at timestamp chooses the closest known quote whether it goes before or after it but it must be within 1 minute. The accepted range might be changed easy.

A currency pair like "ETHU" and "SDT" will kinda work using rate for "ETHUSDT". Ignoring this, otherwise we will need to manage a list of all available currencies.

Binance API rate precision is less then required 12 decimal digits. Storing whatever we got, quantizing to 12 digits just in case.

#### Skipped/postponed:

- proper logging instead of prints
- linters, pre-commit and stuff
- more riguorous testing


## Redis Data Structure

Quotes are stored as Redis **sorted sets** with keys having the format `quote:{symbol}`. The `{price}:{timestamp}` goes as a member, and the timestamp is the score.

Using timestamps as scores allows efficiently querying by time with `ZREVRANGE`, `ZRANGEBYSCORE` and dropping obsolete entires with `ZREMRANGEBYSCORE` commands.

The member is not simply price to not overwrite older entries, this is still a set.

#### Example:

- Key: `quote:BTCUSDT`
- Member: `50000.123456:1637172158`
    - `50000.123456`: The price of BTC/USDT.
    - `1637172158`: The timestamp when the price was fetched.
- Score: `1637172158` same timestamp
