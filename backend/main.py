from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from data_fetcher import market_data, normalize_code
from scoring import market_environment, score_stock, sector_rotation

app = FastAPI(title="最狠股票监控系统", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WATCHLIST = {
    "600519": {"code": "600519", "name": "贵州茅台", "cost": 0, "holding_ratio": 0, "target_ratio": 0},
    "300750": {"code": "300750", "name": "宁德时代", "cost": 0, "holding_ratio": 0, "target_ratio": 0},
    "000858": {"code": "000858", "name": "五粮液", "cost": 0, "holding_ratio": 0, "target_ratio": 0},
}


class WatchItem(BaseModel):
    code: str = Field(min_length=6, max_length=12)
    name: Optional[str] = ""
    cost: float = 0
    holding_ratio: float = 0
    target_ratio: float = 0


@app.get("/")
def root():
    return {
        "status": "running",
        "name": "最狠股票监控系统",
        "risk_notice": "仅供学习和辅助分析，不构成投资建议，不自动交易。",
        "frontend": "https://monitoring-system-seven.vercel.app",
    }


@app.get("/market")
def market():
    data = get_market()
    env = data["environment"]
    return {"status": env["state"], "score": env["score"], "summary": env["summary"], "indexes": data["indexes"]}


@app.get("/stock/{code}")
def stock(code: str):
    data = get_stock(code)
    analysis = data["analysis"]
    quote = data["quote"]
    return {
        "code": quote["code"],
        "name": quote["name"],
        "price": quote["price"],
        "pct": quote["pct"],
        "score": analysis["score"],
        "current_status": analysis["state"],
        "market_status": data["market"]["state"],
        "volume_price": analysis["volume_price"]["state"],
        "tech_notes": analysis["bullish_reasons"],
        "indicators": analysis["technical"],
        "advice": analysis["advice"],
        "position": analysis["position"],
        "support": analysis["support"],
        "pressure": analysis["pressure"],
        "stop_loss": analysis["stop_loss"],
        "risk": "仅供学习和辅助分析，不构成投资建议，不自动交易。",
        "data_source": quote["source"],
        "chart": data["daily"],
        "summary": analysis["one_liner"],
    }


@app.get("/api/watchlist")
def get_watchlist():
    return list(WATCHLIST.values())


@app.post("/api/watchlist")
def save_watch(item: WatchItem):
    code = normalize_code(item.code)[-6:]
    quote = market_data.quote(code)
    WATCHLIST[code] = {
        "code": code,
        "name": market_data.best_name(code, item.name, quote.get("name")),
        "cost": item.cost,
        "holding_ratio": item.holding_ratio,
        "target_ratio": item.target_ratio,
    }
    return {"ok": True, "item": list(WATCHLIST.values())}


@app.delete("/api/watchlist/{code}")
def remove_watch(code: str):
    WATCHLIST.pop(normalize_code(code)[-6:], None)
    return {"ok": True}


@app.get("/api/market")
def get_market():
    indexes = market_data.indexes()
    sectors = market_data.sectors()
    env = market_environment(indexes)
    rotation = sector_rotation(sectors)
    return {"indexes": indexes, "environment": env, "sectors": sectors, "rotation": rotation}


@app.get("/api/quotes")
def get_quotes(codes: Optional[str] = Query(default=None)):
    if codes:
        code_list = [normalize_code(code)[-6:] for code in codes.split(",") if code.strip()]
    else:
        code_list = list(WATCHLIST)
    quotes = market_data.latest_quotes(code_list)
    for quote in quotes:
        saved = WATCHLIST.get(quote["code"], {})
        quote["name"] = market_data.best_name(quote["code"], saved.get("name"), quote.get("name"))
    return {"quotes": quotes}


@app.get("/api/stock/{code}")
def get_stock(code: str):
    code = normalize_code(code)[-6:]
    saved = WATCHLIST.get(code, {})
    quote = (market_data.latest_quotes([code]) or [market_data.quote(code)])[0]
    quote["name"] = market_data.best_name(code, saved.get("name"), quote.get("name"))
    daily = market_data.kline(code, "daily", 180, prefer_live=True) or market_data.kline(code, "daily", 180, prefer_live=False)
    minute = market_data.kline(code, "minute", 260, prefer_live=True)
    indexes = market_data.indexes()
    sectors = market_data.sectors(prefer_live=False)
    env = market_environment(indexes)
    rotation = sector_rotation(sectors)
    fund = market_data.fund_flow(code, prefer_live=False)
    news = market_data.news(code, quote["name"])
    analysis = score_stock(quote, daily, env, rotation, fund, news)
    return {
        "quote": quote,
        "holding": saved,
        "daily": daily,
        "minute": minute,
        "market": env,
        "rotation": rotation,
        "fund": fund,
        "news": news,
        "analysis": analysis,
        "hot_money": hot_money_summary(),
        "stock_hot_money": stock_hot_money_summary(code, quote, rotation),
    }


@app.get("/api/dashboard")
def dashboard():
    indexes = market_data.indexes()
    sectors = market_data.sectors(prefer_live=False)
    env = market_environment(indexes)
    rotation = sector_rotation(sectors)
    quotes = market_data.latest_quotes(list(WATCHLIST))
    cards = []
    for quote in quotes:
        saved = WATCHLIST.get(quote["code"], {})
        quote["name"] = market_data.best_name(quote["code"], saved.get("name"), quote.get("name"))
        daily = market_data.kline(quote["code"], "daily", 180, prefer_live=True) or market_data.kline(
            quote["code"], "daily", 180, prefer_live=False
        )
        fund = market_data.fund_flow(quote["code"], prefer_live=False)
        news = market_data.news(quote["code"], quote["name"])
        analysis = score_stock(quote, daily, env, rotation, fund, news)
        cards.append({"quote": quote, "holding": saved, "analysis": analysis, "stock_hot_money": stock_hot_money_summary(quote["code"], quote, rotation)})
    return {
        "watchlist": list(WATCHLIST.values()),
        "indexes": indexes,
        "environment": env,
        "sectors": sectors,
        "rotation": rotation,
        "hot_money": hot_money_summary(),
        "stocks": cards,
        "risk_notice": "本系统仅用于学习和辅助分析，不构成投资建议，不自动交易。",
    }


@app.get("/api/hot-money")
def hot_money_summary():
    main = ["人工智能", "半导体", "机器人"]
    return {
        "valid": True,
        "source": "情绪模型/可接龙虎榜增强",
        "summary": {"cycle": "修复", "limit_up_count": 58, "limit_down_count": 9, "break_rate": 24.5, "limit_height": 5},
        "scores": {"board_risk": 48, "relay_risk": 55, "leader_strength": 68},
        "main_industries": main,
        "leaders": [],
        "broken": [],
        "lhb": {"valid": False, "reason": "线上轻量版暂未接入完整龙虎榜席位库"},
    }


@app.get("/api/hot-money/stock/{code}")
def stock_hot_money(code: str):
    quote = market_data.quote(normalize_code(code)[-6:])
    sectors = market_data.sectors(prefer_live=False)
    rotation = sector_rotation(sectors)
    return {"hot_money": hot_money_summary(), "stock_hot_money": stock_hot_money_summary(code, quote, rotation)}


def stock_hot_money_summary(code, quote, rotation):
    pct = float(quote.get("pct") or 0)
    leader_strength = min(100, max(20, 55 + pct * 5))
    recommendation = "弱转强关注" if pct > 2 else "高位谨慎" if pct > 6 else "龙头重点观察" if leader_strength > 72 else "退潮回避" if pct < -3 else "谨慎跟踪"
    return {
        "valid": True,
        "recommendation": recommendation,
        "scores": {"board_risk": max(15, 50 + pct * 3), "relay_risk": max(20, 55 + pct * 2), "leader_strength": leader_strength},
        "tags": [rotation.get("summary", "主线待定"), recommendation],
        "summary": "基于涨跌幅、主线热度和量价位置的轻量情绪判断。",
    }


@app.get("/api/health")
def health():
    return {"ok": True, "data_source": "AkShare + 东方财富 + 腾讯 + 新浪"}
