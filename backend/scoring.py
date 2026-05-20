import pandas as pd

from indicators import clamp, enrich_kline, technical_snapshot, volume_price_state


def market_environment(indexes):
    valid_indexes = [i for i in indexes if i.get("valid") and i.get("pct") is not None]
    if len(valid_indexes) < 4:
        return {
            "score": 0,
            "state": "行情不可用",
            "summary": "核心指数实时数据不足，暂停使用大盘环境参与建议计算。",
            "valid": False,
        }
    avg_pct = sum(i["pct"] for i in valid_indexes) / len(valid_indexes)
    strong_count = sum(1 for i in valid_indexes if i["pct"] > 0.5)
    weak_count = sum(1 for i in valid_indexes if i["pct"] < -0.8)
    amount = sum(i.get("amount", 0) or 0 for i in valid_indexes)
    score = 50 + avg_pct * 12 + strong_count * 4 - weak_count * 7
    if amount > 3_000_000_000_000:
        score += 8
    score = round(clamp(score), 1)
    if score >= 72:
        state = "强势"
    elif score >= 52:
        state = "震荡"
    elif score >= 38:
        state = "弱势"
    else:
        state = "风险释放"
    return {
        "score": score,
        "state": state,
        "summary": f"核心指数平均涨跌幅 {avg_pct:.2f}%，上涨指数 {strong_count} 个，下跌压力指数 {weak_count} 个。",
        "valid": True,
    }


def sector_rotation(sectors):
    all_rows = sectors.get("industry", []) + sectors.get("concept", [])
    if not all_rows:
        return {"score": 50, "main": [], "catch_up": [], "fading": [], "summary": "板块数据不足。"}
    sorted_rows = sorted(all_rows, key=lambda x: x.get("pct", 0), reverse=True)
    main = sorted_rows[:5]
    fading = sorted_rows[-5:]
    catch_up = [r for r in sorted_rows if 0.8 <= r.get("pct", 0) <= 2.2][:5]
    avg_top = sum(r["pct"] for r in main) / len(main)
    score = round(clamp(50 + avg_top * 8), 1)
    return {
        "score": score,
        "main": main,
        "catch_up": catch_up,
        "fading": fading,
        "summary": "主线：" + "、".join(r["name"] for r in main[:3]),
    }


def score_stock(stock, kline, env, sector, fund, news):
    df = pd.DataFrame(kline)
    tech = technical_snapshot(df)
    vp = volume_price_state(df)
    market_valid = env.get("valid", True)
    market_score = env["score"] if market_valid else 0
    sector_score = sector["score"]
    tech_score = clamp(tech["trend_score"] * 0.6 + tech["momentum_score"] * 0.4 - max(0, tech["risk_score"] - 65) * 0.35)
    fund_score = fund["score"]
    volume_price_score = vp["score"]
    news_score = news["score"]
    total = (
        market_score * 0.15
        + sector_score * 0.20
        + tech_score * 0.20
        + fund_score * 0.20
        + volume_price_score * 0.15
        + news_score * 0.10
    )
    if not market_valid:
        total = min(total, 44)
    elif env["state"] in ["弱势", "风险释放"]:
        total -= 8 if env["state"] == "弱势" else 14
    total = round(clamp(total), 1)
    advice, position = advice_by_score(total, tech["risk_score"], market_valid)
    trade_plan = build_trade_plan(stock, total, tech, vp)
    reasons = build_reasons(stock, env, sector, fund, vp, tech, news)
    risks = build_risks(env, fund, vp, tech, news)
    return {
        "score": total,
        "state": vp["state"],
        "advice": advice,
        "position": position,
        "trade_plan": trade_plan,
        "bullish_reasons": reasons,
        "risks": risks,
        "support": tech["support"],
        "pressure": tech["pressure"],
        "stop_loss": tech["stop_loss"],
        "one_liner": f"{stock['name']} 当前综合评分 {total}，{advice}，建议仓位 {position}。",
        "data_quality": "实时指数有效" if market_valid else "核心指数不可用，建议已降级",
        "sub_scores": {
            "market": market_score,
            "sector": sector_score,
            "technical": round(tech_score, 1),
            "fund": fund_score,
            "volume_price": volume_price_score,
            "news": news_score,
        },
        "technical": tech,
        "volume_price": vp,
    }


def advice_by_score(score, risk, market_valid=True):
    if not market_valid:
        return "数据不足", "0%"
    if score >= 82 and risk < 70:
        return "重点关注", "70%"
    if score >= 70:
        return "持有", "50%"
    if score >= 58:
        return "谨慎持有", "30%"
    if score >= 45:
        return "减仓观察", "10%"
    return "回避", "0%"


