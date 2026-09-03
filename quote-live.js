/**
 * quote-live.js — 行情快照条「实时行情」通用前端
 * ------------------------------------------------------------------
 * 用法（看板页 <head>）：
 *   <script src="../quote-live.js" defer></script>
 * 并在 .quotebar 上声明代码：
 *   <div class="quotebar" data-a-code="sh601919" data-h-code="hk01919">
 *
 * 可选属性：
 *   data-quote-api="/api/quote"   接口地址，默认 /api/quote
 *   data-quote-autoload="0"       关闭页面加载自动刷新（默认开启）
 *
 * 机制：
 *   1) 按 .qg-title 判断分组（A股 / H股），按 .ql 标签文字匹配字段
 *   2) 页面加载自动拉一次（失败静默，保留静态快照）
 *   3) 点「刷新行情」再拉一次，成功写入数值 + 时间戳，失败提示错误
 * ------------------------------------------------------------------
 */

(function () {
  'use strict';

  /* ---------------- 标签 → 字段 ---------------- */
  // key: 标签文字（去空格）；value: [数据路径, 格式化器, 是否按涨跌着色]
  var FIELD_MAP = {
    'A': {
      '最新价':   ['price',     'price',   true],
      '涨跌幅':   ['pct',       'pct',     true],
      '涨跌额':   ['change',    'chg',     true],
      '昨收':     ['prevClose', 'price',   false],
      '今开':     ['open',      'price',   false],
      '最高':     ['high',      'price',   false],
      '最低':     ['low',       'price',   false],
      '成交额':   ['amount',    'amount',  false],
      '动态PE':   ['peDyn',     'ratio',   false],
      '市盈率':   ['peDyn',     'ratio',   false],
      '市净率':   ['pb',        'ratio',   false],
      '总市值':   ['totalCap',  'yi',      false],
    },
    'H': {
      '最新价':    ['price',    'price',   true],
      '涨跌幅':    ['pct',      'pct',     true],
      '涨跌额':    ['change',   'chg',     true],
      '昨收':      ['prevClose','price',   false],
      '今开':      ['open',     'price',   false],
      '最高':      ['high',     'price',   false],
      '最低':      ['low',      'price',   false],
      '成交额':    ['amount',   'amount',  false],
      '动态PE':    ['peDyn',    'ratio',   false],
      '市盈率':    ['peDyn',    'ratio',   false],
      '市净率':    ['pb',       'ratio',   false],
      '股息率TTM': ['divYield', 'pct2',    false],
      '股息率':    ['divYield', 'pct2',    false],
      '溢价(H/A)': ['__premium__','pctFrac', true],
      'AH溢价':    ['__premium__','pctFrac', true],
      '总市值':    ['totalCap', 'yi',      false],
    },
  };

  /* ---------------- 格式化 ---------------- */
  function isNum(v) { return typeof v === 'number' && isFinite(v); }

  var FMT = {
    price: function (v) { return isNum(v) ? v.toFixed(2) : '—'; },
    chg:   function (v) { return isNum(v) ? (v > 0 ? '+' : '') + v.toFixed(2) : '—'; },
    pct:   function (v) { return isNum(v) ? (v > 0 ? '+' : '') + v.toFixed(2) + '%' : '—'; },
    pct2:  function (v) { return isNum(v) ? v.toFixed(2) + '%' : '—'; },
    // 溢价：Worker 返回的是小数比例（如 -0.3244），需 ×100
    pctFrac: function (v) { return isNum(v) ? (v > 0 ? '+' : '') + (v * 100).toFixed(2) + '%' : '—'; },
    ratio: function (v) { return isNum(v) ? v.toFixed(2) : '—'; },
    // 成交额：Worker 已统一为「元」
    amount: function (v) {
      if (!isNum(v)) return '—';
      if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿';
      if (v >= 1e4) return (v / 1e4).toFixed(2) + '万';
      return v.toFixed(0);
    },
    // 市值：上游单位「亿元」
    yi:    function (v) {
      if (!isNum(v)) return '—';
      if (v >= 10000) return (v / 10000).toFixed(2) + '万亿';
      return v.toFixed(0) + '亿';
    },
  };

  function pick(data, group, key) {
    if (key === '__premium__') return data.premium;
    var leg = group === 'H' ? data.h : data.a;
    return leg ? leg[key] : undefined;
  }

  /* ---------------- 渲染 ---------------- */
  function paint(bar, data) {
    var groups = bar.querySelectorAll('.qgroup');
    for (var g = 0; g < groups.length; g++) {
      var titleEl = groups[g].querySelector('.qg-title');
      var title = titleEl ? (titleEl.textContent || '').trim() : '';
      var group = title.indexOf('H') === 0 ? 'H' : 'A';
      var map = FIELD_MAP[group] || {};

      var items = groups[g].querySelectorAll('.qitem');
      for (var i = 0; i < items.length; i++) {
        var item = items[i];
        var lab = item.querySelector('.ql');
        var val = item.querySelector('.qv');
        if (!lab || !val) continue;

        var spec = map[(lab.textContent || '').trim()];
        if (!spec) continue;

        var raw = pick(data, group, spec[0]);
        if (raw === undefined || raw === null) continue;

        var text = FMT[spec[1]](raw);
        if (text === '—') continue;

        // 保留原有的 <small>港元</small> 之类的后缀
        var small = val.querySelector('small');
        val.innerHTML = text + (small ? small.outerHTML : '');

        // 着色
        val.classList.remove('up', 'down', 'flat');
        if (spec[2] && isNum(raw)) {
          val.classList.add(raw > 0 ? 'up' : (raw < 0 ? 'down' : 'flat'));
        }
      }
    }

    // 时间戳
    var dateEl = bar.querySelector('.qdate');
    if (dateEl) {
      var d = new Date();
      var p = function (n) { return String(n).padStart(2, '0'); };
      dateEl.textContent =
        '实时行情 ' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' +
        p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds()) +
        '（腾讯行情 + 新浪汇率）';
      dateEl.classList.remove('qdate-off');
    }
    bar.setAttribute('data-quote-state', 'live');
  }

  /* ---------------- 拉取 ---------------- */
  function fetchQuote(bar) {
    var a = bar.getAttribute('data-a-code') || '';
    var h = bar.getAttribute('data-h-code') || '';
    var api = bar.getAttribute('data-quote-api') || '/api/quote';
    if (!a && !h) return Promise.reject(new Error('未配置 data-a-code / data-h-code'));

    var qs = [];
    if (a) qs.push('a=' + encodeURIComponent(a));
    if (h) qs.push('h=' + encodeURIComponent(h));

    return fetch(api + '?' + qs.join('&'), { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (o) {
        if (!o || !o.ok) throw new Error((o && o.error) || '接口返回失败');
        return o;
      });
  }

  /* ---------------- 单个看板接线 ---------------- */
  function wire(bar) {
    if (bar.getAttribute('data-quote-wired') === '1') return;
    bar.setAttribute('data-quote-wired', '1');

    // 用事件委托绑定：行情条由脚本异步渲染时也能生效
    bar.addEventListener('click', function (e) {
      var btn = e.target && e.target.closest ? e.target.closest('.qrefresh') : null;
      if (!btn || !bar.contains(btn)) return;
      e.preventDefault();
      refresh(btn, false).catch(function () {});
    });

    // 页面加载自动拉一次（失败静默，保留静态快照）
    if (bar.getAttribute('data-quote-autoload') !== '0') {
      refresh(null, true).catch(function () {});
    }

    function ui() {
      var btn = bar.querySelector('.qrefresh') || document.getElementById('qRefreshBtn');
      return {
        btn: btn,
        msg: bar.querySelector('.qmsg') || document.getElementById('qRefreshMsg'),
        spinner: btn ? btn.querySelector('.spinner') : null,
        label: btn ? btn.querySelector('.lbl') : null,
      };
    }

    function setLoading(on) {
      var u = ui();
      if (!u.btn) return;
      u.btn.disabled = on;
      if (u.spinner) u.spinner.classList.toggle('hidden', !on);
      if (u.label && on) u.label.textContent = '刷新中…';
    }

    function refresh(btn, silent) {
      if (!silent) {
        setLoading(true);
        var m0 = ui().msg;
        if (m0) { m0.className = 'qmsg'; m0.textContent = ''; }
      }
      return fetchQuote(bar)
        .then(function (data) {
          paint(bar, data);
          if (!silent) {
            var d = new Date();
            var p = function (n) { return String(n).padStart(2, '0'); };
            var u = ui();
            if (u.msg) {
              u.msg.className = 'qmsg ok';
              u.msg.textContent = '✓ 已更新 ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
            }
            if (u.label) u.label.textContent = '刷新行情';
          }
          return data;
        })
        .catch(function (err) {
          if (!silent) {
            var u = ui();
            if (u.msg) {
              u.msg.className = 'qmsg err';
              u.msg.textContent = '✗ ' + (err && err.message ? err.message : err);
            }
            if (u.label) u.label.textContent = '重试';
          }
          throw err;
        })
        .finally(function () {
          if (!silent) setLoading(false);
        });
    }
  }

  /* ---------------- 入口 ---------------- */
  function init() {
    var bars = document.querySelectorAll('.quotebar[data-a-code], .quotebar[data-h-code]');
    for (var i = 0; i < bars.length; i++) wire(bars[i]);
  }

  window.QuoteLive = { init: init, refresh: fetchQuote };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
