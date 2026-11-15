import { speak } from "./speech.js";
import { renderPagination } from "./pagination.js";
import { api, write, requestId } from "./api.js";
import {
  WORDS,
  SCENARIOS,
  state,
  LABELS,
  INTERVALS,
  setProgress,
  pendingDrafts,
  loadContent,
} from "./store.js";
import { $, esc, notify, dayKey, showView } from "./ui.js";
let deck = "job",
  queue = [],
  index = 0,
  revealed = false,
  activeView = "today",
  quizIndex = 0,
  quizCorrect = 0,
  quizAnswered = false;
function due(w) {
  return !!state.reviews[w.id] && state.reviews[w.id].due <= Date.now();
}
export function makeQueue() {
  const rows = WORDS.filter((w) => w.deck === deck);
  queue =
    $("#queue-mode").value === "all"
      ? rows
      : rows
          .filter((w) => due(w))
          .sort((a, b) => state.reviews[a.id].due - state.reviews[b.id].due)
          .concat(rows.filter((w) => !state.reviews[w.id]));
  index = 0;
  revealed = false;
  renderCard();
}
function refreshStats() {
  const count = new Set(state.days[dayKey()] || []).size;
  $("#daily-count").textContent = count;
  $("#daily-bar").style.width = Math.min((count / 12) * 100, 100) + "%";
  $(".bar").setAttribute("aria-valuenow", Math.min(count, 12));
  $("#goal-label").textContent = count >= 12 ? "今日目标已完成" : "目标 12 词";
  $("#due-count").textContent = WORDS.filter(due).length;
  $("#learned-count").textContent = WORDS.filter(
    (w) => state.reviews[w.id],
  ).length;
  $("#word-total").textContent = WORDS.length;
}
const speakerIcon =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M11 5 5 9H2v6h3l6 4V5Z"/><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/></svg>';
function renderCard() {
  refreshStats();
  const w = queue[index];
  if (!w) {
    const future = WORDS.filter((w) => w.deck === deck && state.reviews[w.id])
      .map((w) => state.reviews[w.id].due)
      .filter((t) => t > Date.now());
    $("#card-area").innerHTML =
      '<div class="flashcard empty"><h2>这组词暂时完成了。</h2><p class="muted">' +
      (future.length
        ? "下次复习：" + new Date(Math.min(...future)).toLocaleString("zh-CN")
        : "可以选择另一组词汇继续学习。") +
      '</p><button id="refresh-queue" class="secondary">刷新待复习词汇</button><p><button class="text-button" id="browse-all">浏览这组全部词汇 →</button></p></div>';
    $("#refresh-queue").onclick = makeQueue;
    $("#browse-all").onclick = () => {
      $("#queue-mode").value = "all";
      makeQueue();
    };
    return;
  }
  const nextDays = INTERVALS[Math.min(state.reviews[w.id]?.stage || 0, 4)];
  $("#card-area").innerHTML =
    '<article class="flashcard"><div class="card-top"><span class="badge">' +
    (w.deck === "job"
      ? "软件与求职 · SOFTWARE & CAREER"
      : w.deck === "ielts"
        ? "主题补充 · WORK & SOCIETY"
        : "场景补充 · WORKPLACE") +
    '</span><span class="position">' +
    String(index + 1).padStart(2, "0") +
    " / " +
    String(queue.length).padStart(2, "0") +
    '</span></div><div class="word-row"><h2 class="word" lang="en">' +
    esc(w.term) +
    '</h2><button class="audio" id="speak-word" aria-label="朗读单词">' +
    speakerIcon +
    '</button></div><p class="word-meta">' +
    esc(w.pos) +
    ' <span aria-hidden="true">·</span> ' +
    (w.source_label ||
      (w.id.startsWith("custom-")
        ? "自定义词汇"
        : w.deck === "job"
          ? "职位正文词汇"
          : "自主选编词汇")) +
    '</p><div class="recall" ' +
    (revealed ? "hidden" : "") +
    '>先回忆它的意思。<span>你能在工作或讨论中，怎样使用这个词？</span></div><div class="answer" ' +
    (!revealed ? "hidden" : "") +
    '><h3 class="meaning">' +
    esc(w.meaning) +
    '</h3><div class="collocation" lang="en">' +
    esc(w.collocation) +
    '</div><p class="content-kind">' +
    (w.example_kind === "definition" ? "英文释义" : "工作与学习例句") +
    '</p><p class="example" lang="en">' +
    esc(w.example) +
    '</p><p class="translation">' +
    esc(w.translation) +
    '</p></div><div class="card-bottom"><a href="' +
    esc(w.source_url) +
    '" target="_blank" rel="noopener">' +
    (w.source_label
      ? esc(w.source_label) + " ↗"
      : w.deck === "job"
        ? "来源：LinkedIn · Binance ↗"
        : "学习方法参考：British Council ↗") +
    "</a>" +
    (revealed
      ? '<button class="text-button" id="speak-example" style="font-size:10px">朗读' +
        (w.example_kind === "definition" ? "释义" : "例句") +
        "</button>"
      : "<span>" +
        (w.example_kind === "definition"
          ? "词典释义 · 非情景例句"
          : "例句为原创教学内容") +
        "</span>") +
    '</div></article><div class="actions">' +
    (revealed
      ? '<button class="grade" data-grade="again">还没记住<span>10 分钟后</span></button><button class="grade" data-grade="hard">有点印象<span>1 天后</span></button><button class="grade" data-grade="good">记住了<span>' +
        nextDays +
        " 天后</span></button>"
      : '<button class="primary" id="reveal">查看释义与例句 <span aria-hidden="true">↗</span></button>') +
    '</div><p class="shortcut">' +
    (revealed
      ? "按 1 / 2 / 3 自评 · 只有自评才记录学习进度"
      : "空格查看答案 · ← / → 切换词卡") +
    "</p>";
  $("#speak-word").onclick = () => speak(w.term);
  if (revealed) {
    $("#speak-example").onclick = () => speak(w.example);
    document
      .querySelectorAll("[data-grade]")
      .forEach((b) => (b.onclick = () => grade(b.dataset.grade)));
  } else
    $("#reveal").onclick = () => {
      revealed = true;
      renderCard();
    };
}

