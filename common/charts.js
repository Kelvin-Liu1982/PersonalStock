/*
 * common/charts.js — 业绩追踪看板通用图表/弹窗前端模块
 * ------------------------------------------------------------------
 * 由 Phase 1 重构抽取自 5 个看板的重复 JS：
 *   - 迷你 sparkline 渲染（原 sparkMini / spark 两份近似实现合并为 renderSparkline）
 *   - 趋势图模态框生命周期（open / close / Esc / 遮罩点击 / [data-close] / 可选 季·年 切换）
 *   - cosco 内联 SVG 注入（data-img → __CHARTS__）
 *   - cosco 指标名频率自动追加（__FREQ__）
 *
 * 设计原则：
 *   - 纯前端、无依赖、无构建步骤；通过 <script src> 引入即可（defer 亦可，见各看板接线说明）。
 *   - 暴露全局 CommonCharts；同时为兼容既有 HTML 内联 onclick（closeChart / closeTrendModal）也挂载同名全局函数。
 *   - 不直接写死任何看板的 DOM id；选择器由调用方在 init 时传入，保证子项目隔离。
 *
 * 历史（看板内原实现差异，已统一）：
 *   - mobile/telecom 的 sparkMini 以 min>=0 时归零为基线（与年度 SVG 一致）；
 *   - unicom 的 sparkMini 未归零、cosco 的 spark 也未归零；统一为 renderSparkline(opts.baselineZero)，
 *     默认值：sparkMini=true（与 mobile/telecom 一致），spark=false（与 cosco 原行为一致）。
 */
