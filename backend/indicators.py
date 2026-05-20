import math
import numpy as np
import pandas as pd


def clamp(value, lower=0, upper=100):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return lower
    return max(lower, min(upper, float(value)))


def enrich_kline(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for col in ["open", "close", "high", "low", "volume", "amount"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
    for n in [5, 10, 20, 60]:
        out[f"ma{n}"] = out["close"].rolling(n, min_periods=1).mean()
    exp12 = out["close"].ewm(span=12, adjust=False).mean()
    exp26 = out["close"].ewm(span=26, adjust=False).mean()
    out["dif"] = exp12 - exp26
    out["dea"] = out["dif"].ewm(span=9, adjust=False).mean()
    out["macd"] = (out["dif"] - out["dea"]) * 2
    delta = out["close"].diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi"] = (100 - 100 / (1 + rs)).fillna(50)
    low_n = out["low"].rolling(9, min_periods=1).min()
    high_n = out["high"].rolling(9, min_periods=1).max()
    rsv = (out["close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    out["k"] = rsv.fillna(50).ewm(com=2, adjust=False).mean()
    out["d"] = out["k"].ewm(com=2, adjust=False).mean()
    out["j"] = 3 * out["k"] - 2 * out["d"]
    mid = out["close"].rolling(20, min_periods=1).mean()
    std = out["close"].rolling(20, min_periods=1).std().fillna(0)
    out["boll_mid"] = mid
    out["boll_upper"] = mid + 2 * std
    out["boll_lower"] = mid - 2 * std
    out["vol_ma5"] = out["volume"].rolling(5, min_periods=1).mean()
    out["vol_ma20"] = out["volume"].rolling(20, min_periods=1).mean()
    return out.replace([np.inf, -np.inf], np.nan).fillna(0)


def technical_snapshot(df: pd.DataFrame):
    if df.empty or ("valid" in df.columns and not df["valid"].fillna(False).astype(bool).any()):
        return {
            "trend_score": 50,
            "momentum_score": 50,
            "risk_score": 50,
            "support": None,
            "pressure": None,
            "stop_loss": None,
            "valid": False,
            "data_source": "不可用",
            "level_note": "真实历史K线不可用，暂停输出支撑/压力位。",
            "indicators": [],
        }
    data = enrich_kline(df)
    last = data.iloc[-1]
    close = float(last["close"])
    trend = 40
    if close > last["ma5"] > last["ma10"] > last["ma20"]:
        trend += 35
    elif close > last["ma20"]:
        trend += 20
    elif close < last["ma20"]:
        trend -= 10
    momentum = 50 + clamp(last["macd"] * 20, -20, 20) + (last["rsi"] - 50) * 0.35
    support, pressure, level_note = price_levels(data, close)
    stop_loss = support * 0.97 if support else close * 0.93
    risk = 35
    if last["rsi"] > 78:
        risk += 25
    if close > last["boll_upper"]:
        risk += 15
    if last["volume"] > last["vol_ma20"] * 2 and last["close"] <= last["open"]:
        risk += 20
    return {
        "trend_score": round(clamp(trend), 1),
        "momentum_score": round(clamp(momentum), 1),
        "risk_score": round(clamp(risk), 1),
        "support": round(support, 2),
        "pressure": round(pressure, 2),
        "stop_loss": round(stop_loss, 2),
        "valid": True,
        "data_source": str(last.get("source", "真实K线")),
        "level_note": level_note,
        "indicators": data.tail(120).to_dict("records"),
    }


def price_levels(data: pd.DataFrame, close: float):
    recent = data.tail(60).copy()
    support_candidates = []
    pressure_candidates = []

    for col in ["ma5", "ma10", "ma20", "ma60", "boll_mid", "boll_lower", "boll_upper"]:
        value = float(recent.iloc[-1].get(col, 0) or 0)
        if value <= 0:
            continue
        if value < close:
            support_candidates.append(value)
        elif value > close:
            pressure_candidates.append(value)

    lows = recent["low"].astype(float).tolist()
    highs = recent["high"].astype(float).tolist()
    for idx in range(1, max(1, len(recent) - 1)):
        low = lows[idx]
        high = highs[idx]
        if low <= lows[idx - 1] and low <= lows[min(idx + 1, len(lows) - 1)] and low < close:
            support_candidates.append(low)
        if high >= highs[idx - 1] and high >= highs[min(idx + 1, len(highs) - 1)] and high > close:
            pressure_candidates.append(high)

    support_candidates.extend([v for v in lows if close * 0.9 <= v < close])
    pressure_candidates.extend([v for v in highs if close < v <= close * 1.18])

    support = max(support_candidates) if support_candidates else float(recent["low"].tail(20).min())
    pressure = min(pressure_candidates) if pressure_candidates else float(recent["high"].tail(20).max())
    if pressure <= close:
        pressure = float(recent["high"].tail(60).max())
    if support >= close:
        support = float(recent["low"].tail(60).min())

    note = "支撑/压力基于真实前复权日K、均线、近期高低点综合计算。"
    return support, pressure, note


def volume_price_state(df: pd.DataFrame):
    if len(df) < 2:
        return {"state": "数据不足", "score": 50, "explain": "等待更多行情数据确认。"}
    data = enrich_kline(df)
    last = data.iloc[-1]
    prev = data.iloc[-2]
    price_chg = (last["close"] - prev["close"]) / prev["close"] * 100 if prev["close"] else 0
    vol_ratio = last["volume"] / last["vol_ma20"] if last["vol_ma20"] else 1
    high_break = last["close"] >= data.tail(20)["high"].max() * 0.995
    if vol_ratio >= 1.8 and price_chg >= 2.5 and high_break:
        state, score, explain = "放量突破", 88, "价格带量越过近期压力，趋势资金合力较强，值得重点跟踪。"
    elif vol_ratio >= 1.5 and price_chg > 1:
        state, score, explain = "放量上涨", 78, "量能放大且价格上行，趋势增强。"
    elif vol_ratio >= 1.8 and abs(price_chg) < 0.8:
        state, score, explain = "放量滞涨", 42, "资金分歧明显，可能存在兑现或上方抛压。"
    elif vol_ratio >= 1.5 and price_chg <= -1:
        state, score, explain = "放量下跌", 35, "恐慌或主力撤退迹象增强，先看风险释放是否充分。"
    elif vol_ratio < 0.8 and price_chg > 0:
        state, score, explain = "缩量上涨", 68, "抛压不重，趋势相对健康，但爆发力不足。"
    elif vol_ratio < 0.8 and price_chg < 0:
        state, score, explain = "缩量下跌", 45, "承接偏弱，短线仍需等待资金回流。"
    else:
        state, score, explain = "缩量横盘", 55, "多空暂时均衡，等待放量选择方向。"
    return {
        "state": state,
        "score": score,
        "volume_change": round((vol_ratio - 1) * 100, 1),
        "price_change": round(price_chg, 2),
        "explain": explain,
    }
