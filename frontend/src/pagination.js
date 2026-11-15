import { esc } from "./ui.js";
export function renderPagination(element, data, sizes, onChange) {
  const { page, pages, page_size: size, total } = data;
  const focus = element.contains(document.activeElement)
    ? document.activeElement.dataset.pageAction
    : null;
  element.innerHTML = `<span class="page-summary">${total ? (page - 1) * size + 1 : 0}–${Math.min(page * size, total)} / ${total}</span><div class="page-controls"><label>每页 <select data-page-action="size" aria-label="每页显示数量">${sizes.map((n) => `<option value="${n}" ${n === size ? "selected" : ""}>${n}</option>`).join("")}</select></label><button class="secondary" data-page-action="prev" ${page <= 1 ? "disabled" : ""} aria-label="上一页">← 上一页</button><label>第 <select data-page-action="page" aria-label="跳转到页码">${Array.from({ length: pages }, (_, i) => `<option value="${i + 1}" ${i + 1 === page ? "selected" : ""}>${i + 1}</option>`).join("")}</select> / ${pages} 页</label><button class="secondary" data-page-action="next" ${page >= pages ? "disabled" : ""} aria-label="下一页">下一页 →</button></div>`;
  element.querySelector('[data-page-action="prev"]').onclick = () =>
    onChange(page - 1, size);
  element.querySelector('[data-page-action="next"]').onclick = () =>
    onChange(page + 1, size);
  element.querySelector('[data-page-action="page"]').onchange = (e) =>
    onChange(Number(e.target.value), size);
  element.querySelector('[data-page-action="size"]').onchange = (e) =>
    onChange(1, Number(e.target.value));
  if (focus)
    element
      .querySelector(`[data-page-action="${esc(focus)}"]`)
      ?.focus({ preventScroll: true });
}
