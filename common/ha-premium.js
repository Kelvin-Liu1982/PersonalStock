/*
 * common/ha-premium.js — H/A 溢价率（日频）卡片内联图表
 * ------------------------------------------------------------------
 * 纯前端、无依赖、无构建；与 common/ha_premium.py 配套：
 *   Python 端负责取数 → 生成 <script id="haPremiumData" type="application/json"> 序列；
 *   本文件负责把序列渲染成卡片内嵌 SVG，并在「刷新行情」后同步更新末点。
 *
 * 数据格式（script#haPremiumData 的 textContent）：
 *   { "<key>": { "a":"sh601898", "h":"hk01898", "unit":"%",
 *                "updated":"2026-10-23", "series": [["2025-03-11", -25.2], ...] } }
 *   series 每项 [日期, 溢价率%]，可选第三项 1 表示「盘中实时点」。
 *
 * 用法（看板 HTML）：
 *   <div class="hachart" data-ha-key="601898"></div>
 *   <script id="haPremiumData" type="application/json">{...}</script>
 *   <script src="../common/ha-premium.js" defer></script>
 *
 * 与行情联动：
 *   quote-live.js 每次成功刷新后会在 document 上派发 'quote:updated'
 *   （detail = { bar, data }，data.premium 为小数比例）；本文件收到后：
 *     · 末点日期 == 今天 → 就地改写末点数值；
 *     · 末点日期 < 今天且为工作日 → 追加「盘中」点（空心点标识）；
 *     · 周末 → 只改写末点（周六日行情仍是周五收盘，不应新增点）。
 * ------------------------------------------------------------------
 */
