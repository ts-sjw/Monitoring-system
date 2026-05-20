const api = {
  base:
    window.STOCK_API_BASE ||
    localStorage.getItem("STOCK_API_BASE") ||
    "https://monitoring-system-v5zc.onrender.com",
  dashboard: () => fetch(`${api.base}/api/dashboard`).then((r) => r.json()),
  market: () => fetch(`${api.base}/api/market`).then((r) => r.json()),
  stock: (code) => fetch(`${api.base}/api/stock/${code}`).then((r) => r.json()),
  quotes: (codes) => fetch(`${api.base}/api/quotes?codes=${encodeURIComponent(codes.join(","))}`).then((r) => r.json()),
  hotMoney: () => fetch(`${api.base}/api/hot-money`).then((r) => r.json()),
  stockHotMoney: (code) => fetch(`${api.base}/api/hot-money/stock/${code}`).then((r) => r.json()),
  save: (payload) =>
    fetch(`${api.base}/api/watchlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => r.json()),
  remove: (code) => fetch(`${api.base}/api/watchlist/${code}`, { method: "DELETE" }).then((r) => r.json()),
};

const state = {
  dashboard: null,
  selected: null,
  stock: null,
  charts: {},
  priceTimer: null,
  marketTimer: null,
  chartMode: "daily",
};

function chart(id) {
  if (!state.charts[id]) state.charts[id] = echarts.init(document.getElementById(id));
  state.charts[id].group = "stockSync";
  return state.charts[id];
}

function clsPct(value) {
  return value >= 0 ? "up" : "down";
}

function money(value) {
  const n = Number(value || 0);
  if (Math.abs(n) >= 100000000) return `${(n / 100000000).toFixed(2)}亿`;
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(2)}万`;
  return n.toFixed(0);
}

function fmtNum(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits);
}

function renderMarket(data) {
  const env = data.environment;
  chart("marketGauge").setOption({
    backgroundColor: "transparent",
    series: [
      {
        type: "gauge",
        min: 0,
        max: 100,
        radius: "92%",
        progress: { show: true, width: 10 },
        axisLine: { lineStyle: { width: 10, color: [[0.38, "#3fd08c"], [0.72, "#e6b84f"], [1, "#f05d5e"]] } },
        axisLabel: { color: "#92a39b", distance: 12, fontSize: 10 },
        pointer: { width: 4 },
        detail: { valueAnimation: true, formatter: `${env.state}\n{value}`, color: "#e9f0ec", fontSize: 18 },
        data: [{ value: env.score }],
      },
    ],
  });

  document.getElementById("indexStrip").innerHTML = data.indexes
    .map(
      (item) => `
      <div class="index-item">
        <div class="name">${item.name}</div>
        <div class="price">${fmtNum(item.price, 2)}</div>
        <div class="${clsPct(item.pct || 0)}">${fmtNum(item.pct, 2)}%</div>
        <div class="muted">${item.valid === false ? "行情不可用" : money(item.amount)}</div>
      </div>`
    )
    .join("");
}

function renderWatch(stocks) {
  const box = document.getElementById("watchList");
  box.innerHTML = stocks
    .map(({ quote, holding, analysis, stock_hot_money }) => {
      const active = state.selected === quote.code ? "active" : "";
      const hotLabel = stock_hot_money?.recommendation || "情绪待定";
      return `
        <div class="stock-row ${active}" data-code="${quote.code}">
          <div>
            <strong>${quote.name}</strong>
            <span class="muted">${quote.code}</span>
            <div class="stock-meta">
              <span class="${clsPct(quote.pct)}" data-pct="${quote.code}">${quote.pct.toFixed(2)}%</span>
              <span>分 ${analysis.score}</span>
              <span data-hot-label>${hotLabel}</span>
              <span>仓 ${holding?.holding_ratio || 0}%/${holding?.target_ratio || 0}%</span>
            </div>
          </div>
          <div class="row-actions">
            <span data-price="${quote.code}">${Number(quote.price || 0).toFixed(2)}</span>
            <button title="删除" data-delete="${quote.code}">×</button>
          </div>
        </div>`;
    })
    .join("");

  box.querySelectorAll(".stock-row").forEach((row) => {
    row.addEventListener("click", (event) => {
      const del = event.target.getAttribute("data-delete");
      if (del) {
        removeStock(del);
        return;
      }
      selectStock(row.dataset.code);
    });
  });
}

