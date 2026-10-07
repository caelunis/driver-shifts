// Applies the saved theme before first paint, so the page never flashes the wrong one.
// A separate file rather than an inline script: the CSP allows scripts only from 'self'.
try {
  var t = localStorage.getItem("theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch (e) {}
