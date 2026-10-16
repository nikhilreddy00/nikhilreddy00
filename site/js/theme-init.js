// Runs before first paint (kept out of index.html so the CSP needs no inline script).

// Refuse to render inside another site's frame (GitHub Pages can't send
// X-Frame-Options or frame-ancestors headers, so this is the fallback).
if (window.top !== window.self) {
  document.documentElement.style.display = "none";
  try { window.top.location.replace(window.self.location.href); } catch (e) { /* cross-origin top: stay hidden */ }
}

// Apply a saved theme.
try { const t = localStorage.getItem("theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; } catch (e) { /* storage blocked */ }
