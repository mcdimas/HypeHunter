/* Apply before paint; theme is a browser preference, available before login. */
function currentTheme() { return document.documentElement.dataset.theme || "dark"; }
function setTheme(theme) {
  theme = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#f7f7fb" : "#0d0e12");
  try { localStorage.setItem("hype-theme", theme); } catch {}
}
try { setTheme(localStorage.getItem("hype-theme")); } catch { setTheme("dark"); }
document.addEventListener("click", event => {
  const button = event.target.closest("[data-theme]");
  if (!button) return;
  setTheme(button.dataset.theme === "toggle" ? (currentTheme() === "dark" ? "light" : "dark") : button.dataset.theme);
  document.querySelectorAll("[data-theme]").forEach(el => {
    if (el.dataset.theme === "toggle") {
      el.setAttribute("aria-label", currentTheme() === "dark" ? "Включить светлую тему" : "Включить тёмную тему");
      el.title = el.getAttribute("aria-label");
    } else el.setAttribute("aria-pressed", String(el.dataset.theme === currentTheme()));
  });
});
window.addEventListener("storage", event => { if (event.key === "hype-theme") setTheme(event.newValue); });
