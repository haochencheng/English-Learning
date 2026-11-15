import { write } from "./api.js";
import { WORDS, loadContent } from "./store.js";
import { $, notify } from "./ui.js";
import { refreshStudy } from "./study.js";
let editingId = null;
const fields = [
  "deck",
  "term",
  "pos",
  "meaning",
  "collocation",
  "example",
  "translation",
  "source_url",
  "example_kind",
  "source_label",
];
export function initEditor() {
  function open(id = null) {
    editingId = id;
    const word = WORDS.find((w) => w.id === id);
    $("#word-editor-title").textContent = id ? "编辑词条" : "新增词条";
    $("#word-archive").hidden = !id;
    fields.forEach(
      (key) =>
        ($("#word-form").elements[key].value =
          word?.[key] ||
          (key === "deck" ? "job" : key === "example_kind" ? "example" : "")),
    );
    $("#word-editor-error").textContent = "";
    $("#word-editor").showModal();
  }
  $("#word-add").onclick = () => open();
  $("#word-list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-edit]");
    if (b) open(b.dataset.edit);
  });
  $("#word-editor-close").onclick = () => $("#word-editor").close();
  $("#word-form").onsubmit = async (e) => {
    e.preventDefault();
    $("#word-submit").disabled = true;
    try {
      const data = Object.fromEntries(new FormData(e.target));

      await write(
        editingId ? "/words/" + editingId : "/words",
        editingId ? "PUT" : "POST",
        data,
      );
      await loadContent();
      refreshStudy();
      $("#word-editor").close();
      notify("词条已保存到数据库。");
    } catch (error) {
      $("#word-editor-error").textContent = error.message;
    } finally {
      $("#word-submit").disabled = false;
    }
  };
  $("#word-archive").onclick = async () => {
    if (
      !editingId ||
      !confirm("归档后不再出现在学习队列中，历史学习记录仍保留。继续吗？")
    )
      return;
    try {
      await write("/words/" + editingId, "DELETE", {});
      await loadContent();
      refreshStudy();
      $("#word-editor").close();
      notify("词条已归档。");
    } catch (error) {
      $("#word-editor-error").textContent = error.message;
    }
  };
}
