import { initTranscripts, selectTranscript } from "./transcripts.js";
import { renderPagination } from "./pagination.js";
import { api, write } from "./api.js";
import { $, esc, notify } from "./ui.js";
import { LABELS } from "./store.js";

let videoPage = 1,
  videoSize = 12;
let items = [],
  selected = null,
  notesDirty = false,
  pollTimer = null,
  listRequest = 0;
const STATUS = {
  running: "采集中",
  completed: "已完成",
  partial: "部分成功",
  failed: "采集失败",
  interrupted: "服务重启，任务已中断",
};
export async function loadVideos() {
  const request = ++listRequest;
  const params = new URLSearchParams({ page: videoPage, page_size: videoSize });
  if ($("#video-deck").value !== "all")
    params.set("deck", $("#video-deck").value);
  if ($("#video-search").value.trim())
    params.set("q", $("#video-search").value.trim());
  if ($("#video-favorites").checked) params.set("favorite", "true");
  try {
    const data = await api("/videos?" + params);
    if (request !== listRequest) return;
    items = data.items;
    videoPage = data.page;
    $("#video-count").textContent = `${data.total} 个视频 · 来源 YouTube`;
    renderPagination(
      $("#video-pagination"),
      data,
      [12, 24, 48],
      (page, size) => {
        videoPage = page;
        videoSize = size;
        loadVideos();
      },
    );
    $("#video-list").innerHTML = items.length
      ? items
          .map(
            (
              v,
            ) => `<button class="video-item ${v.youtube_id === selected?.youtube_id ? "selected" : ""}" data-video="${v.youtube_id}">
      <span class="thumbnail"><img src="${esc(v.thumbnail_url)}" alt="" loading="lazy" referrerpolicy="strict-origin-when-cross-origin"><span class="play-icon" aria-hidden="true">▶</span></span>
      <span class="video-info"><span class="video-category">${LABELS[v.deck]} ${v.favorite ? "· 已收藏" : ""} ${v.completed ? "· 已完成" : ""}</span><strong>${esc(v.title)}</strong><span class="muted">${esc(v.channel)}</span></span></button>`,
          )
          .join("")
      : '<div class="empty"><h2>这里还没有视频</h2><p class="muted">试试其他筛选，或点击「采集资料」同步精选视频。</p></div>';
    document
      .querySelectorAll("[data-video]")
      .forEach((b) => (b.onclick = () => selectVideo(b.dataset.video)));
  } catch (error) {
    $("#video-count").textContent = "读取失败，可点击刷新重试";
    notify(error.message);
  }
}
async function saveNotes() {
  if (!selected || !notesDirty) return true;
  const videoId = selected.youtube_id,
    text = $("#video-notes").value;
  $("#video-note-status").textContent = "正在保存…";
  try {
    await write(`/videos/${videoId}/progress`, "PATCH", { notes: text });
    if (selected.youtube_id === videoId && $("#video-notes").value === text) {
      selected.notes = text;
      notesDirty = false;
      $("#video-note-status").textContent = "已保存到数据库";
    }
    return !notesDirty;
  } catch (error) {
    $("#video-note-status").textContent = "保存失败，笔记仍保留在输入框中";
    notify(error.message);
    return false;
  }
}
async function selectVideo(id) {
  if (id === selected?.youtube_id) return;
  if (!(await saveNotes())) return;
  selected = items.find((v) => v.youtube_id === id);
  if (!selected) return;
  $("#video-placeholder").hidden = true;
  $("#video-detail").hidden = false;
  $("#video-title").textContent = selected.title;
  $("#video-channel").textContent =
    `${selected.channel} · ${LABELS[selected.deck]}`;
  $("#video-hint").textContent = selected.learning_hint;
  $("#video-external").href = `https://www.youtube.com/watch?v=${id}`;
  $("#video-player").src =
    `https://www.youtube-nocookie.com/embed/${id}?cc_lang_pref=en&cc_load_policy=1&rel=0`;
  $("#video-player").title = selected.title;
  $("#video-notes").value = selected.notes;
  notesDirty = false;
  $("#video-note-status").textContent = "已从数据库读取";
  $("#video-meta").textContent =
    `采集于 ${new Date(selected.fetched_at).toLocaleString("zh-CN")} · ${selected.source === "curated" ? "精选资料" : selected.source === "channels" ? "频道订阅" : selected.source === "search" ? "关键词检索" : "链接导入"}`;
  updateActions();
  selectTranscript(id);
  if (window.matchMedia("(max-width:1150px)").matches) {
    $(".video-inspector").scrollIntoView({
      block: "start",
      behavior: window.matchMedia("(prefers-reduced-motion:reduce)").matches
        ? "instant"
        : "smooth",
    });
  }
  document
    .querySelectorAll("[data-video]")
    .forEach((b) => b.classList.toggle("selected", b.dataset.video === id));
}
function updateActions() {
  $("#video-save").textContent = selected.favorite ? "已收藏 ✓" : "收藏视频";
  $("#video-save").setAttribute("aria-pressed", !!selected.favorite);
  $("#video-complete").textContent = selected.completed
    ? "已完成 ✓"
    : "标记学完";
  $("#video-complete").setAttribute("aria-pressed", !!selected.completed);
}
async function toggle(field) {
  if (!selected) return;
  try {
    const data = await write(
      `/videos/${selected.youtube_id}/progress`,
      "PATCH",
      { [field]: !selected[field] },
    );
    selected[field] = data[field];
    updateActions();
    await loadVideos();
  } catch (error) {
    notify(error.message);
  }
}
async function refreshRuns() {
  clearTimeout(pollTimer);
  try {
    const runs = await api("/video-sync");
    const latest = runs[0];
    $("#sync-history").innerHTML =
      runs
        .slice(0, 5)
        .map(
          (run) =>
            `<div class="sync-row"><strong>${STATUS[run.status] || esc(run.status)}</strong><span>${new Date(run.started_at).toLocaleString("zh-CN")} · 写入/更新 ${run.imported} · 失败 ${run.failed}</span>${run.details.map((d) => `<p>${esc([d.source, d.error || d.message].filter(Boolean).join("："))}</p>`).join("")}</div>`,
        )
        .join("") || '<p class="muted">还没有采集记录。</p>';
    const running = latest?.status === "running";
    $("#sync-start").disabled = running;
    $("#sync-start").textContent = running ? "正在采集…" : "开始采集";
    $("#video-sync-status").textContent = latest
      ? `${STATUS[latest.status]} · 本次写入/更新 ${latest.imported} 个视频`
      : "尚未采集";
    if (running) pollTimer = setTimeout(refreshRuns, 1500);
    else await loadVideos();
  } catch (error) {
    $("#video-sync-status").textContent = "读取采集状态失败，请点刷新重试";
    $("#sync-start").disabled = false;
    notify(error.message);
  }
}
export async function initVideos() {
  initTranscripts();
  let debounce;
  $("#video-search").oninput = () => {
    clearTimeout(debounce);
    videoPage = 1;
    ++listRequest;
    debounce = setTimeout(loadVideos, 250);
  };
  $("#video-deck").onchange = $("#video-favorites").onchange = () => {
    videoPage = 1;
    loadVideos();
  };
  $("#video-refresh").onclick = refreshRuns;
  $("#video-notes").oninput = () => {
    notesDirty = true;
    $("#video-note-status").textContent = "有更改待保存";
  };
  $("#video-notes-save").onclick = saveNotes;
  $("#video-save").onclick = () => toggle("favorite");
  $("#video-complete").onclick = () => toggle("completed");
  window.addEventListener("beforeunload", (e) => {
    if (notesDirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  document.addEventListener("viewchange", (e) => {
    if (e.detail === "videos") loadVideos();
    else if (selected) {
      saveNotes();
      $("#video-player").src = "";
    }
    if (
      e.detail === "videos" &&
      selected &&
      !$("#video-player").getAttribute("src")
    )
      $("#video-player").src =
        `https://www.youtube-nocookie.com/embed/${selected.youtube_id}?cc_lang_pref=en&cc_load_policy=1&rel=0`;
  });
  $("#video-import-form").onsubmit = async (e) => {
    e.preventDefault();
    $("#video-import-button").disabled = true;
    try {
      const data = await write("/videos/import", "POST", {
        url: $("#video-url").value,
        deck: $("#video-import-deck").value,
      });
      $("#video-url").value = "";
      $("#video-deck").value = "all";
      $("#video-search").value = "";
      $("#video-favorites").checked = false;
      videoPage = 1;
      await loadVideos();
      await selectVideo(data.youtube_id);
      notify("视频资料已保存到数据库。");
    } catch (error) {
      notify(error.message);
    } finally {
      $("#video-import-button").disabled = false;
    }
  };
  $("#sync-mode").onchange = () =>
    ($("#sync-search-fields").hidden = $("#sync-mode").value !== "search");
  $("#sync-form").onsubmit = async (e) => {
    e.preventDefault();
    $("#sync-start").disabled = true;
    try {
      await write("/video-sync", "POST", {
        mode: $("#sync-mode").value,
        deck: $("#sync-deck").value,
        query: $("#sync-query").value,
        limit: Number($("#sync-limit").value),
      });
      await refreshRuns();
    } catch (error) {
      notify(error.message);
      $("#sync-start").disabled = false;
    }
  };
  try {
    const config = await api("/video-config");
    $("#api-key-status").textContent = config.search_enabled
      ? "关键词检索已连接。"
      : "关键词检索尚未启用：请在后端 .env 设置 YOUTUBE_API_KEY。精选同步、频道订阅和视频链接导入无需密钥。";
    $('#sync-mode option[value="search"]').disabled = !config.search_enabled;
    $("#channel-list").textContent = config.channels
      .map((c) => c.name)
      .join(" · ");
  } catch (error) {
    notify(error.message);
  }
  await refreshRuns();
}
