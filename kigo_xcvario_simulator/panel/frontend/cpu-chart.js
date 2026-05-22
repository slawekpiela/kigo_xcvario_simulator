const CPU_LOG_ENDPOINT = "/api/v1/pi/cpu-temperature-log?limit=7200";

const canvas = document.getElementById("cpu-chart-canvas");
const statusPill = document.getElementById("cpu-chart-status");
const rangeNode = document.getElementById("cpu-chart-range");
const summaryGrid = document.getElementById("cpu-chart-summary");
const errorNode = document.getElementById("cpu-chart-error");
const refreshButton = document.getElementById("refresh-cpu-chart-button");

async function loadCpuChart() {
  setStatus("idle", "Loading");
  showError("");
  try {
    const response = await fetch(`${CPU_LOG_ENDPOINT}&ts=${Date.now()}`);
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error((payload && (payload.message || payload.error)) || `${response.status} ${response.statusText}`);
    }
    const payload = await response.json();
    const records = normalizeRecords(payload.records || []);
    if (records.length === 0) {
      throw new Error("No CPU log samples available.");
    }
    drawChart(records);
    renderSummary(payload.summary, payload.source, records);
    setStatus("ok", "Snapshot");
  } catch (error) {
    setStatus("error", "Error");
    showError(String(error.message || error));
  }
}

function normalizeRecords(records) {
  return records
    .map((record) => ({
      timestamp: String(record.timestamp || ""),
      date: new Date(record.timestamp),
      temperatureC: finiteOrNull(record.cpu_temp_c),
      cpuPercent: finiteOrNull(record.cpu_used_percent),
    }))
    .filter((record) => !Number.isNaN(record.date.getTime()) && (record.temperatureC !== null || record.cpuPercent !== null));
}

function finiteOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function drawChart(records) {
  const ctx = canvas.getContext("2d");
  const scale = window.devicePixelRatio || 1;
  const cssWidth = canvas.clientWidth || canvas.width;
  const cssHeight = Math.max(420, Math.round(cssWidth * 0.46));
  canvas.width = Math.round(cssWidth * scale);
  canvas.height = Math.round(cssHeight * scale);
  canvas.style.height = `${cssHeight}px`;
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  const margin = { left: 74, right: 78, top: 46, bottom: 64 };
  const plot = {
    x: margin.left,
    y: margin.top,
    width: cssWidth - margin.left - margin.right,
    height: cssHeight - margin.top - margin.bottom,
  };

  const timeMin = records[0].date.getTime();
  const timeMax = Math.max(records[records.length - 1].date.getTime(), timeMin + 1000);
  const temps = records.map((record) => record.temperatureC).filter((value) => value !== null);
  const cpus = records.map((record) => record.cpuPercent).filter((value) => value !== null);
  const tempRange = paddedRange(Math.min(...temps), Math.max(...temps), 1);
  const cpuRange = [0, Math.max(5, Math.ceil(Math.max(...cpus) / 5) * 5)];

  drawFrame(ctx, plot);
  drawGrid(ctx, plot, tempRange, cpuRange, timeMin, timeMax);
  drawSeries(ctx, plot, records, timeMin, timeMax, tempRange, "temperatureC", "#ff8175", 2.3);
  drawSeries(ctx, plot, records, timeMin, timeMax, cpuRange, "cpuPercent", "#77e4c8", 1.8);
  drawLegend(ctx, plot);
}

function paddedRange(min, max, pad) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return [0, 1];
  }
  if (min === max) {
    return [min - 1, max + 1];
  }
  return [Math.floor(min - pad), Math.ceil(max + pad)];
}

function drawFrame(ctx, plot) {
  ctx.fillStyle = "rgba(255, 255, 255, 0.035)";
  ctx.strokeStyle = "rgba(224, 239, 231, 0.16)";
  ctx.lineWidth = 1;
  ctx.fillRect(plot.x, plot.y, plot.width, plot.height);
  ctx.strokeRect(plot.x, plot.y, plot.width, plot.height);
}

