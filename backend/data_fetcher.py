import numpy as np
import pandas as pd

ak = None


def get_akshare():
    global ak
    if ak is not None:
        return ak
    try:
        import akshare as ak_module

        ak = ak_module
        return ak
    except Exception:
        return None


def get_stock_daily(code: str):
    ak_module = get_akshare()
    if ak_module is not None:
        try:
            df = ak_module.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
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
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["source"] = "AkShare"
            df["valid"] = True
            return df.tail(120).dropna(subset=["close"])
        except Exception:
            pass

    close = np.cumsum(np.random.randn(120)) + 10
    return pd.DataFrame(
        {
            "date": list(range(120)),
            "close": close,
            "open": close,
            "high": close * 1.02,
            "low": close * 0.98,
            "volume": np.random.randint(100000, 1000000, 120),
            "amount": np.random.randint(10000000, 50000000, 120),
            "pct": np.random.randn(120),
            "source": "fallback-demo",
            "valid": False,
        }
    )


def get_market_index():
    ak_module = get_akshare()
    if ak_module is not None:
        try:
            df = ak_module.stock_zh_index_daily(symbol="sh000001")
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            return df.tail(60).dropna(subset=["close"])
        except Exception:
            return None
    return None
