import { api } from "./api.js";
export let WORDS = [];
export let SCENARIOS = [];
export let state = { version: 1, reviews: {}, days: {}, drafts: {} };
export const pendingDrafts = new Map();
export const LABELS = {
  job: "求职英语",
  ielts: "雅思主题",
  business: "商务英语",
};
export const INTERVALS = [1, 3, 7, 14, 30];
export function setProgress(value) {
  state = {
    ...value,
    drafts: { ...value.drafts, ...Object.fromEntries(pendingDrafts) },
  };
}
export async function loadContent() {
  const data = await api("/bootstrap");
  WORDS = data.words;
  SCENARIOS = data.scenarios;
  setProgress(data.progress);
  return data;
}
