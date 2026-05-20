import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests


INDEX_MAP = {
    "sh000001": "上证指数",
    "sz399001": "深成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
    "sh000300": "沪深300",
    "sh000905": "中证500",
}

EXECUTOR = ThreadPoolExecutor(max_workers=6)
NAME_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "stock_names.csv"


def normalize_code(code: str) -> str:
    return code.strip().lower().replace(".", "")


def eastmoney_sec_id(code: str) -> str:
    code = normalize_code(code)
    if code.startswith(("6", "9")) or code.startswith("sh"):
        return f"1.{code[-6:]}"
    return f"0.{code[-6:]}"


class MarketData:
    def __init__(self):
        self.ak = None
        self._ak_loaded = False
        self._spot_cache = {"ts": 0, "df": None}
        self._sector_cache = {"ts": 0, "data": None}
        self._name_cache = {"ts": 0, "map": {}}
        self._kline_cache = {}

    def _run(self, func, timeout=7):
        future = EXECUTOR.submit(func)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            return None
        except Exception:
            return None

    def _akshare(self):
        if self._ak_loaded:
            return self.ak

        def load():
            import akshare as ak

            return ak

        self.ak = self._run(load, timeout=5)
        self._ak_loaded = True
        return self.ak

    def _spot(self):
        now = time.time()
        if self._spot_cache["df"] is not None and now - self._spot_cache["ts"] < 20:
            return self._spot_cache["df"]
        ak = self._akshare()
        if not ak:
            return None
        df = self._run(lambda: ak.stock_zh_a_spot_em(), timeout=2)
        if df is not None and not df.empty:
            self._spot_cache = {"ts": now, "df": df}
            return df
        return None

    def quote(self, code: str):
        code = normalize_code(code)[-6:]
        df = self._spot()
        if df is not None:
            row = df[df["代码"].astype(str) == code]
            if not row.empty:
                return self._quote_from_row(row.iloc[0], code)
        east = self._eastmoney_quote(code)
        if east:
            return east
        return self._fallback_quote(code)

    def stock_name(self, code: str):
        code = normalize_code(code)[-6:]
        now = time.time()
        if self._name_cache["map"] and now - self._name_cache["ts"] < 24 * 60 * 60:
            return self._name_cache["map"].get(code)
        disk_map = self._load_name_cache_file()
        if disk_map:
            self._name_cache = {"ts": now, "map": disk_map}
            return disk_map.get(code)
        ak = self._akshare()
        if not ak:
            return None
        df = self._run(lambda: ak.stock_info_a_code_name(), timeout=3)
        if df is None or df.empty:
            return None
        name_map = self._name_map_from_df(df)
        self._save_name_cache_file(df)
        self._name_cache = {"ts": now, "map": name_map}
        return name_map.get(code)

    def _load_name_cache_file(self):
        if not NAME_CACHE_FILE.exists():
            return {}
        try:
            df = pd.read_csv(NAME_CACHE_FILE, dtype={"code": str})
            return self._name_map_from_df(df)
        except Exception:
            return {}

    def _save_name_cache_file(self, df):
        try:
            NAME_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            df[["code", "name"]].to_csv(NAME_CACHE_FILE, index=False, encoding="utf-8-sig")
        except Exception:
            pass

    def _name_map_from_df(self, df):
        return {
            str(row["code"]).zfill(6): str(row["name"]).strip()
            for _, row in df.iterrows()
            if str(row.get("code", "")).strip()
        }

    def is_placeholder_name(self, code: str, name: str | None):
        if not name:
            return True
        text = str(name).strip()
        tail = normalize_code(code)[-3:]
        return (
            text == normalize_code(code)[-6:]
            or text.endswith(tail) and len(text) <= 8
            or bool(re.fullmatch(r"股票\d{3,6}", text))
            or text.lower() in {"nan", "none", "null"}
        )

    def best_name(self, code: str, *names):
        for name in names:
            if not self.is_placeholder_name(code, name):
                return str(name).strip()
        looked_up = self.stock_name(code)
        if looked_up and not self.is_placeholder_name(code, looked_up):
            return looked_up
        return f"股票{normalize_code(code)[-3:]}"

    def batch_quotes(self, codes):
        df = self._spot()
        out = []
        for code in codes:
            pure = normalize_code(code)[-6:]
            row = df[df["代码"].astype(str) == pure] if df is not None else pd.DataFrame()
            if not row.empty:
                out.append(self._quote_from_row(row.iloc[0], pure))
            else:
                out.append(self._eastmoney_quote(pure) or self._fallback_quote(pure))
        return out

    def latest_quotes(self, codes):
        quotes = self._sina_quotes(codes)
        if quotes:
            return quotes
        rows = []
        for code in codes:
            pure = normalize_code(code)[-6:]
            rows.append(self._eastmoney_quote(pure) or self._fallback_quote(pure))
        return rows

    def _sina_quotes(self, codes):
        symbols = []
        for code in codes:
            pure = normalize_code(code)[-6:]
            prefix = "sh" if pure.startswith(("6", "9")) else "sz"
            symbols.append(prefix + pure)
        if not symbols:
            return []
        try:
            url = "https://hq.sinajs.cn/list=" + ",".join(symbols)
            resp = requests.get(url, timeout=1.2, headers={"Referer": "https://finance.sina.com.cn/"})
            resp.encoding = "gbk"
            rows = []
            for line in resp.text.splitlines():
                if '="' not in line:
                    continue
                symbol = line.split("=", 1)[0][-8:]
                code = symbol[-6:]
                payload = line.split('"', 2)[1]
                parts = payload.split(",")
                if len(parts) < 32 or not parts[0]:
                    continue
                prev_close = float(parts[2] or 0)
                price = float(parts[3] or 0)
                pct = (price - prev_close) / prev_close * 100 if prev_close else 0
                rows.append(
                    {
                        "code": code,
                        "name": self.best_name(code, parts[0]),
                        "price": round(price, 2),
                        "pct": round(pct, 2),
                        "amount": float(parts[9] or 0),
                        "turnover": 0,
                        "volume_ratio": 0,
                        "source": "新浪",
                    }
                )
            return rows
        except Exception:
            return []

    def kline(self, code: str, period="daily", limit=180, prefer_live=True):
        pure = normalize_code(code)[-6:]
        if period == "minute" and prefer_live:
            rows = self._tencent_minute_line(pure)
            if rows:
                return rows[-limit:]
        if period == "daily" and prefer_live:
            rows = self._tencent_daily_kline(pure, limit)
            if rows:
                return rows
        ak = self._akshare() if prefer_live else None
        if ak and prefer_live:
            if period == "minute":
                df = self._run(lambda: ak.stock_zh_a_hist_min_em(symbol=pure, period="5", adjust=""), timeout=2)
            else:
                df = self._run(lambda: ak.stock_zh_a_hist(symbol=pure, period="daily", adjust="qfq"), timeout=2)
            if df is not None and not df.empty:
                return self._clean_kline(df.tail(limit))
        return [] if prefer_live else self._fallback_kline(pure, limit)

    def _market_symbol(self, code):
        pure = normalize_code(code)[-6:]
        prefix = "sh" if pure.startswith(("6", "9")) else "sz"
        return prefix + pure

    def _tencent_daily_kline(self, code, limit=180):
        pure = normalize_code(code)[-6:]
        cache_key = ("tencent_daily", pure, limit)
        cached = self._kline_cache.get(cache_key)
        if cached and time.time() - cached["ts"] < 60:
            return cached["rows"]
        symbol = self._market_symbol(pure)
        try:
            url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            params = {"param": f"{symbol},day,,,{limit},qfq"}
            data = requests.get(url, params=params, timeout=2.5).json().get("data", {}).get(symbol, {})
            raw = data.get("qfqday") or data.get("day") or []
            rows = []
            for item in raw[-limit:]:
                close = float(item[2])
                volume = float(item[5]) if len(item) > 5 else 0
                rows.append(
                    {
                        "date": item[0],
                        "open": float(item[1]),
                        "close": close,
                        "high": float(item[3]),
                        "low": float(item[4]),
                        "volume": volume,
                        "amount": volume * close * 100,
                        "source": "腾讯前复权日K",
                        "valid": True,
                    }
                )
            if rows:
                self._kline_cache[cache_key] = {"ts": time.time(), "rows": rows}
            return rows
        except Exception:
            return []

    def _tencent_minute_line(self, code):
        pure = normalize_code(code)[-6:]
        cache_key = ("tencent_minute", pure)
        cached = self._kline_cache.get(cache_key)
        if cached and time.time() - cached["ts"] < 10:
            return cached["rows"]
        symbol = self._market_symbol(pure)
        try:
            url = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
            data = requests.get(url, params={"code": symbol}, timeout=2.5).json().get("data", {}).get(symbol, {})
            raw = data.get("data", {}).get("data", [])
            rows = []
            last_amount = 0.0
            for item in raw:
                parts = item.split()
                if len(parts) < 4:
                    continue
                time_text = parts[0]
                price = float(parts[1])
                volume = float(parts[2])
                amount = float(parts[3])
                rows.append(
                    {
                        "date": f"{time_text[:2]}:{time_text[2:]}",
                        "open": price,
                        "close": price,
                        "high": price,
                        "low": price,
                        "volume": max(0.0, volume),
                        "amount": max(0.0, amount - last_amount),
                        "cum_amount": amount,
                        "source": "腾讯分时",
                        "valid": True,
                    }
                )
                last_amount = amount
            if rows:
                self._kline_cache[cache_key] = {"ts": time.time(), "rows": rows}
            return rows
        except Exception:
            return []

    def indexes(self):
        rows = self._sina_index_quotes()
        if rows:
            return rows
        ak = self._akshare()
        if ak:
            rows = self._akshare_sina_index_quotes()
            if rows:
                return rows
        return []

    def index_quote(self, code, name):
        rows = self._sina_index_quotes([code])
        if rows:
            return rows[0]
        return {"code": code, "name": name, "price": None, "pct": None, "amount": None, "source": "不可用", "valid": False}

    def _sina_index_quotes(self, codes=None):
        selected = codes or list(INDEX_MAP.keys())
        try:
            url = "https://hq.sinajs.cn/list=" + ",".join(selected)
            resp = requests.get(url, timeout=2, headers={"Referer": "https://finance.sina.com.cn/"})
            resp.encoding = "gbk"
            rows = []
            for line in resp.text.splitlines():
                if '="' not in line:
                    continue
                code = line.split("=", 1)[0].split("_")[-1]
                payload = line.split('"', 2)[1]
                parts = payload.split(",")
                if len(parts) < 6 or not parts[0]:
                    continue
                prev_close = float(parts[2] or 0)
                price = float(parts[3] or 0)
                pct = (price - prev_close) / prev_close * 100 if prev_close else float(parts[4] or 0)
                amount = float(parts[9] or 0) if len(parts) > 9 else 0
                rows.append(
                    {
                        "code": code,
                        "name": INDEX_MAP.get(code, parts[0]),
                        "price": round(price, 4),
                        "pct": round(pct, 3),
                        "amount": amount,
                        "source": "新浪实时",
                        "valid": True,
                    }
                )
            found = {row["code"] for row in rows}
            return rows if all(code in found for code in selected) else []
        except Exception:
            return []

    def _akshare_sina_index_quotes(self):
        try:
            ak = self._akshare()
            if not ak:
                return []
            df = self._run(lambda: ak.stock_zh_index_spot_sina(), timeout=3)
            if df is None or df.empty:
                return []
            rows = []
            for code, name in INDEX_MAP.items():
                hit = df[df["代码"].astype(str) == code]
                if hit.empty:
                    return []
                r = hit.iloc[0]
                rows.append(
                    {
                        "code": code,
                        "name": name,
                        "price": float(r.get("最新价", 0) or 0),
                        "pct": float(r.get("涨跌幅", 0) or 0),
                        "amount": float(r.get("成交额", 0) or 0),
                        "source": "AkShare-新浪",
                        "valid": True,
                    }
                )
            return rows
        except Exception:
            return []

    def sectors(self, prefer_live=True):
        now = time.time()
        if self._sector_cache["data"] is not None and now - self._sector_cache["ts"] < 60:
            return self._sector_cache["data"]
        ak = self._akshare() if prefer_live else None
        if ak and prefer_live:
            industry = self._run(lambda: ak.stock_board_industry_name_em().head(60), timeout=2)
            concept = self._run(lambda: ak.stock_board_concept_name_em().head(80), timeout=2)
            if industry is not None and concept is not None:
                data = {
                    "industry": self._clean_sector(industry, "行业"),
                    "concept": self._clean_sector(concept, "概念"),
                    "source": "AkShare",
                }
                self._sector_cache = {"ts": now, "data": data}
                return data
        return self._fallback_sectors()

    def fund_flow(self, code: str, prefer_live=True):
        pure = normalize_code(code)[-6:]
        ak = self._akshare() if prefer_live else None
        if ak and prefer_live:
            df = self._run(
                lambda: ak.stock_individual_fund_flow(stock=pure, market="sh" if pure.startswith("6") else "sz"),
                timeout=2,
            )
            if df is not None and not df.empty:
                row = df.tail(1).iloc[0]
                main = float(row.get("主力净流入-净额", 0) or 0)
                return self._fund_state(main, "AkShare")
        base = random.uniform(-80000000, 100000000)
        return self._fund_state(base, "Fallback")

    def _quote_from_row(self, r, code):
        return {
            "code": code,
            "name": str(r.get("名称", code)),
            "price": float(r.get("最新价", 0) or 0),
            "pct": float(r.get("涨跌幅", 0) or 0),
            "amount": float(r.get("成交额", 0) or 0),
            "turnover": float(r.get("换手率", 0) or 0),
            "volume_ratio": float(r.get("量比", 0) or 0),
            "source": "AkShare",
        }

    def _eastmoney_quote(self, code):
        try:
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {"secid": eastmoney_sec_id(code), "fields": "f14,f43,f48,f50,f168,f170"}
            data = requests.get(url, params=params, timeout=3).json().get("data") or {}
            if not data:
                return None
            price = float(data.get("f43", 0) or 0) / 100
            pct = float(data.get("f170", 0) or 0) / 100
            return {
                "code": code,
                "name": str(data.get("f14") or code),
                "price": price,
                "pct": pct,
                "amount": float(data.get("f48", 0) or 0),
                "turnover": float(data.get("f168", 0) or 0) / 100,
                "volume_ratio": float(data.get("f50", 0) or 0) / 100,
                "source": "东方财富",
            }
        except Exception:
            return None

    def news(self, code: str, name: str):
        keywords = ["业绩", "政策催化", "订单", "增持", "减持", "监管", "重组", "行业景气"]
        picked = random.sample(keywords, 4)
        items = []
        for word in picked:
            direction = "利好" if word in ["业绩", "政策催化", "订单", "增持", "重组", "行业景气"] else "利空"
            items.append(
                {
                    "title": f"{name} 相关消息：{word}",
                    "summary": f"识别到关键词“{word}”，需要结合公告原文和成交量验证影响。",
                    "direction": direction,
                    "duration": "短中期" if direction == "利好" else "短期扰动",
                    "keyword": word,
                }
            )
        score = 66 if any(item["direction"] == "利好" for item in items) else 45
        if any(item["keyword"] in ["减持", "监管"] for item in items):
            score -= 15
        return {"score": max(0, min(100, score)), "items": items, "source": "关键词模拟/可接公告源"}

    def _clean_kline(self, df, minute=False):
        rename = {
            "日期": "date",
            "时间": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
        }
        out = df.rename(columns=rename)
        cols = ["date", "open", "close", "high", "low", "volume", "amount"]
        out = out[[c for c in cols if c in out.columns]].copy()
        for c in cols:
            if c not in out.columns:
                out[c] = 0
        out["date"] = out["date"].astype(str)
        return out[cols].to_dict("records")

    def _clean_sector(self, df, kind):
        rows = []
        for _, r in df.iterrows():
            rows.append(
                {
                    "name": str(r.get("板块名称", r.get("名称", ""))),
                    "pct": float(r.get("涨跌幅", 0) or 0),
                    "amount": float(r.get("成交额", 0) or 0),
                    "kind": kind,
                }
            )
        return rows

    def _fallback_quote(self, code):
        seed = sum(ord(c) for c in normalize_code(code))
        rng = random.Random(seed + datetime.now().toordinal())
        price = round(rng.uniform(6, 88), 2)
        pct = round(rng.uniform(-5.5, 6.8), 2)
        return {
            "code": normalize_code(code)[-6:],
            "name": self.best_name(code),
            "price": price,
            "pct": pct,
            "amount": round(rng.uniform(0.6, 90) * 100000000, 0),
            "turnover": round(rng.uniform(0.5, 18), 2),
            "volume_ratio": round(rng.uniform(0.55, 3.8), 2),
            "source": "Fallback",
        }

    def _fallback_kline(self, code, limit=180):
        rng = random.Random(sum(ord(c) for c in code))
        dates = [datetime.now() - timedelta(days=limit - i) for i in range(limit)]
        price = rng.uniform(8, 60)
        rows = []
        for day in dates:
            change = rng.uniform(-0.035, 0.04)
            open_price = price * (1 + rng.uniform(-0.015, 0.015))
            close = max(1, price * (1 + change))
            high = max(open_price, close) * (1 + rng.uniform(0, 0.025))
            low = min(open_price, close) * (1 - rng.uniform(0, 0.025))
            volume = rng.uniform(50000, 2000000)
            amount = volume * close * 100
            rows.append(
                {
                    "date": day.strftime("%Y-%m-%d"),
                    "open": round(open_price, 2),
                    "close": round(close, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "volume": round(volume, 0),
                    "amount": round(amount, 0),
                    "source": "Fallback",
                    "valid": False,
                }
            )
            price = close
        return rows

    def _fallback_sectors(self):
        names = ["半导体", "人工智能", "机器人", "新能源车", "创新药", "军工", "消费电子", "低空经济", "算力", "证券"]
        rows = [
            {"name": name, "pct": round(random.uniform(-3, 5), 2), "amount": random.randint(80, 900) * 100000000, "kind": "行业"}
            for name in names
        ]
        concepts = [
            {"name": name + "概念", "pct": round(random.uniform(-3, 6), 2), "amount": random.randint(50, 700) * 100000000, "kind": "概念"}
            for name in names
        ]
        return {"industry": rows, "concept": concepts, "source": "Fallback"}

    def _fund_state(self, main_flow, source):
        if main_flow > 60000000:
            phase, score = "吸筹/拉升", 82
        elif main_flow > 0:
            phase, score = "温和流入", 68
        elif main_flow < -80000000:
            phase, score = "出货/撤退", 32
        else:
            phase, score = "分歧", 52
        return {
            "main_net_inflow": round(main_flow, 0),
            "northbound": round(random.uniform(-80, 120) * 100000000, 0),
            "large_order": round(main_flow * random.uniform(0.35, 0.85), 0),
            "phase": phase,
            "score": score,
            "abnormal": abs(main_flow) > 90000000,
            "source": source,
        }


market_data = MarketData()
