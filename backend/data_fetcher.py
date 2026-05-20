from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime

import numpy as np
import pandas as pd

ak = None
executor = ThreadPoolExecutor(max_workers=2)


def run_with_timeout(func, seconds=8):
    future = executor.submit(func)
    try:
        return future.result(timeout=seconds)
    except TimeoutError:
        return None
    except Exception:
        return None


def get_akshare():
    global ak
    if ak is not None:
        return ak

    def load_module():
        import akshare as ak_module

        return ak_module

    ak = run_with_timeout(load_module, seconds=8)
    return ak


def normalize_stock_frame(df):
    df = df.rename(
        columns={
            "日期": "date",
            "收盘": "close",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "涨跌幅": "pct",
        }
    )
    keep = ["date", "open", "close", "high", "low", "volume", "amount", "pct"]
    df = df[[col for col in keep if col in df.columns]].copy()
    for col in ["open", "close", "high", "low", "volume", "amount", "pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"]).tail(120)
    if df.empty:
        return None
    df["source"] = "AkShare"
    df["valid"] = True
    return df


def demo_stock_daily(code: str):
    seed = abs(hash(code)) % (2**32)
    rng = np.random.default_rng(seed)
    base = 8 + seed % 4500 / 100
    drift = rng.normal(0.015, 0.22, 120).cumsum()
    close = np.maximum(base + drift, 1)
    open_price = close * (1 + rng.normal(0, 0.008, 120))
    high = np.maximum(open_price, close) * (1 + rng.uniform(0.002, 0.025, 120))
    low = np.minimum(open_price, close) * (1 - rng.uniform(0.002, 0.025, 120))
    pct = np.insert(np.diff(close) / close[:-1] * 100, 0, 0)
    volume = rng.integers(100000, 1800000, 120)
    amount = volume * close * 100
    dates = pd.date_range(end=datetime.now(), periods=120, freq="B").strftime("%Y-%m-%d")

    return pd.DataFrame(
        {
            "date": dates,
            "open": open_price,
            "close": close,
            "high": high,
            "low": low,
            "volume": volume,
            "amount": amount,
            "pct": pct,
            "source": "fallback-demo",
            "valid": False,
        }
    )


def get_stock_daily(code: str):
    ak_module = get_akshare()
    if ak_module is not None:
        df = run_with_timeout(
            lambda: ak_module.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq"),
            seconds=10,
        )
        if df is not None:
            normalized = normalize_stock_frame(df)
            if normalized is not None:
                return normalized

    return demo_stock_daily(code)


def demo_market_index():
    rng = np.random.default_rng(20260520)
    close = 3050 + rng.normal(0.8, 18, 60).cumsum()
    dates = pd.date_range(end=datetime.now(), periods=60, freq="B").strftime("%Y-%m-%d")
    return pd.DataFrame(
        {
            "date": dates,
            "close": close,
            "source": "fallback-demo",
            "valid": False,
        }
    )


def get_market_index():
    ak_module = get_akshare()
    if ak_module is not None:
        df = run_with_timeout(lambda: ak_module.stock_zh_index_daily(symbol="sh000001"), seconds=8)
        if df is not None and "close" in df.columns:
            df = df.copy()
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df = df.dropna(subset=["close"]).tail(60)
            if not df.empty:
                df["source"] = "AkShare"
                df["valid"] = True
                return df

    return demo_market_index()
