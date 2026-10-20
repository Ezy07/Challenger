/* 라이트 · 다크 전환. 다크는 기존 화면 그대로 두고, 라이트만 data-mode 로 덮는다. */
(function () {
  const KEY = "safety.mode";

  function savedMode() {
    try { return localStorage.getItem(KEY) === "light" ? "light" : "dark"; } catch (e) { return "dark"; }
  }

  function applyMode(mode, save) {
    const light = mode === "light";
    if (light) document.documentElement.dataset.mode = "light";
    else delete document.documentElement.dataset.mode;
    if (save) {
      try { localStorage.setItem(KEY, light ? "light" : "dark"); } catch (e) { /* 저장을 못 해도 이번 화면은 바뀜 */ }
    }
    paintModeButton();
  }

  function paintModeButton() {
    const box = document.getElementById("mode-change");
    if (!box) return;
    const light = document.documentElement.dataset.mode === "light";
    box.querySelectorAll("[data-mode-set]").forEach((btn) => {
      const on = btn.dataset.modeSet === (light ? "light" : "dark");
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function mountModeChange() {
    paintModeButton();
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("#mode-change [data-mode-set]");
    if (!btn) return;
    e.preventDefault();
    applyMode(btn.dataset.modeSet, true);
  });

  if (!document.querySelector('link[href="mode_change.css"]')) {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    const base = document.currentScript && document.currentScript.src;
    css.href = base ? new URL("mode_change.css", base).href : "mode_change.css";
    document.head.appendChild(css);
  }

  window.mountModeChange = mountModeChange;
  applyMode(savedMode(), false);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", paintModeButton);
  else paintModeButton();
})();