let reviewing = false;
let pendingReview = null;
async function grade(rating) {
  const w = queue[index];
  if (!w || !revealed || reviewing) return;
  if (
    !pendingReview ||
    pendingReview.word_id !== w.id ||
    pendingReview.rating !== rating
  ) {
    pendingReview = {
      word_id: w.id,
      rating,
      request_id: requestId(),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    };
  }
  reviewing = true;
  document.querySelectorAll("[data-grade]").forEach((b) => (b.disabled = true));
  try {
    setProgress(await write("/reviews", "POST", pendingReview));
    pendingReview = null;
    index++;
    revealed = false;
    renderCard();
  } catch (error) {
    notify(error.message + " 本次尚未确认保存，点击同一选项可安全重试。");
    document
      .querySelectorAll("[data-grade]")
      .forEach((b) => (b.disabled = false));
  } finally {
    reviewing = false;
  }
}
function selectDeck(value) {
  deck = value;
  document.querySelectorAll("[data-deck]").forEach((b) => {
    b.classList.toggle("selected", b.dataset.deck === deck);
    b.setAttribute("aria-pressed", b.dataset.deck === deck);
  });
  makeQueue();
}
let libraryPage = 1,
  librarySize = 20,
  libraryRequest = 0;
export async function renderLibrary() {
  const request = ++libraryRequest;
  const params = new URLSearchParams({
    q: $("#search").value.trim(),
    page: libraryPage,
    page_size: librarySize,
  });
  if ($("#library-deck").value !== "all")
    params.set("deck", $("#library-deck").value);
  try {
    const data = await api("/words?" + params);
    if (request !== libraryRequest) return;
    libraryPage = data.page;
    const words = data.items;
    $("#result-count").textContent = `找到 ${data.total} 个词条`;
    renderPagination(
      $("#library-pagination"),
      data,
      [20, 40, 80],
      (page, size) => {
        libraryPage = page;
        librarySize = size;
        renderLibrary();
      },
    );
    $("#word-list").innerHTML = words.length
      ? words
          .map(
            (w) =>
              '<tr><td><button class="word-link" data-word="' +
              w.id +
              '">' +
              esc(w.term) +
              "</button></td><td>" +
              esc(w.meaning) +
              '</td><td class="muted">' +
              LABELS[w.deck] +
              '</td><td class="muted">' +
              (!state.reviews[w.id]
                ? "未学习"
                : due(w)
                  ? "待复习"
                  : "下次 " +
                    new Date(state.reviews[w.id].due).toLocaleDateString(
                      "zh-CN",
                    )) +
              '</td><td><button class=\"text-button\" data-edit=\"' +
              w.id +
              '\">编辑</button></td></tr>',
          )
          .join("")
      : '<tr><td colspan="5" class="muted">没有匹配的词汇，请试试其他关键词。</td></tr>';
    document.querySelectorAll("[data-word]").forEach(
      (b) =>
        (b.onclick = () => {
          const w = WORDS.find((w) => w.id === b.dataset.word);
          $("#queue-mode").value = "all";
          selectDeck(w.deck);
          index = queue.findIndex((x) => x.id === w.id);
          revealed = false;
          renderCard();
          showView("today");
        }),
    );
  } catch (error) {
    if (request === libraryRequest) {
      $("#result-count").textContent = "读取失败，请重新搜索或切换页面重试";
      notify(error.message);
    }
  }
}
function setPractice(type) {
  document.querySelectorAll("[data-practice]").forEach((b) => {
    b.classList.toggle("selected", b.dataset.practice === type);
    b.setAttribute("aria-pressed", b.dataset.practice === type);
  });
  $("#spelling-panel").hidden = type !== "spelling";
  $("#speaking-panel").hidden = type !== "speaking";
}
function quizWords() {
  return WORDS.filter((w) => w.deck === $("#quiz-deck").value);
}
function renderQuiz() {
  quizAnswered = false;
  const words = quizWords(),
    w = words[quizIndex];
  if (!w) {
    $("#quiz-meaning").textContent = "这组暂时没有词条，请先添加词汇。";
    $("#quiz-input").disabled = true;
    $("#quiz-check").hidden = true;
    $("#quiz-next").hidden = true;
    $("#quiz-feedback").textContent = "";
    $("#quiz-progress").textContent = "0 / 0";
    return;
  }
  $("#quiz-progress").textContent =
    quizIndex + 1 + " / " + words.length + " · 答对 " + quizCorrect + " 题";
  $("#quiz-meaning").textContent = w.meaning;
  $("#quiz-input").value = "";
  $("#quiz-input").disabled = false;
  $("#quiz-check").hidden = false;
  $("#quiz-next").hidden = true;
  $("#quiz-feedback").textContent = "";
}
function renderScenario() {
  const id = $("#scenario").value,
    s = SCENARIOS.find((x) => x.id === id);
  $("#scenario-question").textContent = s.q;
  $("#scenario-hint").textContent = s.hint;
  $("#draft").value = state.drafts[id] || "";
  $("#reference").textContent = s.answer;
  $("#reference").hidden = true;
  $("#show-reference").textContent = "查看参考表达";
  $("#show-reference").setAttribute("aria-expanded", "false");
  draftCount();
}
function draftCount() {
  $("#draft-count").textContent =
    ($("#draft").value.trim().match(/\S+/g) || []).length + " words";
}