function renderAdvice(data) {
  const a = data.analysis;
  const q = data.quote;
  const plan = a.trade_plan || {};
  const hot = data.stock_hot_money || {};
  const hotScores = hot.scores || {};
  const tech = a.technical || {};
  document.getElementById("stockTitle").textContent = `${q.name} ${q.code}`;
  document.getElementById("dataSource").textContent = `行情源：${q.source}`;
  document.getElementById("adviceCard").innerHTML = `
    <div class="advice-head">
      <div class="big-score">${a.score}</div>
      <div>
        <div class="advice-title">${a.advice}</div>
        <div class="position">建议仓位 ${a.position}</div>
        <div class="muted">${a.one_liner}</div>
      </div>
    </div>
    <div class="kv">
      <div><span>支撑位</span>${fmtNum(a.support, 2)}</div>
      <div><span>压力位</span>${fmtNum(a.pressure, 2)}</div>
      <div><span>止损位</span>${fmtNum(a.stop_loss, 2)}</div>
    </div>
    <div class="message"><span class="tag">技术位</span>${tech.level_note || "支撑/压力基于真实历史K线计算"}；数据源：${tech.data_source || "未知"}</div>
    <div class="trade-plan">
      <div><span>买点建议</span>${plan.buy_point || "等待分析"}</div>
      <div><span>加仓条件</span>${plan.add_point || "等待分析"}</div>
      <div><span>卖点/止盈</span>${plan.sell_point || "等待分析"}</div>
      <div><span>风控卖点</span>${plan.reduce_point || "等待分析"}</div>
    </div>
    <div class="hot-advice">
      <div><span>游资建议</span>${hot.recommendation || "数据不足"}</div>
      <div><span>打板风险</span>${fmtNum(hotScores.board_risk, 1)}</div>
      <div><span>接力风险</span>${fmtNum(hotScores.relay_risk, 1)}</div>
      <div><span>龙头强度</span>${fmtNum(hotScores.leader_strength, 1)}</div>
      <div class="wide"><span>情绪标签</span>${(hot.tags || []).join("、") || "未进入涨停/龙虎核心池"}；${hot.summary || ""}</div>
    </div>
    <div>
      <strong>看多理由</strong>
      <ul class="reason-list">${a.bullish_reasons.map((x) => `<li>${x}</li>`).join("")}</ul>
    </div>
    <div>
      <strong>风险点</strong>
      <ul class="reason-list">${a.risks.map((x) => `<li>${x}</li>`).join("")}</ul>
    </div>
    <div class="message"><span class="tag">${a.state}</span>${a.volume_price.explain}</div>
  `;

  const names = {
    market: "大盘环境",
    sector: "板块轮动",
    technical: "个股技术",
    fund: "资金行为",
    volume_price: "量价关系",
    news: "消息催化",
  };
  document.getElementById("scoreGrid").innerHTML = Object.entries(a.sub_scores)
    .map(([key, value]) => `<div><span>${names[key]}</span>${value}</div>`)
    .join("");
}

function renderKline(data) {
  if (state.chartMode === "minute") {
    renderMinuteLine(data);
    return;
  }
  const indicators = data.analysis.technical.indicators || [];
  const dates = indicators.map((x) => x.date);
  const values = indicators.map((x) => [x.open, x.close, x.low, x.high]);
  const volume = indicators.map((x) => x.volume);
  chart("kChart").setOption({
    animation: false,
    tooltip: { trigger: "axis" },
    legend: { textStyle: { color: "#92a39b" }, data: ["K线", "MA5", "MA10", "MA20", "成交量"] },
    grid: [{ left: 48, right: 24, top: 34, height: "58%" }, { left: 48, right: 24, top: "74%", height: "18%" }],
    xAxis: [{ type: "category", data: dates }, { type: "category", data: dates, gridIndex: 1 }],
    yAxis: [{ scale: true }, { gridIndex: 1, splitNumber: 2 }],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 50, end: 100 },
      { type: "slider", xAxisIndex: [0, 1], start: 50, end: 100, bottom: 4, height: 18 },
    ],
    series: [
      { name: "K线", type: "candlestick", data: values, itemStyle: { color: "#f05d5e", color0: "#3fd08c", borderColor: "#f05d5e", borderColor0: "#3fd08c" } },
      { name: "MA5", type: "line", data: indicators.map((x) => x.ma5), smooth: true, showSymbol: false },
      { name: "MA10", type: "line", data: indicators.map((x) => x.ma10), smooth: true, showSymbol: false },
      { name: "MA20", type: "line", data: indicators.map((x) => x.ma20), smooth: true, showSymbol: false },
      { name: "成交量", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: volume, itemStyle: { color: "#56c8e8" } },
    ],
  });

  lineChart("macdChart", dates, [
    ["DIF", indicators.map((x) => x.dif)],
    ["DEA", indicators.map((x) => x.dea)],
    ["MACD", indicators.map((x) => x.macd), "bar"],
  ]);
  lineChart("rsiChart", dates, [["RSI", indicators.map((x) => x.rsi)]]);
  lineChart("kdjChart", dates, [
    ["K", indicators.map((x) => x.k)],
    ["D", indicators.map((x) => x.d)],
    ["J", indicators.map((x) => x.j)],
  ]);
  echarts.connect("stockSync");
}