def build_trade_plan(stock, score, tech, vp):
    price = float(stock.get("price") or 0)
    support = float(tech.get("support") or 0)
    pressure = float(tech.get("pressure") or 0)
    stop_loss = float(tech.get("stop_loss") or 0)
    if not price or not tech.get("valid", True) or not support or not pressure:
        return {
            "buy_point": "真实历史K线不足，暂不输出买点。",
            "sell_point": "真实历史K线不足，暂不输出卖点。",
            "add_point": "等待有效K线数据。",
            "reduce_point": "等待有效K线数据。",
            "support": support or None,
            "pressure": pressure or None,
            "stop_loss": stop_loss or None,
        }

    low_buy = support * 1.005 if support else price * 0.985
    high_buy = min(price * 1.01, support * 1.025) if support else price * 1.01
    breakout = pressure * 1.01 if pressure else price * 1.035
    take_profit = pressure * 0.985 if pressure else price * 1.08
    weak_reduce = max(stop_loss * 1.015, support * 0.99) if stop_loss and support else price * 0.965

    if support and price < support * 0.98:
        buy_point = f"破位观察：现价低于支撑 {support:.2f}，先等重新站回支撑位并缩量企稳。"
        add_point = f"加仓点：收盘重新站上 {support:.2f}，再看是否放量突破 {breakout:.2f}。"
    elif score >= 70 and "突破" in vp.get("state", ""):
        buy_point = f"突破买点：放量站上 {breakout:.2f} 后回踩不破，可小仓跟随。"
        add_point = f"加仓点：回踩 {pressure:.2f} 附近企稳，且量能不明显萎缩。"
    elif score >= 58:
        buy_point = f"低吸买点：靠近 {low_buy:.2f}-{high_buy:.2f} 区间止跌，再考虑分批。"
        add_point = f"加仓点：站回短期均线并放量突破 {breakout:.2f}。"
    elif score >= 45:
        buy_point = f"观察买点：只看 {support:.2f} 附近是否出现缩量止跌，不追高。"
        add_point = "加仓点：评分未达强势区，暂不主动加仓。"
    else:
        buy_point = "买点建议：综合评分偏弱，等待重新站上支撑并放量转强。"
        add_point = "加仓点：无。"

    sell_point = f"卖点/止盈：接近 {take_profit:.2f} 若放量滞涨或冲高回落，优先减仓。"
    reduce_point = f"风控卖点：跌破 {weak_reduce:.2f} 或收盘跌破止损位 {stop_loss:.2f}，执行减仓/离场。"
    return {
        "buy_point": buy_point,
        "sell_point": sell_point,
        "add_point": add_point,
        "reduce_point": reduce_point,
        "support": round(support, 2),
        "pressure": round(pressure, 2),
        "stop_loss": round(stop_loss, 2),
    }


def build_reasons(stock, env, sector, fund, vp, tech, news):
    reasons = [
        f"大盘环境为{env['state']}，环境分 {env['score']}。",
        f"板块热度 {sector['score']}，{sector['summary']}。",
        f"资金阶段：{fund['phase']}，主力净流入 {fund['main_net_inflow'] / 100000000:.2f} 亿。",
        f"量价状态：{vp['state']}，{vp['explain']}",
    ]
    if not env.get("valid", True):
        reasons[0] = "核心指数实时数据不可用，本次不输出强操作建议。"
    if tech["trend_score"] >= 70:
        reasons.append("均线趋势较强，短中期结构占优。")
    if news["score"] >= 60:
        reasons.append("消息关键词偏正面，但仍需核对公告原文。")
    return reasons[:6]


def build_risks(env, fund, vp, tech, news):
    risks = []
    if env["state"] in ["弱势", "风险释放"]:
        risks.append("大盘偏弱，个股建议等级已自动下调。")
    if not env.get("valid", True):
        risks.append("核心指数未取得真实实时数据，最终建议已降级为数据不足。")
    if "滞涨" in vp["state"] or "下跌" in vp["state"]:
        risks.append(vp["explain"])
    if fund["phase"] in ["出货/撤退", "分歧"]:
        risks.append(f"资金面处于{fund['phase']}，追高胜率下降。")
    if tech["risk_score"] >= 70:
        risks.append("技术风险分偏高，注意高位回落和布林带外侧回归。")
    bad_news = [item["keyword"] for item in news["items"] if item["direction"] == "利空"]
    if bad_news:
        risks.append("消息面存在风险关键词：" + "、".join(bad_news))
    return risks or ["暂无显著硬风险，但需控制仓位并按止损执行。"]
