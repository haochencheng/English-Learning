import { notify } from "./ui.js";
export function stopSpeaking() {
  if ("speechSynthesis" in window) speechSynthesis.cancel();
}
export function speak(text, language = "en-GB") {
  if (!("speechSynthesis" in window))
    return notify("当前浏览器不支持朗读，请使用支持语音合成的浏览器。");
  stopSpeaking();
  const utterance = new SpeechSynthesisUtterance(text);
  const voices = speechSynthesis.getVoices();
  utterance.voice =
    voices.find((v) => v.lang === language) ||
    voices.find((v) => v.lang.startsWith(language.split("-")[0])) ||
    null;
  utterance.lang = utterance.voice?.lang || language;
  utterance.rate = 0.85;
  utterance.onerror = (e) => {
    if (!["interrupted", "canceled"].includes(e.error))
      notify("朗读暂不可用，请检查设备语音包或网络。");
  };
  speechSynthesis.speak(utterance);
}
