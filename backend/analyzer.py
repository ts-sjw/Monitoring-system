import numpy as np

from data_fetcher import get_market_index, get_stock_daily


def safe_float(value, default=0):
    try:
        if np.isnan(value):
            return default
        return float(value)
    except Exception:
        return default


def calc_indicators(df):
    close = df["close"]
    volume = df["volume"]

    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd = (dif - dea) * 2

    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    rsi = 100 - 100 / (1 + up.rolling(14).mean() / down.rolling(14).mean())

    return {
        "ma5": safe_float(ma5.iloc[-1]),
        "ma10": safe_float(ma10.iloc[-1]),
        "ma20": safe_float(ma20.iloc[-1]),
        "ma60": safe_float(ma60.iloc[-1]),
        "macd": safe_float(macd.iloc[-1]),
        "rsi": safe_float(rsi.iloc[-1], 50),
        "vol_ma5": safe_float(volume.rolling(5).mean().iloc[-1]),
    }


def volume_price_analysis(df):
    close = df["close"].tolist()
    volume = df["volume"].tolist()

    latest_vol = volume[-1]
    avg_vol = np.mean(volume[-5:])
    price_change = (close[-1] - close[-2]) / close[-2] if close[-2] else 0

    if latest_vol > 1.5 * avg_vol:
        if price_change > 0.02:
            return "放量上涨，趋势增强", 15
        if price_change > 0:
            return "放量滞涨，注意出货风险", -15
        return "放量下跌，风险释放", -15

    if latest_vol < 0.7 * avg_vol:
        if price_change > 0:
            return "缩量上涨，抛压较轻", 8
        if price_change < 0:
            return "缩量下跌，承接偏弱", -8
        return "缩量横盘，等待方向", 0

    return "量价正常", 0


def tech_score(df):
    close = df["close"].iloc[-1]
    ind = calc_indicators(df)
    score = 50
    notes = []

    if close > ind["ma5"] > ind["ma10"] > ind["ma20"]:
        score += 20
        notes.append("均线多头排列")
    elif close < ind["ma5"] < ind["ma10"] < ind["ma20"]:
        score -= 20
        notes.append("均线空头排列")
    else:
        notes.append("均线震荡")

    if ind["macd"] > 0:
        score += 10
        notes.append("MACD偏强")
    else:
        score -= 10
        notes.append("MACD偏弱")

    if ind["rsi"] > 75:
        score -= 8
        notes.append("RSI偏高，注意追高")
    elif ind["rsi"] < 30:
        score += 5
        notes.append("RSI偏低，可能超跌")

    return max(0, min(100, score)), notes, ind


def analyze_market():
    df = get_market_index()
    if df is None or df.empty:
        return {
            "status": "未知",
            "score": 50,
            "summary": "大盘数据获取失败，按中性处理",
        }

    close = df["close"]
    ma5 = close.rolling(5).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    latest = close.iloc[-1]

    if latest > ma5 > ma20:
        return {"status": "强势", "score": 80, "summary": "大盘趋势偏强，可适度积极"}
    if latest < ma5 < ma20:
        return {"status": "弱势", "score": 35, "summary": "大盘偏弱，控制仓位"}
    return {"status": "震荡", "score": 55, "summary": "大盘震荡，精选个股"}


def chart_rows(df):
    rows = []
    for _, row in df.tail(120).iterrows():
        rows.append(
            {
                "date": str(row["date"]),
                "open": round(float(row["open"]), 2),
                "close": round(float(row["close"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "volume": round(float(row["volume"]), 2),
            }
        )
    return rows


def analyze_stock(code: str):
    df = get_stock_daily(code)
    latest = df.iloc[-1]

    base_score, notes, ind = tech_score(df)
    vp_text, vp_score = volume_price_analysis(df)
    market = analyze_market()

    final_score = base_score * 0.45 + market["score"] * 0.25 + (50 + vp_score) * 0.30
    final_score = max(0, min(100, round(final_score, 1)))

    support = round(float(df["low"].tail(20).min()), 2)
    pressure = round(float(df["high"].tail(20).max()), 2)
    stop_loss = round(support * 0.97, 2)

    if final_score >= 80:
        advice = "强势关注"
        position = "30%-50%"
    elif final_score >= 65:
        advice = "持有 / 回踩关注"
        position = "20%-40%"
    elif final_score >= 50:
        advice = "震荡观察"
        position = "10%-20%"
    elif final_score >= 35:
        advice = "谨慎持有 / 降低仓位"
        position = "0%-10%"
    else:
        advice = "回避 / 减仓观察"
        position = "0%"

    return {
        "code": code,
        "price": round(float(latest["close"]), 2),
        "pct": round(float(latest.get("pct", 0)), 2),
        "score": final_score,
        "current_status": "强势" if final_score >= 65 else "震荡" if final_score >= 50 else "偏弱",
        "market_status": market["status"],
        "volume_price": vp_text,
        "tech_notes": notes,
        "indicators": ind,
        "advice": advice,
        "position": position,
        "support": support,
        "pressure": pressure,
        "stop_loss": stop_loss,
        "risk": "仅供学习和辅助分析，不构成投资建议，不自动交易。",
        "data_source": str(latest.get("source", "unknown")),
        "chart": chart_rows(df),
        "summary": f"大盘{market['status']}，个股{vp_text}，技术面：{'、'.join(notes)}。当前建议：{advice}。",
    }
