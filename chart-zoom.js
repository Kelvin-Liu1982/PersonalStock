/**
 * chart-zoom.js — 看板图表「双击放大」通用前端
 * ------------------------------------------------------------------
 * 用法（看板页 <head> 里引入一次即可，全页图表自动生效）：
 *   <script src="../chart-zoom.js" defer>   子目录看板（china-mobile / coal / telecom / unicom）
 *   <script src="/chart-zoom.js" defer>     根路径看板（cosco-shipping）
 *
 * 自动命中范围（事件委托，动态注入的图表同样生效）：
 *   1) [data-img]          内联 SVG 容器（cosco 看板趋势区 .imgbox，由 __CHARTS__ 注入）
 *   2) img[src$=".svg"]    <img> 引用的独立 SVG 文件（china-mobile / coal / telecom）
 *   3) [data-zoom]         任何其他结构：在容器上显式加 data-zoom 即可
 *
 * 关闭方式：点遮罩 / 点右上角 × / 按 Esc
 * 排除：元素自身或祖先带 data-nozoom（例如不希望放大的小图、图标）；
 *       所有 sparkline（.spark / .spark-mini，及其内部的 img/svg）一律不放大、
 *       也不加「双击放大」提示——sparkline 只是缩略展示，无任何其它功能。
 *
 * 可选：在命中元素上加 data-title="XXX"，放大层顶部会显示该标题；
 *       未指定时，img 取 alt、figure 取 figcaption 作为标题。
 * ------------------------------------------------------------------
 */