const dirtyDrafts = new Set();
const draftTimers = new Map();
const draftChains = new Map();
const draftVersions = new Map();
let quizPendingId = null;
function draftStatus(text) {
  $("#draft-status").textContent = text;
}
function persistDraft(id) {
  clearTimeout(draftTimers.get(id));
  const text = state.drafts[id] || "";
  const version = draftVersions.get(id);
  const chain = (draftChains.get(id) || Promise.resolve())
    .catch(() => {})
    .then(async () => {
      if ($("#scenario").value === id) draftStatus("正在保存…");
      try {
        await write(`/drafts/${id}`, "PUT", { text });
        if (draftVersions.get(id) === version) {
          dirtyDrafts.delete(id);
          pendingDrafts.delete(id);
        }
        if ($("#scenario").value === id)
          draftStatus(dirtyDrafts.has(id) ? "有更改待保存" : "已保存到数据库");
      } catch (error) {
        if ($("#scenario").value === id)
          draftStatus("保存失败，点击「保存草稿」重试");
        notify(error.message);
      }
    });
  draftChains.set(id, chain);
  return chain;
}
export function refreshStudy() {
  makeQueue();
  renderLibrary();
  quizIndex = 0;
  quizCorrect = 0;
  renderQuiz();
  renderScenario();
  for (const select of [$("#library-deck"), $("#quiz-deck")]) {
    [...select.options].forEach((option) => {
      if (LABELS[option.value])
        option.textContent = `${LABELS[option.value]} · ${WORDS.filter((w) => w.deck === option.value).length}`;
    });
  }
  $("#library-description").textContent =
    `${WORDS.length} 个词条。支持新增、编辑和归档，更新后立即生效。`;
}
export function initStudy() {
  document.addEventListener("viewchange", (e) => {
    activeView = e.detail;
    if (activeView === "library") renderLibrary();
    if (activeView === "today") refreshStats();
    if (activeView !== "practice")
      for (const id of dirtyDrafts) persistDraft(id);
  });
  document
    .querySelectorAll("[data-deck]")
    .forEach((b) => (b.onclick = () => selectDeck(b.dataset.deck)));
  $("#queue-mode").onchange = makeQueue;
  let searchTimer;
  $("#search").oninput = () => {
    libraryPage = 1;
    ++libraryRequest;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(renderLibrary, 200);
  };
  $("#library-deck").onchange = () => {
    libraryPage = 1;
    renderLibrary();
  };
  document
    .querySelectorAll("[data-practice]")
    .forEach((b) => (b.onclick = () => setPractice(b.dataset.practice)));
  $("#open-speaking").onclick = () => {
    showView("practice");
    setPractice("speaking");
  };
  $("#quiz-deck").onchange = () => {
    quizIndex = 0;
    quizCorrect = 0;
    quizPendingId = null;
    renderQuiz();
  };
  $("#quiz-form").onsubmit = async (e) => {
    e.preventDefault();
    if (quizAnswered || $("#quiz-check").disabled) return;
    const w = quizWords()[quizIndex],
      answer = $("#quiz-input").value.trim();
    if (!w || !answer) return;
    quizPendingId ||= requestId();
    $("#quiz-check").disabled = true;
    try {
      const result = await write("/quiz-attempts", "POST", {
        word_id: w.id,
        answer,
        request_id: quizPendingId,
      });
      quizPendingId = null;
      if (result.correct) quizCorrect++;
      quizAnswered = true;
      $("#quiz-input").disabled = true;
      $("#quiz-check").hidden = true;
      $("#quiz-next").hidden = false;
      $("#quiz-next").textContent =
        quizIndex === quizWords().length - 1
          ? "完成本轮，重新开始"
          : "下一题 →";
      $("#quiz-feedback").innerHTML =
        `<p class="feedback-result">${result.correct ? "答对了。" : "再记一下："}</p><div class="feedback-line"><strong lang="en">${esc(result.term)}</strong><button type="button" class="audio" id="quiz-speak-word" aria-label="朗读答案单词">${speakerIcon}</button></div><p class="content-kind">${result.example_kind === "definition" ? "英文释义" : "例句"}</p><div class="feedback-line"><span lang="en">${esc(result.example)}</span><button type="button" class="audio" id="quiz-speak-example" aria-label="朗读答案句子">${speakerIcon}</button></div>${quizIndex === quizWords().length - 1 ? `<p>本轮答对 ${quizCorrect} / ${quizWords().length} 题。</p>` : ""}`;
      $("#quiz-speak-word").onclick = () => speak(result.term);
      $("#quiz-speak-example").onclick = () => speak(result.example);
      $("#quiz-progress").textContent =
        quizIndex +
        1 +
        " / " +
        quizWords().length +
        " · 答对 " +
        quizCorrect +
        " 题";
    } catch (error) {
      notify(error.message);
    } finally {
      $("#quiz-check").disabled = false;
    }
  };
  $("#quiz-input").addEventListener("input", () => (quizPendingId = null));
  $("#quiz-next").onclick = () => {
    quizIndex++;
    if (quizIndex === quizWords().length) {
      quizIndex = 0;
      quizCorrect = 0;
    }
    renderQuiz();
    $("#quiz-input").focus();
  };
  $("#scenario").onchange = () => {
    for (const id of dirtyDrafts) persistDraft(id);
    renderScenario();
    draftStatus(
      dirtyDrafts.has($("#scenario").value) ? "待保存" : "已从数据库读取",
    );
  };
  $("#draft").maxLength = 20000;
  $("#draft").oninput = () => {
    const id = $("#scenario").value;
    state.drafts[id] = $("#draft").value;
    pendingDrafts.set(id, $("#draft").value);
    dirtyDrafts.add(id);
    draftVersions.set(id, (draftVersions.get(id) || 0) + 1);
    clearTimeout(draftTimers.get(id));
    draftTimers.set(
      id,
      setTimeout(() => persistDraft(id), 600),
    );
    draftCount();
    draftStatus("待保存…");
  };
  $("#save-draft").onclick = () => persistDraft($("#scenario").value);
  window.addEventListener("beforeunload", (e) => {
    if (dirtyDrafts.size) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  $("#show-reference").onclick = () => {
    const hidden = $("#reference").hidden;
    $("#reference").hidden = !hidden;
    $("#show-reference").setAttribute("aria-expanded", hidden);
    $("#show-reference").textContent = hidden ? "收起参考表达" : "查看参考表达";
  };
  $("#export").onclick = async () => {
    try {
      await Promise.all([...dirtyDrafts].map(persistDraft));
      if (dirtyDrafts.size) throw new Error("仍有草稿未保存，请先重试保存。");
      const data = await api("/progress");
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "wordcraft-progress-" + dayKey() + ".json";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify("已导出词汇进度与表达草稿。视频等完整数据请使用数据库备份。");
    } catch (error) {
      notify(error.message);
    }
  };
  $("#import").onclick = () => $("#import-file").click();
  $("#import-file").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      if (file.size > 2_000_000) throw Error("文件不能超过 2 MB");
      const data = JSON.parse(await file.text());
      if (
        !confirm(
          "将合并词汇进度，保留数据库中较新的复习记录和已有草稿。继续吗？",
        )
      )
        return;
      setProgress(await write("/progress/import", "POST", data));
      refreshStudy();
      notify("进度已合并到数据库。");
    } catch (error) {
      notify("导入失败：" + error.message);
    } finally {
      e.target.value = "";
    }
  };
  document.addEventListener("keydown", (e) => {
    if (
      activeView !== "today" ||
      ["INPUT", "TEXTAREA", "SELECT", "BUTTON", "A"].includes(
        document.activeElement.tagName,
      ) ||
      e.ctrlKey ||
      e.metaKey ||
      e.altKey ||
      e.repeat
    )
      return;
    if (e.code === "Space" && queue[index]) {
      e.preventDefault();
      revealed = !revealed;
      renderCard();
    } else if (revealed && ["1", "2", "3"].includes(e.key)) {
      grade({ 1: "again", 2: "hard", 3: "good" }[e.key]);
    } else if (
      ["ArrowLeft", "ArrowRight"].includes(e.key) &&
      queue.length &&
      !reviewing
    ) {
      e.preventDefault();
      index = Math.max(
        0,
        Math.min(queue.length - 1, index + (e.key === "ArrowRight" ? 1 : -1)),
      );
      revealed = false;
      renderCard();
    }
  });
  $("#job-link").href = WORDS.find((w) => w.deck === "job")?.source_url || "#";
  $("#plan-job").href = $("#job-link").href;
  refreshStudy();
}