function renderMinuteLine(data) {
  const rows = data.minute || [];
  const dates = rows.map((x) => x.date);
  const price = rows.map((x) => x.close);
  const avg = movingAverage(price, 20);
  const volume = rows.map((x) => x.volume);
  chart("kChart").setOption(
    {
      animation: false,
      tooltip: { trigger: "axis" },
      legend: { textStyle: { color: "#92a39b" }, data: ["分时", "均价", "成交量"] },
      grid: [{ left: 48, right: 24, top: 34, height: "58%" }, { left: 48, right: 24, top: "74%", height: "18%" }],
      xAxis: [{ type: "category", data: dates }, { type: "category", data: dates, gridIndex: 1 }],
      yAxis: [{ scale: true }, { gridIndex: 1, splitNumber: 2 }],
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1], start: 0, end: 100 },
        { type: "slider", xAxisIndex: [0, 1], start: 0, end: 100, bottom: 4, height: 18 },
      ],
      series: [
        { name: "分时", type: "line", data: price, smooth: true, showSymbol: false, lineStyle: { color: "#56c8e8", width: 2 } },
        { name: "均价", type: "line", data: avg, smooth: true, showSymbol: false, lineStyle: { color: "#e6b84f", width: 1 } },
        { name: "成交量", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: volume, itemStyle: { color: "#4b6bff" } },
      ],
    },
    true
  );
  lineChart("macdChart", dates, [["分时涨跌", price.map((x, i) => (i ? ((x - price[i - 1]) / price[i - 1]) * 100 : 0))]]);
  lineChart("rsiChart", dates, [["分时价", price]]);
  lineChart("kdjChart", dates, [["成交额", rows.map((x) => x.cum_amount || x.amount || 0), "bar"]]);
  echarts.connect("stockSync");
}

function movingAverage(values, windowSize) {
  return values.map((_, idx) => {
    const start = Math.max(0, idx - windowSize + 1);
    const slice = values.slice(start, idx + 1);
    return Number((slice.reduce((sum, x) => sum + Number(x || 0), 0) / slice.length).toFixed(3));
  });
}

function lineChart(id, dates, series) {
  chart(id).setOption({
    animation: false,
    tooltip: { trigger: "axis" },
    grid: { left: 38, right: 16, top: 24, bottom: 28 },
    xAxis: { type: "category", data: dates, axisLabel: { show: false } },
    yAxis: { scale: true, splitLine: { lineStyle: { color: "#203028" } } },
    dataZoom: [{ type: "inside", xAxisIndex: 0, start: state.chartMode === "daily" ? 50 : 0, end: 100 }],
    series: series.map(([name, data, type]) => ({ name, type: type || "line", data, showSymbol: false, smooth: true })),
  }, true);
}

