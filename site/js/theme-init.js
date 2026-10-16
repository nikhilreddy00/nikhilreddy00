// Apply a saved theme before first paint (kept out of index.html so the CSP needs no inline script).
try { const t = localStorage.getItem("theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; } catch (e) { /* storage blocked */ }
