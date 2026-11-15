import { write } from "./api.js";
import { loadContent, setProgress, state } from "./store.js";
import { $, notify, showView } from "./ui.js";
import { initStudy, refreshStudy } from "./study.js";
import { initVideos } from "./videos.js";
import { initEditor } from "./content-editor.js";

async function start() {
  $("#app-status").textContent = "连接数据库…";
  try {
    await loadContent();
    initStudy();
    initEditor();
    document
      .querySelectorAll("[data-view]")
      .forEach((b) => (b.onclick = () => showView(b.dataset.view)));
    $("#date").textContent = new Date().toLocaleDateString("zh-CN", {
      month: "long",
      day: "numeric",
      weekday: "long",
    });
    $("#app-status").textContent = "已连接 · 数据库保存";
    $("#app-loading").hidden = true;
    $("#workspace-content").inert = false;
    let legacy = null;
    try {
      legacy = JSON.parse(localStorage.getItem("wordcraft-study-v1"));
    } catch {}
    const needsMigration =
      legacy &&
      (Object.entries(legacy.reviews || {}).some(
        ([id, r]) => !state.reviews[id] || r.count > state.reviews[id].count,
      ) ||
        Object.entries(legacy.days || {}).some(([day, ids]) =>
          ids.some((id) => !(state.days[day] || []).includes(id)),
        ) ||
        Object.keys(legacy.drafts || {}).some((id) => !(id in state.drafts)));
    if (needsMigration) {
      $("#legacy-banner").hidden = false;
      $("#migrate-legacy").onclick = async () => {
        $("#migrate-legacy").disabled = true;
        try {
          setProgress(await write("/progress/import", "POST", legacy));
          refreshStudy();
          $("#legacy-banner").hidden = true;
          notify("旧版进度已合并；浏览器中的原始备份仍保留。");
        } catch (error) {
          notify(error.message);
        } finally {
          $("#migrate-legacy").disabled = false;
        }
      };
    }
    await initVideos();
  } catch (error) {
    $("#app-status").textContent = "连接失败";
    $("#app-loading").innerHTML =
      '<strong>暂时无法连接学习服务</strong><p id="boot-error"></p><button class="secondary" id="retry-boot">重新连接</button>';
    $("#boot-error").textContent = error.message;
    $("#retry-boot").onclick = () => location.reload();
  }
}
start();
