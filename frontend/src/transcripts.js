import { api, write } from "./api.js";
import { $, esc, notify } from "./ui.js";
import { speak, stopSpeaking } from "./speech.js";
let videoId = null,
  transcript = null,
  timer = null,
  generation = 0,
  lookupGeneration = 0,
  visible = 80,
  activeWord = "",
  activeSentence = "",
  dictionaryCache = new Map();
const importDrafts = new Map();
const speaker =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M11 5 5 9H2v6h3l6 4V5Z"/><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/></svg>';
function words(text) {
  let output = "",
    last = 0;
  for (const match of text.matchAll(/[A-Za-z]+(?:['’\-][A-Za-z]+)*/g)) {
    output += esc(text.slice(last, match.index));
    output += `<button type="button" class="subtitle-word" data-lookup="${esc(match[0])}" aria-label="查词：${esc(match[0])}">${esc(match[0])}</button>`;
    last = match.index + match[0].length;
  }
  return output + esc(text.slice(last));
}
function timeLabel(start) {
  const seconds = Math.floor(start);
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
function render() {
  if (!transcript) return;
  const rows = transcript.segments,
    ready = rows.length > 0;
  $("#transcript-status").textContent =
    transcript.status === "fetching"
      ? "正在读取英文字幕和中文译文…"
      : ready
        ? `${rows.length} 段英文 · ${transcript.translated} 段有中文译文 · 已保存`
        : "尚无字幕";
  $("#transcript-message").textContent =
    transcript.message ||
    (!ready
      ? "可获取公开视频字幕，也可导入英文与中文字幕。"
      : transcript.translated < rows.length
        ? "部分段落暂时没有对应译文，可导入中文字幕补充。"
        : "");
  $("#transcript-source").textContent = [
    transcript.english_source,
    transcript.translation_source,
    ready ? "字幕可能含识别或翻译误差，可对照视频核对。" : "",
  ]
    .filter(Boolean)
    .join(" · ");
  $("#transcript-fetch").disabled = transcript.status === "fetching";
  $("#transcript-fetch").textContent = ready ? "重新获取字幕" : "获取双语字幕";
  $("#transcript-search").disabled = !ready;
  $("#transcript-empty").hidden = ready;
  $("#transcript-rows").classList.toggle(
    "hide-chinese",
    !$("#transcript-chinese").checked,
  );
  const search = $("#transcript-search").value.trim().toLowerCase();
  const matched = search
      ? rows.filter((s) =>
          (s.english + " " + s.chinese).toLowerCase().includes(search),
        )
      : rows,
    shown = matched.slice(0, visible);
  $("#transcript-rows").innerHTML =
    shown
      .map(
        (s) =>
          `<article class="subtitle-cue" data-seq="${s.seq}"><div class="cue-heading">${s.start === null ? `<span class="muted">${s.seq + 1}</span>` : `<button type="button" class="cue-time" data-seek="${s.start}" aria-label="跳转到 ${timeLabel(s.start)}">${timeLabel(s.start)}</button>`}<button type="button" class="audio" data-read-cue="${s.seq}" aria-label="朗读第 ${s.seq + 1} 段英文">${speaker}</button></div><p class="cue-english" lang="en">${words(s.english)}</p><p class="cue-chinese" lang="zh-CN">${esc(s.chinese || "该段暂无对应译文")}</p></article>`,
      )
      .join("") ||
    (ready ? '<p class="muted">没有匹配的字幕，请换个关键词。</p>' : "");
  $("#transcript-count").textContent = ready
    ? `显示 ${shown.length} / ${matched.length} 段${search ? "（搜索整个字幕）" : ""}`
    : "";
  $("#transcript-more").hidden = shown.length >= matched.length;
}
async function refresh(current = videoId, version = generation) {
  try {
    const data = await api(`/videos/${current}/transcript`);
    if (current !== videoId || version !== generation) return;
    transcript = data;
    render();
    clearTimeout(timer);
    if (data.status === "fetching" && !$("#view-videos").hidden)
      timer = setTimeout(() => refresh(current, version), 1500);
  } catch (error) {
    if (version === generation) {
      $("#transcript-status").textContent = "字幕读取失败";
      $("#transcript-message").textContent = error.message;
      $("#transcript-fetch").disabled = false;
    }
  }
}
async function fetchTranscript(refreshExisting = false) {
  const current = videoId,
    version = generation;
  if (!current) return;
  $("#transcript-fetch").disabled = true;
  $("#transcript-status").textContent = "正在请求字幕…";
  try {
    await write(`/videos/${current}/transcript/fetch`, "POST", {
      refresh: refreshExisting,
    });
    if (current === videoId && version === generation)
      await refresh(current, version);
  } catch (error) {
    if (version === generation) {
      $("#transcript-message").textContent = error.message;
      $("#transcript-fetch").disabled = false;
    }
  }
}
export async function selectTranscript(id) {
  if (videoId) {
    const english = $("#subtitle-en").value,
      chinese = $("#subtitle-zh").value;
    if (english || chinese) importDrafts.set(videoId, { english, chinese });
    else importDrafts.delete(videoId);
  }
  videoId = id;
  ++generation;
  ++lookupGeneration;
  clearTimeout(timer);
  stopSpeaking();
  transcript = null;
  visible = 80;
  $("#transcript-search").value = "";
  for (const id of [
    "transcript-rows",
    "transcript-count",
    "transcript-source",
    "transcript-message",
  ])
    $("#" + id).textContent = "";
  $("#transcript-status").textContent = "正在读取字幕…";
  $("#transcript-more").hidden = true;
  $("#transcript-fetch").disabled = true;
  $("#transcript-search").disabled = true;
  $("#transcript-empty").hidden = true;
  $("#word-lookup").hidden = true;
  $("#transcript-import").open = false;
  $("#subtitle-en").value = importDrafts.get(id)?.english || "";
  $("#subtitle-zh").value = importDrafts.get(id)?.chinese || "";
  $("#subtitle-import-save").disabled = false;
  $("#subtitle-import-status").textContent = "";
  const version = generation;
  await refresh(id, version);
  if (version === generation && transcript?.status === "empty")
    await fetchTranscript();
}
async function lookup(word, seq) {
  if (!word || word.length > 60) return;
  const token = ++lookupGeneration,
    context = transcript?.segments.find((s) => s.seq === Number(seq));
  activeWord = word;
  activeSentence = context?.english || "";
  $("#word-lookup").hidden = false;
  $("#lookup-term").textContent = word;
  $("#lookup-phonetic").textContent = "";
  $("#lookup-meaning").textContent = "正在查词…";
  $("#lookup-definition").textContent = "";
  $("#lookup-definition-panel").open = false;
  $("#lookup-definition-panel").hidden = true;
  $("#lookup-source").textContent = "";
  $("#lookup-context").textContent =
    context?.chinese || "这段字幕暂时没有中文译文。";
  $("#lookup-sentence-speak").disabled = !activeSentence;
  try {
    const key = word.toLowerCase().replaceAll("’", "'");
    let data = dictionaryCache.get(key);
    if (!data) {
      data = await api("/dictionary?" + new URLSearchParams({ q: word }));
      if (dictionaryCache.size > 500) dictionaryCache.clear();
      dictionaryCache.set(key, data);
    }
    if (token !== lookupGeneration) return;
    $("#lookup-term").textContent =
      data.term === key ? word : `${word} → ${data.term}`;
    $("#lookup-phonetic").textContent = data.phonetic
      ? `/${data.phonetic}/`
      : "";
    $("#lookup-meaning").textContent = data.meaning;
    $("#lookup-definition").textContent = data.definition;
    $("#lookup-definition-panel").hidden = !data.definition;
    $("#lookup-source").textContent = data.source;
  } catch (error) {
    if (token === lookupGeneration)
      $("#lookup-meaning").textContent = error.message;
  }
}
export function initTranscripts() {
  window.addEventListener("beforeunload", (e) => {
    if (
      [...importDrafts.keys()].some((id) => id !== videoId) ||
      $("#subtitle-en").value ||
      $("#subtitle-zh").value
    ) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  $("#transcript-fetch").onclick = () => fetchTranscript(true);
  $("#transcript-more").onclick = () => {
    visible += 80;
    render();
  };
  $("#transcript-search").oninput = () => {
    visible = 80;
    render();
  };
  $("#transcript-chinese").onchange = () =>
    $("#transcript-rows").classList.toggle(
      "hide-chinese",
      !$("#transcript-chinese").checked,
    );
  $("#transcript-stop").onclick = stopSpeaking;
  $("#lookup-word-speak").innerHTML = speaker + " 朗读单词";
  $("#lookup-word-speak").onclick = () => speak(activeWord);
  $("#lookup-sentence-speak").onclick = () => speak(activeSentence);
  $("#lookup-close").onclick = () => {
    ++lookupGeneration;
    $("#word-lookup").hidden = true;
  };
  $("#transcript-rows").onclick = (e) => {
    const word = e.target.closest("[data-lookup]");
    if (word)
      return lookup(
        word.dataset.lookup,
        word.closest("[data-seq]").dataset.seq,
      );
    const read = e.target.closest("[data-read-cue]");
    if (read)
      return speak(
        transcript.segments.find((s) => s.seq === Number(read.dataset.readCue))
          .english,
      );
    const seek = e.target.closest("[data-seek]");
    if (seek) {
      stopSpeaking();
      $("#video-player").src =
        `https://www.youtube-nocookie.com/embed/${videoId}?start=${Math.floor(Number(seek.dataset.seek))}&autoplay=1&cc_lang_pref=en&cc_load_policy=1&rel=0`;
    }
  };
  $("#transcript-rows").addEventListener("mouseup", () => {
    const selection = window.getSelection(),
      text = selection?.toString().trim();
    if (!text || !/^[A-Za-z]+(?:['’\-][A-Za-z]+)*$/.test(text)) return;
    const anchor = selection.anchorNode?.parentElement?.closest("[data-seq]");
    if (anchor && $("#transcript-rows").contains(anchor))
      lookup(text, anchor.dataset.seq);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      $("#word-lookup").hidden = true;
      ++lookupGeneration;
      stopSpeaking();
    }
  });
  document.addEventListener("viewchange", (e) => {
    if (e.detail !== "videos") {
      stopSpeaking();
      clearTimeout(timer);
      $("#word-lookup").hidden = true;
    } else if (videoId) refresh();
  });
  for (const [id, target] of [
    ["subtitle-en-file", "#subtitle-en"],
    ["subtitle-zh-file", "#subtitle-zh"],
  ])
    $("#" + id).onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const version = generation;
      try {
        if (file.size > 1_500_000) throw new Error("字幕文件不能超过 1.5 MB。");
        const text = await file.text();
        if (version === generation) $(target).value = text;
      } catch (error) {
        notify(error.message);
      } finally {
        e.target.value = "";
      }
    };
  $("#subtitle-import-form").onsubmit = async (e) => {
    e.preventDefault();
    const current = videoId,
      version = generation,
      english = $("#subtitle-en").value,
      chinese = $("#subtitle-zh").value;
    if (!english.trim() && !chinese.trim()) {
      $("#subtitle-import-status").textContent = "请粘贴或选择字幕文件。";
      return;
    }
    if (
      transcript?.total &&
      !confirm("导入将替换当前视频的字幕；视频笔记会保留。继续吗？")
    )
      return;
    $("#subtitle-import-save").disabled = true;
    try {
      const data = await write(`/videos/${current}/transcript`, "PUT", {
        english,
        chinese,
      });
      if (version === generation) {
        transcript = data;
        importDrafts.delete(current);
        visible = 80;
        render();
        $("#subtitle-en").value = "";
        $("#subtitle-zh").value = "";
        $("#subtitle-import-status").textContent = "双语字幕已保存到数据库。";
      }
    } catch (error) {
      if (version === generation)
        $("#subtitle-import-status").textContent = error.message;
    } finally {
      if (version === generation) $("#subtitle-import-save").disabled = false;
    }
  };
}
