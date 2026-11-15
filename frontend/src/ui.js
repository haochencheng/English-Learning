export const $ = (selector) => document.querySelector(selector);
export const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
let timer;
export function notify(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(timer);
  timer = setTimeout(() => ($("#toast").hidden = true), 5000);
}
export function dayKey() {
  const d = new Date();
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, "0"),
    String(d.getDate()).padStart(2, "0"),
  ].join("-");
}
export function showView(name) {
  document
    .querySelectorAll(".view")
    .forEach((v) => (v.hidden = v.id !== `view-${name}`));
  document.querySelectorAll("[data-view]").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === name);
    if (b.dataset.view === name) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  $("#breadcrumb").textContent = {
    today: "今日学习",
    library: "我的词库",
    practice: "场景练习",
    videos: "视频学习",
    plan: "学习方案",
  }[name];
  document.dispatchEvent(new CustomEvent("viewchange", { detail: name }));
  window.scrollTo({ top: 0, behavior: "instant" });
}
