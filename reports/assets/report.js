"use strict";

(() => {
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const navigation = Array.from(document.querySelectorAll(".nav-link"));
  const sections = Array.from(document.querySelectorAll(".report-section"));
  const topButton = document.getElementById("back-to-top");

  if (window.lucide) {
    window.lucide.createIcons({ attrs: { "aria-hidden": "true", focusable: "false" } });
  }

  const activateTab = (selectedTab, moveFocus = false) => {
    tabs.forEach((tab) => {
      const selected = tab === selectedTab;
      tab.classList.toggle("active", selected);
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      const panel = document.getElementById(tab.getAttribute("aria-controls"));
      if (panel) panel.hidden = !selected;
    });
    if (moveFocus) selectedTab.focus();
  };

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", (event) => {
      let nextIndex = index;
      if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft") nextIndex = (index + tabs.length - 1) % tabs.length;
      else if (event.key === "Home") nextIndex = 0;
      else if (event.key === "End") nextIndex = tabs.length - 1;
      else return;
      event.preventDefault();
      activateTab(tabs[nextIndex], true);
    });
  });

  const revealHashTarget = () => {
    const target = document.getElementById(window.location.hash.slice(1));
    if (target instanceof HTMLDetailsElement) target.open = true;
  };
  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", () => {
      const target = document.getElementById(link.getAttribute("href").slice(1));
      if (target instanceof HTMLDetailsElement) target.open = true;
    });
  });
  window.addEventListener("hashchange", revealHashTarget);
  revealHashTarget();

  const updateScrollState = () => {
    const offset = 100;
    let activeSection = sections[0];
    for (const section of sections) {
      if (section.getBoundingClientRect().top <= offset) activeSection = section;
    }
    navigation.forEach((link) => {
      const active = link.getAttribute("href") === `#${activeSection.id}`;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
    topButton.hidden = window.scrollY < 650;
  };
  let framePending = false;
  window.addEventListener("scroll", () => {
    if (framePending) return;
    framePending = true;
    window.requestAnimationFrame(() => {
      updateScrollState();
      framePending = false;
    });
  }, { passive: true });
  window.addEventListener("resize", updateScrollState);
  topButton.addEventListener("click", () => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reducedMotion ? "instant" : "smooth" });
  });
  updateScrollState();
})();