(function (global) {
  'use strict';

  // ===================== 1) 迷你 sparkline =====================
  // box: DOM 元素；values: 数值数组；color: 描边色；opts: {baselineZero,W,H,pad}
  function renderSparkline(box, values, color, opts) {
    opts = opts || {};
    color = color || '#c8102e';
    if (!box) return;
    var pts = (values || []).map(function (v) { return Number(v); })
      .filter(function (v) { return !isNaN(v); });
    if (!pts.length) { box.innerHTML = ''; return; }
    var min = Math.min.apply(null, pts), max = Math.max.apply(null, pts);
    if (opts.baselineZero && min >= 0) { min = 0; } // 与年度 SVG 的 0 基准一致，避免小波动被过度放大
    if (min === max) { var d = Math.abs(max) || 1; min -= d * 0.15; max += d * 0.15; }
    var W = opts.W || 100, H = opts.H || 24, pad = opts.pad || 3, n = pts.length;
    var X = function (i) { return n <= 1 ? W / 2 : pad + i * (W - 2 * pad) / (n - 1); };
    var Y = function (v) { return pad + (1 - (v - min) / (max - min)) * (H - 2 * pad); };
    var line = '';
    pts.forEach(function (v, i) { line += (i ? 'L' : 'M') + X(i).toFixed(2) + ' ' + Y(v).toFixed(2) + ' '; });
    var area = 'M' + X(0).toFixed(2) + ' ' + H + ' ' + line.replace('M', 'L') +
      'L' + X(n - 1).toFixed(2) + ' ' + H + ' Z';
    box.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" width="100%" height="100%">' +
      '<path d="' + area + '" fill="' + color + '" fill-opacity="0.12"/>' +
      '<path d="' + line + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>' +
      '</svg>';
  }
  // 按 id 取元素渲染（mobile/telecom/unicom 用法）：默认 0 基线
  function sparkMini(id, values, color) {
    renderSparkline(document.getElementById(id), values, color, { baselineZero: true });
  }
  // 按元素渲染（cosco 用法）：不归零，与原 spark(el,data,color) 行为一致
  function spark(el, data, color) {
    renderSparkline(el, data, color, { baselineZero: false });
  }

  // ===================== 2) 通用趋势图模态框 =====================
  // cfg: {
  //   modal:   选择器或元素（模态根）
  //   openClass: 打开时加到 modal 的 class，默认 'open'
  //   body:    内容容器选择器或元素（注入 innerHTML / img 的外层 div）
  //   img:     <img> 选择器或元素（coal 模式：直接设 src）
  //   title:   标题元素选择器或元素
  //   periodToggle: 季/年 切换容器选择器或元素（含 .pt[data-period] 子按钮）；缺省不启用
  //   defaultPeriod: 'q' | 'y'，默认 'q'
  //   closeSel: 关闭触发器选择器，默认 '[data-close]'
  //   render:  可选自定义渲染 fn(ctx, payload, period)，ctx={modal,body,img,title}
  // }
  function createTrendModal(cfg) {
    cfg = cfg || {};
    // 延迟解析 DOM：看板常在 <script> 之后才定义模态框，故 open() 时再 querySelector。
    var modalSel = cfg.modal, bodySel = cfg.body, imgSel = cfg.img, titleSel = cfg.title, periodSel = cfg.periodToggle;
    var openClass = cfg.openClass || 'open';
    var closeSel = cfg.closeSel || '[data-close]';
    var defaultPeriod = cfg.defaultPeriod || 'q';
    var _modal = null, _body = null, _img = null, _title = null, _period = null, _attached = false;
    var curPeriod = defaultPeriod;
    var lastPayload = null;

    function isInlineSvg(s) { return typeof s === 'string' && s.trim().indexOf('<svg') === 0; }

    function resolve() {
      if (_modal) return _modal;
      _modal = typeof modalSel === 'string' ? document.querySelector(modalSel) : modalSel;
      if (!_modal) return null;
      _body = bodySel ? (typeof bodySel === 'string' ? _modal.querySelector(bodySel) : bodySel) : null;
      _img = imgSel ? (typeof imgSel === 'string' ? _modal.querySelector(imgSel) : imgSel) : null;
      _title = titleSel ? (typeof titleSel === 'string' ? _modal.querySelector(titleSel) : titleSel) : null;
      _period = periodSel ? (typeof periodSel === 'string' ? _modal.querySelector(periodSel) : periodSel) : null;
      if (!_attached) {
        _attached = true;
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
        _modal.addEventListener('click', function (e) {
          if (e.target === _modal || (closeSel && e.target.closest && e.target.closest(closeSel))) close();
        });
        if (_period) {
          _period.querySelectorAll('.pt').forEach(function (b) {
            b.addEventListener('click', function () {
              curPeriod = b.dataset.period;
              _period.querySelectorAll('.pt').forEach(function (x) { x.classList.toggle('active', x === b); });
              render(lastPayload, curPeriod);
            });
          });
        }
      }
      return _modal;
    }

    function render(payload, period) {
      if (typeof cfg.render === 'function') {
        cfg.render({ modal: _modal, body: _body, img: _img, title: _title }, payload, period);
        return;
      }
      // 默认：payload 为内联 SVG 字符串或图片地址
      if (_body) {
        _body.innerHTML = isInlineSvg(payload) ? payload : '<img src="' + payload + '" alt="趋势图">';
      } else if (_img) {
        _img.src = payload;
      }
    }

    function open(payload) {
      if (!resolve()) { console.warn('[CommonCharts] createTrendModal.open: modal 未找到', modalSel); return; }
      curPeriod = defaultPeriod;
      if (_period && payload && payload.q && payload.y && !payload.single) {
        _period.style.display = cfg.periodShowDisplay || 'inline-flex';
        _period.querySelectorAll('.pt').forEach(function (b) {
          b.classList.toggle('active', b.dataset.period === curPeriod);
        });
      } else if (_period) {
        _period.style.display = 'none';
      }
      render(payload, curPeriod);
      _modal.classList.add(openClass);
    }
    function close() { if (_modal) _modal.classList.remove(openClass); }

    return {
      el: function () { return resolve(); },
      open: function (payload) { lastPayload = payload; open(payload); },
      close: close
    };
  }

  // ===================== 3) cosco 内联 SVG 注入 =====================
  // 把 __CHARTS__[id]（内联 SVG 字符串或图片地址）注入到所有 [data-img="id"] 容器
  function injectCharts(selector, chartsObj) {
    var nodes = document.querySelectorAll(selector || '[data-img]');
    nodes.forEach(function (node) {
      var id = node.getAttribute('data-img');
      var c = chartsObj[id];
      if (!c) return;
      node.innerHTML = (typeof c === 'string' && c.trim().indexOf('<svg') === 0)
        ? c : '<img src="' + c + '" alt="' + id + '">';
    });
  }

  // ===================== 4) cosco 指标名频率自动追加 =====================
  // 读取 __FREQ__（{chartId: "周"|"月"|"季"|"年"}），给 .metric .k 追加 (频率)；
  // 仅当该指标含 openChart('chartId') 按钮且频率已知时追加，避免误伤无图指标。
  function appendFreq(opts) {
    opts = opts || {};
    var freqObj = opts.freq && typeof opts.freq !== 'undefined' ? opts.freq : (typeof __FREQ__ !== 'undefined' ? __FREQ__ : null);
    if (!freqObj) return;
    var metricSel = opts.metricSel || '.metric';
    var keySel = opts.keySel || '.k';
    var btnSel = opts.btnSel || '.tbtn[onclick^="openChart"]';
    document.querySelectorAll(metricSel).forEach(function (m) {
      var k = m.querySelector(keySel);
      if (!k) return;
      var btn = m.querySelector(btnSel);
      var f = null;
      if (btn) {
        var mm = (btn.getAttribute('onclick') || '').match(/openChart\('([^']+)'/);
        if (mm) f = freqObj[mm[1]];
      }
      if (!f) return;
      var t = k.textContent
        .replace(/[（(][^）)]*(最新|截至|年内)[^）)]*[）)]/g, '')
        .replace(/[（(]\d{4}[）)]/g, '')
        .replace(/[（(][周月季年][）)]/g, '')
        .trim();
      k.textContent = t + '(' + f + ')';
    });
  }

  // ===================== 导出 =====================
  var API = {
    renderSparkline: renderSparkline,
    sparkMini: sparkMini,
    spark: spark,
    createTrendModal: createTrendModal,
    injectCharts: injectCharts,
    appendFreq: appendFreq
  };
  global.CommonCharts = API;
  // 兼容既有看板：原先各看板内联定义了 sparkMini / spark 作为全局函数，
  // 抽取到 common 后仍需保留全局名，避免逐个改写 sparkMini('id',...) 调用点。
  global.sparkMini = sparkMini;
  global.spark = spark;
  if (typeof module !== 'undefined' && module.exports) module.exports = API; // 便于 node 单元测试
  return API;
})(typeof window !== 'undefined' ? window : this);