function renderBottom(data) {
  const rotation = data.rotation || state.dashboard.rotation;
  const sectors = [...(rotation.main || []), ...(rotation.catch_up || []), ...(rotation.fading || [])];
  chart("sectorHeat").setOption({
    tooltip: {},
    series: [
      {
        type: "treemap",
        roam: false,
        breadcrumb: { show: false },
        data: sectors.map((s) => ({
          name: s.name,
          value: Math.max(1, Math.abs(s.pct) * 10),
          pct: s.pct,
          itemStyle: { color: s.pct >= 0 ? "#7b2e32" : "#1d6b4b" },
          label: { formatter: `${s.name}\n${s.pct}%` },
        })),
      },
    ],
  });

  const fund = data.fund;
  document.getElementById("fundFlow").innerHTML = fund
    ? `
      <div class="fund-line"><span>主力净流入</span><strong>${money(fund.main_net_inflow)}</strong></div>
      <div class="fund-line"><span>北向资金</span><strong>${money(fund.northbound)}</strong></div>
      <div class="fund-line"><span>大单资金</span><strong>${money(fund.large_order)}</strong></div>
      <div class="fund-line"><span>识别阶段</span><strong>${fund.phase}</strong></div>
      <div class="fund-line"><span>异常放量</span><strong>${fund.abnormal ? "是" : "否"}</strong></div>`
    : `<div class="fund-line">选择股票后显示资金流。</div>`;

  const news = data.news?.items || [];
  document.getElementById("newsFlow").innerHTML = news.length
    ? news
        .map(
          (n) => `
        <div class="message">
          <span class="tag">${n.direction}</span><strong>${n.title}</strong>
          <div class="muted">${n.summary}</div>
          <div class="muted">持续性：${n.duration}</div>
        </div>`
        )
        .join("")
    : `<div class="message">选择股票后显示消息面关键词。</div>`;

  renderHotMoney(data.hot_money || state.dashboard?.hot_money, data.stock_hot_money);
}

function renderHotMoney(hotMoney, stockHot, loadingText) {
  const box = document.getElementById("hotMoneyFlow");
  if (!box) return;
  if (loadingText) {
    box.innerHTML = `<div class="message">${loadingText}</div>`;
    return;
  }
  if (!hotMoney || !hotMoney.valid) {
    box.innerHTML = `<div class="message">游资情绪数据不足：${hotMoney?.reason || "等待数据"}</div>`;
    return;
  }
  const s = hotMoney.summary;
  const scores = hotMoney.scores || {};
  const leaders = (hotMoney.leaders || []).slice(0, 5);
  const broken = (hotMoney.broken || []).slice(0, 4);
  box.innerHTML = `
    <div class="emotion-grid">
      <div><span>情绪周期</span><strong>${s.cycle}</strong></div>
      <div><span>涨停/跌停</span><strong>${s.limit_up_count}/${s.limit_down_count}</strong></div>
      <div><span>炸板率</span><strong>${fmtNum(s.break_rate, 1)}%</strong></div>
      <div><span>连板高度</span><strong>${s.limit_height}板</strong></div>
      <div><span>打板风险</span><strong>${fmtNum(scores.board_risk, 1)}</strong></div>
      <div><span>接力风险</span><strong>${fmtNum(scores.relay_risk, 1)}</strong></div>
      <div><span>龙头强度</span><strong>${fmtNum(scores.leader_strength, 1)}</strong></div>
      <div><span>个股情绪</span><strong>${stockHot?.recommendation || "待选股"}</strong></div>
    </div>
    <div class="message"><span class="tag">主线</span>${(hotMoney.main_industries || []).join("、") || "暂无"}</div>
    <div class="message"><span class="tag">来源</span>${hotMoney.source || "未知"}${hotMoney.cache_saved_at ? `；缓存时间 ${hotMoney.cache_saved_at}` : ""}</div>
    <div class="mini-list"><strong>市场龙头</strong>${leaders.map((x) => `<div>${x.name} ${x.code} ${x.limit_count}板 ${x.industry}</div>`).join("") || "<div>暂无</div>"}</div>
    <div class="mini-list"><strong>炸板风险</strong>${broken.map((x) => `<div>${x.name} ${x.code} 炸板${x.break_count}次 ${x.industry}</div>`).join("") || "<div>暂无</div>"}</div>
    <div class="muted">${hotMoney.lhb?.valid ? "龙虎榜数据已接入" : "龙虎榜：" + (hotMoney.lhb?.reason || "暂无数据")}</div>
  `;
}

async function selectStock(code) {
  state.selected = code;
  state.stock = await api.stock(code);
  renderWatch(state.dashboard.stocks);
  renderAdvice(state.stock);
  renderKline(state.stock);
  renderBottom(state.stock);
  loadStockHotMoney(code);
}

