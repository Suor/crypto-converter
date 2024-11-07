import time
from unittest.mock import patch

from fastapi.testclient import TestClient
from decimal import Decimal

from run import app


client = TestClient(app)


@patch("run.get_latest_quote")
def test_convert(mock):
    mock.return_value = (Decimal('1.234567'), time.time())
    response = client.get("/?amount=3&from=BTC&to=USDT")
    assert response.status_code == 200
    assert response.json() == {"amount": "3.703701", "rate": "1.234567000000"}

    mock.return_value = (Decimal('1.234567'), time.time() - 61)
    response = client.get("/?amount=3&from=BTC&to=USDT")
    assert response.status_code == 410
    assert response.json() == {"detail": "quotes_outdated"}


@patch("run.get_quote_at")
def test_convert_at(mock):
    stamp = time.time() - 3600

    mock.return_value = (Decimal('1.234567'), stamp)
    response = client.get("/?amount=3&from=BTC&to=USDT&at=%s" % stamp)
    assert response.status_code == 200
    assert response.json() == {"amount": "3.703701", "rate": "1.234567000000"}

    mock.return_value = None
    response = client.get("/?amount=3&from=BTC&to=USDT&at=%s" % stamp)
    assert response.status_code == 404
    assert response.json() == {"detail": "quote_not_found"}