(function () {
  'use strict';

  var OVERLAY_ID = 'cz-overlay';
  var CSS_ID = 'cz-style';

  /* ---------------- 注入样式（只注入一次） ---------------- */
  function injectCSS() {
    if (document.getElementById(CSS_ID)) return;
    var css =
      '.cz-overlay{position:fixed;inset:0;background:rgba(15,23,42,.72);z-index:99999;' +
      'display:flex;align-items:center;justify-content:center;padding:28px;cursor:zoom-out}' +
      '.cz-box{position:relative;background:#fff;border-radius:12px;padding:16px 18px;' +
      'max-width:96vw;max-height:94vh;overflow:auto;cursor:default;' +
      'box-shadow:0 18px 50px rgba(0,0,0,.35)}' +
      '.cz-close{position:absolute;top:6px;right:14px;font-size:26px;line-height:1;' +
      'color:#64748b;cursor:pointer;z-index:2;user-select:none}' +
      '.cz-close:hover{color:#0f172a}' +
      '.cz-cap{font-size:12.5px;color:#475569;font-weight:600;margin:0 26px 10px 2px}' +
      '.cz-body svg{display:block;width:min(92vw,1400px)!important;height:auto!important;' +
      'max-height:84vh!important}' +
      // 注意：<img> 引用的独立 SVG 通常只有 viewBox、没有 width/height 属性，
      // 浏览器会退回默认对象尺寸 300x150，导致放大层里反而比原图更小。
      // 因此必须给 img 一个「确定宽度」强制放大（不能用 width:auto + max-width，
      // 那只缩不放），height:auto 由 viewBox 比例推导，max-height 负责限制高度。
      '.cz-body img{display:block;width:min(92vw,1400px)!important;height:auto!important;' +
      'max-height:84vh!important;background:#fff}' +
      'body.cz-lock{overflow:hidden}';
    var st = document.createElement('style');
    st.id = CSS_ID;
    st.appendChild(document.createTextNode(css));
    document.head.appendChild(st);
  }

  /* ---------------- 从事件目标定位图表 ---------------- */
  function findChart(el) {
    if (!el || !el.closest) return null;
    // 1) <img src="*.svg">（自身即图表）
    var tag = el.tagName ? el.tagName.toLowerCase() : '';
    if (tag === 'img' && /\.svg(\?|#|$)/i.test(el.getAttribute('src') || '')) {
      return { node: el, kind: 'img' };
    }
    // 2) [data-img] 内联 SVG 容器
    var box = el.closest('[data-img]');
    if (box) return { node: box, kind: 'inline' };
    // 3) .imgbox 通用图表容器（cosco 趋势弹窗 #modal-img 等无 data-img 的容器）
    var ib = el.closest('.imgbox');
    if (ib) return { node: ib, kind: 'inline' };
    // 4) 显式 opt-in
    var z = el.closest('[data-zoom]');
    if (z) return { node: z, kind: 'inline' };
    return null;
  }

  /* 容器内是否含有可放大的图形（svg 或 img） */
  function hasGraphic(node) {
    if (node.tagName) {
      var t = node.tagName.toLowerCase();
      if (t === 'svg' || t === 'img') return true;
    }
    return !!(node.querySelector && (node.querySelector('svg') || node.querySelector('img')));
  }

  /* ---------------- 取标题 ---------------- */
  function titleOf(node, kind) {
    var t = node.getAttribute && node.getAttribute('data-title');
    if (t) return t;
    if (kind === 'img') return node.getAttribute('alt') || '';
    var fig = node.closest ? node.closest('figure') : null;
    if (fig) {
      var cap = fig.querySelector('figcaption');
      if (cap) return cap.textContent.trim();
    }
    return '';
  }

  /* ---------------- 构建放大层内容 ---------------- */
  function buildBody(node, kind) {
    var body = document.createElement('div');
    body.className = 'cz-body';
    if (kind === 'img') {
      var im = document.createElement('img');
      im.src = node.getAttribute('src');
      im.alt = node.getAttribute('alt') || '';
      body.appendChild(im);
      return body;
    }
    // 内联 SVG：克隆容器内的 svg（若容器本身就是 svg 则克隆自身）
    var tag = node.tagName ? node.tagName.toLowerCase() : '';
    if (tag === 'img') {
      // 容器本身就是 img（例如 base64 PNG 图表）
      var im0 = document.createElement('img');
      im0.src = node.getAttribute('src');
      im0.alt = node.getAttribute('alt') || '';
      body.appendChild(im0);
      return body;
    }
    var svg = tag === 'svg' ? node : node.querySelector('svg');
    if (svg) {
      var clone = svg.cloneNode(true);
      clone.removeAttribute('width');
      clone.removeAttribute('height');
      clone.removeAttribute('style');
      body.appendChild(clone);
      return body;
    }
    // 容器内是 <img>（例如 data:image/png;base64 的图表）
    var im = node.querySelector('img');
    if (im) {
      var im2 = document.createElement('img');
      im2.src = im.getAttribute('src');
      im2.alt = im.getAttribute('alt') || '';
      body.appendChild(im2);
      return body;
    }
    // 兜底：整体克隆
    var c2 = node.cloneNode(true);
    c2.removeAttribute && c2.removeAttribute('id');
    body.appendChild(c2);
    return body;
  }

  /* ---------------- 打开 / 关闭 ---------------- */
  function close() {
    var ov = document.getElementById(OVERLAY_ID);
    if (ov && ov.parentNode) ov.parentNode.removeChild(ov);
    document.body.classList.remove('cz-lock');
  }

  function open(node, kind) {
    close();
    injectCSS();

    var ov = document.createElement('div');
    ov.id = OVERLAY_ID;
    ov.className = 'cz-overlay';
    ov.setAttribute('role', 'dialog');

    var box = document.createElement('div');
    box.className = 'cz-box';

    var x = document.createElement('span');
    x.className = 'cz-close';
    x.textContent = '\u00d7';
    x.setAttribute('title', '关闭');
    box.appendChild(x);

    var title = titleOf(node, kind);
    if (title) {
      var cap = document.createElement('div');
      cap.className = 'cz-cap';
      cap.textContent = title;
      box.appendChild(cap);
    }

    box.appendChild(buildBody(node, kind));
    ov.appendChild(box);
    document.body.appendChild(ov);
    document.body.classList.add('cz-lock');

    // 点遮罩关闭（点盒子内部不关）
    ov.addEventListener('click', function (e) {
      if (e.target === ov || e.target === x) close();
    });
  }

  /* ---------------- 事件委托 ---------------- */
  document.addEventListener('dblclick', function (e) {
    var el = e.target;
    if (!el || !el.closest) return;
    // 已在放大层内 / 明确排除 → 不处理
    if (el.closest('.cz-overlay')) return;
    if (el.closest('[data-nozoom], .spark, .spark-mini')) return;

    var hit = findChart(el);
    if (!hit) return;

    // 容器里确实没有可放大的内容则忽略
    if (hit.kind === 'inline' && !hasGraphic(hit.node)) return;

    e.preventDefault();
    open(hit.node, hit.kind);
  });

  /* Esc 关闭（捕获阶段：放大层开着时只关放大层，
     不再向下传递去关掉看板自身的弹窗，例如 cosco 的「趋势」弹窗） */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' && e.key !== 'Esc') return;
    if (!document.getElementById(OVERLAY_ID)) return;
    close();
    e.preventDefault();
    if (e.stopImmediatePropagation) e.stopImmediatePropagation();
  }, true);

  /* ---------------- 可发现性：给可放大图表加 tooltip ---------------- */
  function markHints() {
    var nodes = document.querySelectorAll('[data-img], [data-zoom], img[src$=".svg"]');
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n.closest('[data-nozoom], .spark, .spark-mini')) continue;
      if (!n.getAttribute('title')) n.setAttribute('title', '双击放大');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', markHints);
  } else {
    markHints();
  }
})();