async function loadStockHotMoney(code) {
  renderHotMoney(null, null, "游资情绪加载中...");
  try {
    const data = await api.stockHotMoney(code);
    if (state.selected !== code || !state.stock) return;
    state.stock.hot_money = data.hot_money;
    state.stock.stock_hot_money = data.stock_hot_money;
    renderAdvice(state.stock);
    renderBottom(state.stock);
    updateWatchHotLabel(code, data.stock_hot_money?.recommendation || "情绪待定");
  } catch (error) {
    renderHotMoney({ valid: false, reason: "游资情绪接口暂不可用" });
  }
}

function updateWatchHotLabel(code, label) {
  const node = document.querySelector(`.stock-row[data-code="${code}"] [data-hot-label]`);
  if (node) node.textContent = label;
}

async function removeStock(code) {
  await api.remove(code);
  await loadDashboard();
}

async function loadDashboard() {
  state.dashboard = await api.dashboard();
  renderMarket(state.dashboard);
  renderWatch(state.dashboard.stocks);
  renderBottom(state.dashboard);
  const first = state.dashboard.stocks[0]?.quote?.code;
  if (first) await selectStock(state.selected || first);
  startPriceRefresh();
  startMarketRefresh();
}

function updateQuoteDisplay(quote) {
  const priceNodes = document.querySelectorAll(`[data-price="${quote.code}"]`);
  const pctNodes = document.querySelectorAll(`[data-pct="${quote.code}"]`);
  priceNodes.forEach((node) => {
    node.textContent = Number(quote.price || 0).toFixed(2);
  });
  pctNodes.forEach((node) => {
    node.textContent = `${Number(quote.pct || 0).toFixed(2)}%`;
    node.classList.toggle("up", Number(quote.pct || 0) >= 0);
    node.classList.toggle("down", Number(quote.pct || 0) < 0);
  });
  if (state.stock?.quote?.code === quote.code) {
    state.stock.quote = { ...state.stock.quote, ...quote };
    document.getElementById("dataSource").textContent = `行情源：${quote.source} · 最新价 ${Number(quote.price || 0).toFixed(2)} · ${Number(quote.pct || 0).toFixed(2)}%`;
  }
}

async function refreshLatestPrices() {
  const codes = (state.dashboard?.stocks || []).map((item) => item.quote.code);
  if (!codes.length) return;
  try {
    const data = await api.quotes(codes);
    (data.quotes || []).forEach(updateQuoteDisplay);
  } catch (error) {
    console.warn("latest quote refresh failed", error);
  }
}

function startPriceRefresh() {
  if (state.priceTimer) clearInterval(state.priceTimer);
  refreshLatestPrices();
  state.priceTimer = setInterval(refreshLatestPrices, 1000);
}

async function refreshMarketOnly() {
  try {
    const data = await api.market();
    renderMarket(data);
  } catch (error) {
    console.warn("market refresh failed", error);
  }
}

function startMarketRefresh() {
  if (state.marketTimer) clearInterval(state.marketTimer);
  state.marketTimer = setInterval(refreshMarketOnly, 3000);
}

document.getElementById("watchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    code: document.getElementById("codeInput").value.trim(),
    name: document.getElementById("nameInput").value.trim(),
    cost: Number(document.getElementById("costInput").value || 0),
    holding_ratio: Number(document.getElementById("holdInput").value || 0),
    target_ratio: Number(document.getElementById("targetInput").value || 0),
  };
  if (!payload.code) return;
  await api.save(payload);
  document.getElementById("watchForm").reset();
  state.selected = payload.code.slice(-6);
  await loadDashboard();
});

document.getElementById("refreshBtn").addEventListener("click", loadDashboard);
document.querySelectorAll("[data-chart-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    state.chartMode = button.dataset.chartMode;
    document.querySelectorAll("[data-chart-mode]").forEach((item) => item.classList.toggle("active", item === button));
    if (state.stock) renderKline(state.stock);
  });
});
window.addEventListener("resize", () => Object.values(state.charts).forEach((c) => c.resize()));

loadDashboard().catch((error) => {
  document.body.insertAdjacentHTML("afterbegin", `<div class="notice">系统启动异常：${error.message}</div>`);
});