function drawGrid(ctx, plot, tempRange, cpuRange, timeMin, timeMax) {
  ctx.font = "14px Avenir Next, Segoe UI, sans-serif";
  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(224, 239, 231, 0.08)";
  ctx.fillStyle = "rgba(238, 246, 241, 0.72)";
  ctx.textBaseline = "middle";

  for (let index = 0; index <= 5; index += 1) {
    const ratio = index / 5;
    const y = plot.y + plot.height * ratio;
    const temp = tempRange[1] - (tempRange[1] - tempRange[0]) * ratio;
    const cpu = cpuRange[1] - (cpuRange[1] - cpuRange[0]) * ratio;
    drawLine(ctx, plot.x, y, plot.x + plot.width, y);
    ctx.textAlign = "right";
    ctx.fillText(temp.toFixed(0), plot.x - 12, y);
    ctx.textAlign = "left";
    ctx.fillText(cpu.toFixed(0), plot.x + plot.width + 12, y);
  }

  ctx.textBaseline = "top";
  ctx.textAlign = "center";
  for (let index = 0; index <= 6; index += 1) {
    const ratio = index / 6;
    const x = plot.x + plot.width * ratio;
    const timestamp = new Date(timeMin + (timeMax - timeMin) * ratio);
    drawLine(ctx, x, plot.y, x, plot.y + plot.height);
    ctx.fillText(formatTime(timestamp), x, plot.y + plot.height + 20);
  }

  ctx.save();
  ctx.fillStyle = "#ff8175";
  ctx.translate(22, plot.y + plot.height / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText("Temperature (C)", 0, 0);
  ctx.restore();

  ctx.save();
  ctx.fillStyle = "#77e4c8";
  ctx.translate(plot.x + plot.width + 58, plot.y + plot.height / 2);
  ctx.rotate(Math.PI / 2);
  ctx.fillText("CPU (%)", 0, 0);
  ctx.restore();
}

function drawSeries(ctx, plot, records, timeMin, timeMax, valueRange, key, color, width) {
  ctx.beginPath();
  let hasPoint = false;
  for (const record of records) {
    const value = record[key];
    if (value === null) {
      continue;
    }
    const x = plot.x + ((record.date.getTime() - timeMin) / (timeMax - timeMin)) * plot.width;
    const y = plot.y + ((valueRange[1] - value) / (valueRange[1] - valueRange[0])) * plot.height;
    if (hasPoint) {
      ctx.lineTo(x, y);
    } else {
      ctx.moveTo(x, y);
      hasPoint = true;
    }
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.stroke();
}

function drawLegend(ctx, plot) {
  const x = plot.x + 20;
  const y = plot.y + 20;
  ctx.fillStyle = "rgba(16, 23, 20, 0.9)";
  ctx.strokeStyle = "rgba(224, 239, 231, 0.16)";
  roundRect(ctx, x, y, 300, 76, 12);
  ctx.fill();
  ctx.stroke();
  drawLegendItem(ctx, x + 22, y + 26, "#ff8175", "CPU temperature (C)");
  drawLegendItem(ctx, x + 22, y + 52, "#77e4c8", "CPU usage (%)");
}

function drawLegendItem(ctx, x, y, color, label) {
  ctx.strokeStyle = color;
  ctx.lineWidth = 4;
  drawLine(ctx, x, y, x + 48, y);
  ctx.fillStyle = "#eef6f1";
  ctx.font = "16px Avenir Next, Segoe UI, sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillText(label, x + 64, y);
}

function drawLine(ctx, x1, y1, x2, y2) {
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
}

function roundRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

function renderSummary(summary, source, records) {
  const first = records[0];
  const last = records[records.length - 1];
  rangeNode.textContent = `${formatTime(first.date)} - ${formatTime(last.date)} from ${source.target}`;
  summaryGrid.innerHTML = "";
  appendSummary("Samples", summary.sample_count ?? records.length);
  appendSummary("Temperature", rangeText(summary.temperature_c, "C"));
  appendSummary("CPU", rangeText(summary.cpu_percent, "%"));
  appendSummary("Log", source.path || "-");
}

function appendSummary(label, value) {
  const wrapper = document.createElement("div");
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = label;
  dd.textContent = String(value);
  wrapper.appendChild(dt);
  wrapper.appendChild(dd);
  summaryGrid.appendChild(wrapper);
}

function rangeText(series, suffix) {
  if (!series || series.min === null || series.avg === null || series.max === null) {
    return "-";
  }
  return `${Number(series.min).toFixed(1)} / ${Number(series.avg).toFixed(1)} / ${Number(series.max).toFixed(1)} ${suffix}`;
}

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function setStatus(kind, label) {
  statusPill.className = `status-pill status-pill--${kind}`;
  statusPill.textContent = label;
}

function showError(message) {
  errorNode.hidden = !message;
  errorNode.textContent = message || "";
}

refreshButton.addEventListener("click", () => {
  void loadCpuChart();
});

window.addEventListener("resize", () => {
  void loadCpuChart();
});

void loadCpuChart();
