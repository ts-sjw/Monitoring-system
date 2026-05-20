from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analyzer import analyze_market, analyze_stock

app = FastAPI(title="Stock AI System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "status": "running",
        "name": "Stock AI System",
        "risk_notice": "仅供学习和辅助分析，不构成投资建议，不自动交易。",
    }


@app.get("/market")
def market():
    return analyze_market()


@app.get("/stock/{code}")
def stock(code: str):
    return analyze_stock(code)
