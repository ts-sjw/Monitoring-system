const API_BASE =
  window.STOCK_API_BASE ||
  localStorage.getItem("STOCK_API_BASE") ||
  "http://127.0.0.1:8000";

let chart;

async function analyze() {
  const code = document.getElementById("codeInput").value.trim();
  if (!code) return alert("请输入股票代码");

  const result = document.getElementById("result");
  result.className = "card";
  result.innerHTML = "分析中...";

  try {
    const res = await fetch(`${API_BASE}/stock/${code}`);
    if (!res.ok) throw new Error(`接口请求失败：${res.status}`);
    const data = await res.json();
    renderResult(data);
    renderChart(data.chart || []);
  } catch (error) {
    result.innerHTML = `<p class="bad">请求失败：${error.message}</p><p>请确认后端地址：${API_BASE}</p>`;
  }
}

function renderResult(data) {
  document.getElementById("result").innerHTML = `
    <h2>${data.code}</h2>
    <div class="grid">
      <p><b>当前价格：</b>${data.price}</p>
      <p><b>涨跌幅：</b>${data.pct}%</p>
      <p><b>综合评分：</b>${data.score}</p>
      <p><b>当前状态：</b>${data.current_status}</p>
      <p><b>大盘状态：</b>${data.market_status}</p>
      <p><b>操作建议：</b>${data.advice}</p>
      <p><b>建议仓位：</b>${data.position}</p>
      <p><b>支撑位：</b>${data.support}</p>
      <p><b>压力位：</b>${data.pressure}</p>
      <p><b>止损位：</b>${data.stop_loss}</p>
      <p><b>数据源：</b>${data.data_source}</p>
    </div>
    <p><b>量价判断：</b>${data.volume_price}</p>
    <p><b>技术趋势：</b>${data.tech_notes.join("、")}</p>
    <p><b>风险提示：</b>${data.risk}</p>
    <hr>
    <p>${data.summary}</p>
  `;
}

function renderChart(rows) {
  if (!chart) chart = echarts.init(document.getElementById("chart"));
  const dates = rows.map((x) => x.date);
  const k = rows.map((x) => [x.open, x.close, x.low, x.high]);
  const volume = rows.map((x) => x.volume);

  chart.setOption({
    tooltip: { trigger: "axis" },
    legend: { data: ["K线", "成交量"], textStyle: { color: "#cbd5e1" } },
    grid: [
      { left: 50, right: 24, top: 40, height: "56%" },
      { left: 50, right: 24, top: "74%", height: "16%" },
    ],
    xAxis: [
      { type: "category", data: dates },
      { type: "category", data: dates, gridIndex: 1 },
    ],
    yAxis: [{ scale: true }, { gridIndex: 1 }],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 50, end: 100 },
      { type: "slider", xAxisIndex: [0, 1], start: 50, end: 100 },
    ],
    series: [
      {
        name: "K线",
        type: "candlestick",
        data: k,
        itemStyle: {
          color: "#ef4444",
          color0: "#22c55e",
          borderColor: "#ef4444",
          borderColor0: "#22c55e",
        },
      },
      {
        name: "成交量",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volume,
        itemStyle: { color: "#38bdf8" },
      },
    ],
  });
}

window.addEventListener("resize", () => chart && chart.resize());