(function () {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';
  var LINE = '#15616d';      // 与看板 --acc2 一致（比率类指标用中性青，不用涨跌红绿）
  var ACCENT = '#c8102e';    // 末点/实时点强调
  var UP = '#c8102e';        // 溢价（H 更贵）
  var DOWN = '#2e9e6b';      // 折价（H 更便宜）
  var GRID = '#eef2f6';
  var TICK = '#7a8694';
  var ZERO = '#cbd5e1';

  var store = {};             // key -> series 数据（会被实时刷新就地修改）
  var charts = [];            // { el, key, hoverIdx }

  /* ---------------- 工具 ---------------- */
  function todayStr() {
    var d = new Date();
    var p = function (n) { return String(n).padStart(2, '0'); };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  }

  function isWeekend() {
    var w = new Date().getDay();
    return w === 0 || w === 6;
  }

  function fmtPct(v, d) {
    if (typeof v !== 'number' || !isFinite(v)) return '—';
    d = d == null ? 2 : d;
    return (v > 0 ? '+' : '') + v.toFixed(d) + '%';
  }

  function niceAxis(lo, hi, ticks) {
    ticks = ticks || 4;
    var span = (hi - lo) || (Math.abs(hi) * 0.1 || 1);
    var raw = span / ticks;
    var mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var step = mag;
    var mults = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < mults.length; i++) {
      if (raw <= mults[i] * mag) { step = mults[i] * mag; break; }
    }
    var ylo = Math.floor((lo - span * 0.05) / step) * step;
    var yhi = Math.ceil((hi + span * 0.05) / step) * step;
    if (yhi - ylo < step) yhi = ylo + step;
    return { lo: ylo, hi: yhi, step: step };
  }

  function loadStore() {
    var tag = document.getElementById('haPremiumData');
    if (!tag) return {};
    try {
      var obj = JSON.parse(tag.textContent || '{}');
      var out = {};
      Object.keys(obj).forEach(function (k) {
        var d = obj[k];
        if (!d || !d.series || !d.series.length) return;
        out[k] = {
          a: d.a || '', h: d.h || '',
          updated: d.updated || d.series[d.series.length - 1][0],
          series: d.series.map(function (r) { return [r[0], r[1], r[2] || 0]; })
        };
      });
      return out;
    } catch (e) {
      return {};
    }
  }

  /* ---------------- 渲染 ---------------- */
  function render(c) {
    var d = store[c.key];
    var box = c.svgWrap;
    if (!d) { box.innerHTML = ''; return; }

    var w = Math.max(320, box.clientWidth || 900);
    var h = 150;
    var padL = 46, padR = 14, padT = 14, padB = 22;
    var pw = w - padL - padR, ph = h - padT - padB;
    var s = d.series, n = s.length;
    var vals = s.map(function (r) { return r[1]; });
    var ax = niceAxis(Math.min.apply(null, vals), Math.max.apply(null, vals), 5);

    function X(i) { return padL + (n > 1 ? pw * i / (n - 1) : pw / 2); }
    function Y(v) { return padT + ph * (1 - (v - ax.lo) / (ax.hi - ax.lo)); }

    var dec = (Math.abs(ax.step - Math.round(ax.step)) < 1e-9) ? 0 : 1;
    var o = [];
    o.push('<svg viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="' + h +
           '" xmlns="' + NS + '" font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">');
    o.push('<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="#ffffff"/>');

    // y 网格
    for (var v = ax.lo; v <= ax.hi + ax.step * 1e-6; v += ax.step) {
      var gy = Y(v);
      o.push('<line x1="' + padL + '" y1="' + gy.toFixed(1) + '" x2="' + (w - padR) +
             '" y2="' + gy.toFixed(1) + '" stroke="' + GRID + '" stroke-width="1"/>');
      o.push('<text x="' + (padL - 6) + '" y="' + (gy + 3.5).toFixed(1) + '" fill="' + TICK +
             '" font-size="10" text-anchor="end">' + fmtPct(v, dec) + '</text>');
    }
    // 零轴
    if (ax.lo < 0 && ax.hi > 0) {
      var zy = Y(0);
      o.push('<line x1="' + padL + '" y1="' + zy.toFixed(1) + '" x2="' + (w - padR) +
             '" y2="' + zy.toFixed(1) + '" stroke="' + ZERO + '" stroke-dasharray="4 3"/>');
    }

    // 面积 + 折线
    var pts = [];
    for (var i = 0; i < n; i++) pts.push(X(i).toFixed(1) + ' ' + Y(vals[i]).toFixed(1));
    o.push('<path d="M' + padL + ' ' + (padT + ph).toFixed(1) + ' L' + pts.join(' L') +
           ' L' + (w - padR) + ' ' + (padT + ph).toFixed(1) + ' Z" fill="' + LINE +
           '" fill-opacity="0.07"/>');
    o.push('<path d="M' + pts.join(' L') + '" fill="none" stroke="' + LINE +
           '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>');

    // 末点（实心=收盘，空心=盘中）
    var last = s[n - 1];
    var isLive = !!last[2];
    o.push('<circle cx="' + X(n - 1).toFixed(1) + '" cy="' + Y(last[1]).toFixed(1) +
           '" r="3.4" fill="' + (isLive ? '#ffffff' : ACCENT) + '" stroke="' + ACCENT +
           '" stroke-width="1.6"/>');

    // x 轴月份标签：按可用宽度决定个数
    var maxLab = Math.max(2, Math.floor(pw / 110));
    var seen = {};
    var marks = [];
    for (var j = 0; j < n; j++) {
      var m = s[j][0].slice(0, 7);
      if (seen[m]) continue;
      seen[m] = 1;
      marks.push(j);
    }
    var stepIdx = Math.max(1, Math.ceil(marks.length / maxLab));
    var drawn = [];
    for (var k = 0; k < marks.length; k += stepIdx) drawn.push(marks[k]);
    if (drawn[drawn.length - 1] !== n - 1) drawn.push(n - 1);

    drawn.forEach(function (idx, order) {
      var anchor = idx === n - 1 ? 'end' : (order === 0 ? 'start' : 'middle');
      var lx = X(idx) + (idx === n - 1 ? 0 : (order === 0 ? 2 : 0));
      var lab = (idx === n - 1) ? s[idx][0].slice(5) : s[idx][0].slice(0, 7);
      o.push('<text x="' + lx.toFixed(1) + '" y="' + (h - 6) + '" fill="' + TICK +
             '" font-size="10" text-anchor="' + anchor + '">' + lab + '</text>');
    });

    // 悬停层
    o.push('<line class="ha-hline" x1="0" y1="' + padT + '" x2="0" y2="' + (padT + ph) +
           '" stroke="#c3ccd6" stroke-dasharray="3 3" opacity="0"/>');
    o.push('<circle class="ha-hdot" r="3.4" fill="' + LINE + '" stroke="#fff" stroke-width="1.4" opacity="0"/>');
    o.push('<rect class="ha-hit" x="' + padL + '" y="' + padT + '" width="' + pw +
           '" height="' + ph + '" fill="transparent"/>');
    o.push('</svg>');
    box.innerHTML = o.join('');

    c.svg = box.querySelector('svg');
    c.geom = { w: w, h: h, padL: padL, padB: padB, padT: padT, ph: ph, n: n, X: X, Y: Y, ax: ax };
    bindHover(c);
    syncHeader(c);
  }

  function syncHeader(c) {
    var d = store[c.key];
    if (!d) return;
    var s = d.series, n = s.length;
    var last = s[n - 1][1];
    var prev = n > 1 ? s[n - 2][1] : null;
    var vEl = c.el.querySelector('[data-ha-latest]');
    var cEl = c.el.querySelector('[data-ha-chg]');
    var sEl = c.el.querySelector('[data-ha-sub]');
    if (vEl) {
      vEl.textContent = fmtPct(last);
      vEl.className = 'hachart-val ' + (last > 0 ? 'up' : (last < 0 ? 'down' : ''));
    }
    if (cEl) {
      if (prev == null) { cEl.textContent = ''; }
      else {
        var dp = last - prev;
        cEl.textContent = '较上日 ' + (dp > 0 ? '+' : '') + dp.toFixed(2) + 'pp';
        cEl.className = 'hachart-chg ' + (dp > 0 ? 'up' : (dp < 0 ? 'down' : ''));
      }
    }
    if (sEl) {
      var lo = Math.min.apply(null, s.map(function (r) { return r[1]; }));
      var hi = Math.max.apply(null, s.map(function (r) { return r[1]; }));
      sEl.textContent = s[0][0] + ' ~ ' + s[n - 1][0] + ' · ' + n + ' 个交易日 · 区间 ' +
        fmtPct(lo, 1) + ' ~ ' + fmtPct(hi, 1) + (s[n - 1][2] ? ' · 含盘中' : '');
    }
  }

  function bindHover(c) {
    var svg = c.svg, g = c.geom;
    if (!svg || !g) return;
    var hit = svg.querySelector('.ha-hit');
    var hl = svg.querySelector('.ha-hline');
    var hd = svg.querySelector('.ha-hdot');
    var tip = c.el.querySelector('.ha-tip');
    if (!hit || !tip) return;

    function move(e) {
      var r = svg.getBoundingClientRect();
      var x = (e.clientX != null ? e.clientX : e.touches[0].clientX) - r.left;
      var i = Math.round((x - g.padL) / ((g.w - g.padL - 14) / Math.max(1, g.n - 1)));
      i = Math.max(0, Math.min(g.n - 1, i));
      var d = store[c.key], p = d.series[i];
      var px = g.X(i), py = g.Y(p[1]);
      hl.setAttribute('x1', px); hl.setAttribute('x2', px); hl.setAttribute('opacity', '.9');
      hd.setAttribute('cx', px); hd.setAttribute('cy', py); hd.setAttribute('opacity', '1');
      tip.style.display = 'block';
      tip.textContent = p[0] + '  ' + fmtPct(p[1]) + (p[2] ? '（盘中）' : '');
      var left = Math.max(4, Math.min(g.w - 4, px + 8));
      tip.style.left = left + 'px';
      tip.style.top = Math.max(0, py - 30) + 'px';
      tip.style.transform = (px + 140 > g.w) ? 'translateX(-100%)' : 'none';
    }
    function out() {
      hl.setAttribute('opacity', '0'); hd.setAttribute('opacity', '0');
      tip.style.display = 'none';
    }
    hit.addEventListener('mousemove', move);
    hit.addEventListener('mouseleave', out);
    hit.addEventListener('touchstart', move, { passive: true });
    hit.addEventListener('touchmove', move, { passive: true });
    hit.addEventListener('touchend', out);
  }

  /* ---------------- 实时联动 ---------------- */
  function applyLive(key, pct, dateStr) {
    var d = store[key];
    if (!d || typeof pct !== 'number' || !isFinite(pct)) return false;
    var s = d.series, last = s[s.length - 1];
    var v = Math.round(pct * 100) / 100;
    if (last[0] === dateStr) {
      // 已在当日：只更新数值，保留原有「盘中」标记
      last[1] = v;
    } else if (last[0] < dateStr) {
      if (isWeekend()) {
        // 周末行情仍是上周五收盘（仅汇率微动），按收盘重算末点，不新增点
        last[1] = v;
      } else {
        s.push([dateStr, v, 1]);   // 工作日新增盘中点
      }
    } else {
      return false;   // 历史日期，忽略
    }
    d.updated = s[s.length - 1][0];
    return true;
  }

  function onQuoteUpdated(e) {
    var det = e && e.detail;
    if (!det || !det.bar || !det.data) return;
    var code = (det.bar.getAttribute('data-a-code') || '').replace(/\D/g, '');
    if (!code || typeof det.data.premium !== 'number') return;
    if (!applyLive(code, det.data.premium * 100, todayStr())) return;
    charts.forEach(function (c) { if (c.key === code) render(c); });
  }

  /* ---------------- 初始化 ---------------- */
  function init() {
    store = loadStore();
    charts = [];
    var els = document.querySelectorAll('.hachart[data-ha-key]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var key = el.getAttribute('data-ha-key');
      if (!store[key]) { el.style.display = 'none'; continue; }
      var box = el.querySelector('.ha-svg');
      if (!box) {
        var body = el.querySelector('.hachart-body') || document.createElement('div');
        if (!body.className) body.className = 'hachart-body';
        if (!body.querySelector('.ha-tip')) {
          var tip = document.createElement('div');
          tip.className = 'ha-tip';
          body.appendChild(tip);
        }
        box = document.createElement('div');
        box.className = 'ha-svg';
        body.appendChild(box);
        el.appendChild(body);
      }
      var c = { el: el, svgWrap: box, key: key };
      charts.push(c);
      render(c);
    }

    // 页面加载时若行情已先到（quote-live 自动刷新早于本脚本 init），补一次
    document.querySelectorAll('.quotebar').forEach(function (bar) {
      if (bar._quoteData) onQuoteUpdated({ detail: { bar: bar, data: bar._quoteData } });
    });

    document.addEventListener('quote:updated', onQuoteUpdated);

    var t = null;
    window.addEventListener('resize', function () {
      clearTimeout(t);
      t = setTimeout(function () { charts.forEach(render); }, 150);
    });
  }

  window.HaPremium = { init: init, applyLive: applyLive, store: function () { return store; } };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
