/* 卡片模块：统一渲染一级导航页的标的卡片
 * 同一行业（category）共享背景色，由 category.css 的 --ind-* 变量驱动。
 * 用法：在 HTML 中放一个容器（如 <div id="stockGrid" class="actions"></div>），
 *      本模块读取 #stockGrid 的 data-cards JSON 并渲染。
 */
(function () {
  "use strict";

  // 行业 → CSS 变量名（与 category.css 对应）
  var INDUSTRY_VAR = {
    telecom: "var(--ind-telecom)",
    coal: "var(--ind-coal)",
    shipping: "var(--ind-shipping)",
    internet: "var(--ind-internet)",
    oil: "var(--ind-oil)",
    consumer: "var(--ind-consumer)",
    finance: "var(--ind-finance)",
    power: "var(--ind-power)",
    machinery: "var(--ind-machinery)",
    logistics: "var(--ind-logistics)",
    rail: "var(--ind-rail)"
  };

  function buildCard(cfg) {
    var card = document.createElement("div");
    card.className = "stock-card";
    if (cfg.category && INDUSTRY_VAR[cfg.category]) {
      card.style.setProperty("--cat", INDUSTRY_VAR[cfg.category]);
    }

    if (cfg.categoryLabel) {
      var tag = document.createElement("span");
      tag.className = "cat-tag";
      tag.textContent = cfg.categoryLabel;
      card.appendChild(tag);
    }

    var name = document.createElement("span");
    name.className = "name";
    name.textContent = cfg.name;
    card.appendChild(name);

    var code = document.createElement("span");
    code.className = "code";
    code.textContent = cfg.code || "";
    card.appendChild(code);

    if (cfg.links && cfg.links.length) {
      var links = document.createElement("div");
      links.className = "links";
      cfg.links.forEach(function (l) {
        if (l.menu) {
          links.appendChild(buildReportMenu(l));
        } else {
          var a = document.createElement("a");
          a.href = l.href;
          a.textContent = l.text;
          if (l.title) a.title = l.title;
          links.appendChild(a);
        }
      });
      card.appendChild(links);
    }
    return card;
  }

  // 「财报分析」下拉：列出同一标的的多份财报分析 HTML
  function buildReportMenu(cfg) {
    var wrap = document.createElement("div");
    wrap.className = "report-menu";

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "rm-btn";
    btn.textContent = cfg.text;

    var list = document.createElement("div");
    list.className = "rm-list";

    (cfg.reports || []).forEach(function (r) {
      var a = document.createElement("a");
      a.href = r.href;
      a.textContent = r.label;
      if (r.title) a.title = r.title;
      list.appendChild(a);
    });

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = wrap.classList.toggle("open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      // 让当前卡片整体上浮，避免下拉列表被下面的卡片压住
      var card = wrap.closest(".stock-card");
      if (card) card.classList.toggle("menu-open", open);
    });

    wrap.appendChild(btn);
    wrap.appendChild(list);
    return wrap;
  }

  function render(grid) {
    var raw = grid.getAttribute("data-cards");
    if (!raw) return;
    var cards;
    try {
      cards = JSON.parse(raw);
    } catch (e) {
      console.error("卡片数据解析失败：", e);
      return;
    }
    cards.forEach(function (cfg) {
      grid.appendChild(buildCard(cfg));
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var grids = document.querySelectorAll("#stockGrid");
    Array.prototype.forEach.call(grids, render);

    // 点页面其它地方关闭所有下拉
    document.addEventListener("click", function () {
      var openMenus = document.querySelectorAll(".report-menu.open");
      Array.prototype.forEach.call(openMenus, function (m) {
        m.classList.remove("open");
        var btn = m.querySelector(".rm-btn");
        if (btn) btn.setAttribute("aria-expanded", "false");
        var card = m.closest(".stock-card");
        if (card) card.classList.remove("menu-open");
      });
    });
  });
})();
