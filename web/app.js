import {WavRecorder} from "./audio.js";

const $ = (id) => document.getElementById(id);
const translations = {
  interfaceLanguage:["Interface language","इंटरफ़ेस की भाषा"], newCase:["Start new case","नया केस शुरू करें"],
  eyebrow:["A CONSUMER GRIEVANCE COMPANION FOR INDIA","भारत में उपभोक्ता शिकायतों का साथी"], headline:["Your story. Clearer next steps.","आपकी बात। आगे की स्पष्ट राह।"],
  purpose:["Describe a refund, damaged product or missing delivery in English, Hindi or Hinglish. Review the facts, explore checked information, and prepare your complaint.","रिफंड, खराब उत्पाद या सामान न मिलने की समस्या अंग्रेज़ी, हिन्दी या हिंग्लिश में बताएँ। तथ्य जाँचें, सत्यापित जानकारी समझें और शिकायत तैयार करें।"],
  disclaimer:["Legal information assistance only. This is not a substitute for a qualified lawyer. Facts are user-reported; no outcome is guaranteed.","केवल कानूनी जानकारी में सहायता। यह योग्य वकील का विकल्प नहीं है। तथ्य उपयोगकर्ता के कथन हैं; परिणाम की गारंटी नहीं है।"],
  privacy:["Temporary workspace · Refreshing clears this case. No server conversation storage. Use fictional details for this demo.","अस्थायी कार्यक्षेत्र · रीफ़्रेश करने से केस मिट जाएगा। सर्वर पर बातचीत सहेजी नहीं जाती। डेमो में काल्पनिक विवरण दें।"],
  step1:["01 / TELL YOUR STORY","01 / अपनी बात बताएँ"], step2:["02 / REVIEW YOUR FACTS","02 / तथ्य जाँचें"], step3:["03 / UNDERSTAND YOUR OPTIONS","03 / विकल्प समझें"], step4:["04 / PREPARE YOUR COMPLAINT","04 / शिकायत तैयार करें"],
  conversation:["Conversation","बातचीत"], multilingual:["EN · हिन्दी · Hinglish","English · हिन्दी · हिंग्लिश"], startTitle:["Let’s start with what happened.","शुरू करें: क्या हुआ था?"], startText:["What did you order, and what went wrong? Share only the details you know.","आपने क्या मँगाया और क्या समस्या हुई? केवल वे विवरण दें जो जानते हैं।"],
  example:["Try: “My ₹2,999 headphones arrived damaged and the seller refused a refund.”","उदाहरण: ‘₹2,999 के हेडफ़ोन खराब मिले और विक्रेता ने रिफंड देने से मना किया।’"],
  yourMessage:["Your message","आपका संदेश"], messagePlaceholder:["Describe your consumer problem…","अपनी उपभोक्ता समस्या बताएँ…"], unknowns:["Unknown details can stay unknown.","अज्ञात विवरण अज्ञात रह सकते हैं।"], send:["Send message ↗","संदेश भेजें ↗"],
  voice:["Prefer to speak?","बोलकर बताना चाहते हैं?"], voiceHelp:["Record up to 60 seconds. Transcribe, review and edit, then explicitly send. Audio goes to Google only when you transcribe.","60 सेकंड तक रिकॉर्ड करें। पाठ में बदलें, जाँचें और सुधारें, फिर भेजें। लिप्यंतरण बटन दबाने पर ही ऑडियो Google को जाएगा।"],
  startRecording:["Start recording","रिकॉर्डिंग शुरू करें"], stopRecording:["Stop recording","रिकॉर्डिंग रोकें"], transcribe:["Transcribe audio","ऑडियो का लिप्यंतरण करें"], transcriptLabel:["Review and edit transcript","पाठ जाँचें और सुधारें"], sendVoice:["Send approved transcript","स्वीकृत पाठ भेजें"],
  reviewVoice:["Check names, amounts and dates. Intake receives only the text you approve, not your recording.","नाम, राशि और तारीख जाँचें। केस में केवल आपके स्वीकृत पाठ का उपयोग होगा, रिकॉर्डिंग का नहीं।"], voiceLimit:["Mono PCM WAV · 16 kHz · Below 2 MB. Microphone needs permission and localhost or HTTPS. Text chat always remains available.","मोनो PCM WAV · 16 kHz · 2 MB से छोटा। माइक्रोफ़ोन के लिए अनुमति और localhost या HTTPS चाहिए। लिखकर संदेश भेजना भी उपलब्ध है।"],
  caseFile:["Case File","केस फ़ाइल"], caseHelp:["Your account, not independently verified. Correct any mistakes in the conversation.","आपका विवरण; स्वतंत्र रूप से सत्यापित नहीं। बातचीत में गलतियाँ सुधारें।"], missing:["Details still to clarify","स्पष्ट करने योग्य विवरण"],
  narrativeWarning:["Earlier narrative was cleared after a correction or conflict. Check current facts and add a fresh description when editing your draft.","सुधार या विरोधाभास के बाद पुराना विवरण हटा दिया गया है। वर्तमान तथ्य जाँचें और मसौदा संपादित करते समय नया विवरण जोड़ें।"], guidance:["Legal information","कानूनी जानकारी"],
  package:["Action Package","कार्रवाई के दस्तावेज़"], noExtraAI:["Local templates · No extra AI call","स्थानीय टेम्पलेट · अतिरिक्त AI कॉल नहीं"], packageHelp:["Editable preparation documents, not a lawyer-issued notice. Nothing is sent or filed. Review every statement and fill the placeholders.","संपादन योग्य तैयारी दस्तावेज़, वकील द्वारा जारी नोटिस नहीं। कुछ भेजा या दाखिल नहीं होता। हर कथन जाँचें और खाली स्थान भरें।"],
  documentLanguage:["Document language","दस्तावेज़ की भाषा"], provisional:["Allow a provisional draft with missing-detail placeholders","अधूरे विवरण के खाली स्थानों वाला अस्थायी मसौदा बनाएँ"], generate:["Generate complaint package","शिकायत के दस्तावेज़ बनाएँ"], regenerate:["Regenerate package (replaces edits)","फिर बनाएँ (आपके बदलाव बदलेंगे)"],
  outdated:["This draft may be outdated: case facts or document language changed. Your edits are preserved. Regenerate explicitly to replace them.","केस के तथ्य या दस्तावेज़ की भाषा बदली है; मसौदा पुराना हो सकता है। आपके बदलाव सुरक्षित हैं। बदलने के लिए स्पष्ट रूप से फिर बनाएँ।"],
  complaint:["Complaint to seller / company","विक्रेता / कंपनी को शिकायत"], nchSummary:["NCH preparation summary","NCH तैयारी सारांश"], nchHelp:["Not submitted to or officially validated by NCH.","NCH को भेजा नहीं गया है, न आधिकारिक रूप से सत्यापित है।"], downloadComplaint:["Download complaint · TXT","शिकायत डाउनलोड करें · TXT"], downloadSummary:["Download summary · TXT","सारांश डाउनलोड करें · TXT"],
  checklist:["Evidence checklist","साक्ष्य सूची"], evidenceHelp:["Suggestions to check, not mandatory legal requirements or confirmation that evidence exists.","जाँच के सुझाव, अनिवार्य कानूनी शर्तें या साक्ष्य मौजूद होने की पुष्टि नहीं।"], footer:["For Indian consumer refunds, defective products, non-delivery and related service complaints. Keep a copy of reviewed drafts before closing this page.","भारत में उपभोक्ता रिफंड, खराब उत्पाद, सामान न मिलने और संबंधित सेवाओं की शिकायतों के लिए। पेज बंद करने से पहले जाँचे गए मसौदों की प्रति रखें।"],
  unknown:["Not yet known","अभी अज्ञात"], noEntries:["No entries recorded","कोई प्रविष्टि दर्ज नहीं"], you:["YOU","आप"], assistant:["NYAYSAATHI","न्यायसाथी"],
  noGuidance:["Ask a consumer question in the conversation. Explanations appear only when supported by the checked official sources.","बातचीत में उपभोक्ता प्रश्न पूछें। जाँचे गए आधिकारिक स्रोतों से समर्थित होने पर ही व्याख्या दिखेगी।"], nextStep:["Practical next step","व्यावहारिक अगला कदम"], checked:["Checked","जाँच की तारीख"],
  reported:["You report having","आपके अनुसार उपलब्ध"], collect:["You may want to collect / check","इकट्ठा करने / जाँचने के सुझाव"], unknownEvidence:["Availability unknown","उपलब्धता अज्ञात"],
  initialReadiness:["Describe your grievance to prepare a draft. Missing facts will use placeholders.","मसौदा तैयार करने के लिए शिकायत बताएँ। अधूरे तथ्यों की जगह खाली स्थान होंगे।"], ready:["Ready to draft; review before sending.","मसौदा बनाने के लिए तैयार; भेजने से पहले जाँचें।"], missingReadiness:["Details are missing. Select the provisional option to draft with placeholders.","विवरण अधूरे हैं। खाली स्थानों वाला मसौदा बनाने के लिए अस्थायी विकल्प चुनें।"], insufficient:["More case information is needed. A provisional draft may be available.","और केस विवरण चाहिए। अस्थायी मसौदा उपलब्ध हो सकता है।"], blocked:["Document generation and downloads are disabled for this scope or professional-review safety case.","इस दायरे या पेशेवर जाँच वाले मामले में दस्तावेज़ बनाना और डाउनलोड बंद हैं।"],
  processing:["Collecting case details…","केस विवरण जुटाया जा रहा है…"], transcribing:["Transcribing audio…","ऑडियो का लिप्यंतरण हो रहा है…"], generating:["Preparing local templates…","स्थानीय टेम्पलेट तैयार हो रहे हैं…"], recorded:["Recording ready. Preview before transcribing.","रिकॉर्डिंग तैयार है। लिप्यंतरण से पहले सुनें।"], recording:["Recording…","रिकॉर्डिंग हो रही है…"], permission:["Waiting for microphone permission…","माइक्रोफ़ोन की अनुमति की प्रतीक्षा…"], sentVoice:["Transcript already sent. Record a new message or use text chat.","पाठ पहले ही भेजा गया है। नया संदेश रिकॉर्ड करें या लिखें।"],
  micError:["Microphone unavailable or permission denied. Check browser permissions or use text chat.","माइक्रोफ़ोन उपलब्ध नहीं या अनुमति नहीं मिली। ब्राउज़र की अनुमति जाँचें या लिखकर संदेश भेजें।"], browserError:["This browser cannot record PCM audio here. Use a recent browser on localhost/HTTPS, or type your message.","यह ब्राउज़र यहाँ PCM ऑडियो रिकॉर्ड नहीं कर सकता। localhost/HTTPS पर नया ब्राउज़र इस्तेमाल करें या संदेश लिखें।"], audioError:["The recording could not be prepared. Try a shorter recording or use text chat.","रिकॉर्डिंग तैयार नहीं हो सकी। छोटा संदेश रिकॉर्ड करें या लिखें।"], networkError:["Request failed or timed out. Your existing case is kept. No automatic retry was made.","अनुरोध विफल हुआ या समय समाप्त हुआ। मौजूदा केस सुरक्षित है। अपने आप दोबारा प्रयास नहीं हुआ।"],
};
const errorHindi = {
  missing_configuration:"सर्वर पर Gemini की API key और मॉडल कॉन्फ़िगरेशन जाँचें।", rate_limit:"प्रदाता की उपयोग सीमा पूरी हुई। फिर प्रयास करने से पहले कोटा जाँचें।", timeout:"प्रदाता का समय समाप्त हुआ। अपने आप दोबारा प्रयास नहीं हुआ।", model_error:"प्रदाता अनुरोध पूरा नहीं कर सका। मॉडल की पहुँच और कनेक्शन जाँचें।", invalid_output:"उत्तर सुरक्षित रूप से सत्यापित नहीं हो सका। पिछला केस सुरक्षित है।", unintelligible_audio:"उपयोगी आवाज़ का पाठ नहीं मिला। फिर रिकॉर्ड करें या लिखें।", invalid_audio:"WAV रिकॉर्डिंग अमान्य या अधूरी है।", unsupported_audio:"केवल 16-bit PCM WAV ऑडियो स्वीकार है।", audio_too_long:"रिकॉर्डिंग अधिकतम 60 सेकंड होनी चाहिए।", audio_too_large:"रिकॉर्डिंग 2 MB से छोटी होनी चाहिए।", request_too_large:"अनुरोध आकार सीमा से बड़ा है। छोटा संदेश या रिकॉर्डिंग दें।", invalid_request:"अनुरोध अमान्य है या केस/बातचीत की सीमा से बड़ा है।",
};
const fields = {
  issue_type:["Issue type","समस्या की श्रेणी"], company_or_seller:["Company / seller","कंपनी / विक्रेता"], amount_inr:["Recorded amount","दर्ज राशि"], incident_date:["Incident date","घटना की तारीख"], user_summary:["Your account","आपका विवरण"], timeline:["Timeline","घटनाक्रम"], evidence_available:["Reported evidence","बताया गया साक्ष्य"], desired_resolution:["Desired resolution","इच्छित समाधान"],
};
const state = {case:{}, messages:[], guidance:null, readiness:null, fingerprint:null, package:null, busy:false, recording:false, starting:false,
  voice:{blob:null, url:null, id:null, transcribed:false, submitted:new Set()}, recorder:null};
const language = () => $("language").value;
const t = (key) => translations[key]?.[language() === "hi" ? 1 : 0] || key;
const node = (tag, text, className) => { const element = document.createElement(tag); if (text !== undefined) element.textContent = text; if (className) element.className = className; return element; };
const showError = (error, voice = false) => { const target = $(voice ? "voice-error" : "request-error"); target.textContent = language() === "hi" && errorHindi[error.code] ? errorHindi[error.code] : error.message || t("networkError"); target.hidden = false; };

function boundedHistory() {
  const result = []; let count = 0;
  for (const message of state.messages.slice(-12).reverse()) {
    if (count + message.content.length > 24000) break;
    result.unshift({...message}); count += message.content.length;
  }
  return result;
}
async function api(path, body, audio = false) {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 55000);
  try {
    const response = await fetch(path, {method:"POST", headers:{"Content-Type":audio ? "audio/wav" : "application/json"}, body:audio ? body : JSON.stringify(body), signal:controller.signal, credentials:"same-origin"});
    const result = await response.json();
    if (!response.ok) throw result.error || {message:t("networkError")};
    return result;
  } catch (error) {
    if (error.code || (error.message && !(error instanceof Error))) throw error;
    throw {code:"network_error", message:t("networkError")};
  } finally { clearTimeout(timer); }
}
function setBusy(busy, label = "processing") {
  state.busy = busy; $("request-status").hidden = !busy; $("request-status").textContent = busy ? t(label) : "";
  $("request-error").hidden = true; updateControls();
}
function updateControls() {
  const locked = state.busy || state.recording || state.starting;
  $("send").disabled = locked; $("new-case").disabled = locked;
  $("record").disabled = state.busy || state.starting;
  $("record").textContent = t(state.recording ? "stopRecording" : "startRecording");
  $("transcribe").disabled = locked || state.voice.transcribed || state.voice.submitted.has(state.voice.id);
  $("send-voice").disabled = locked || !$("transcript").value.trim() || state.voice.submitted.has(state.voice.id);
  $("transcript").disabled = state.busy || state.voice.submitted.has(state.voice.id);
  $("generate").disabled = locked || !Object.keys(state.case).length || state.readiness?.status === "out_of_scope";
  for (const id of ["download-complaint","download-summary"]) $(id).disabled = state.busy || state.readiness?.status === "out_of_scope";
}
function renderMessages() {
  $("messages").replaceChildren(); $("empty-chat").hidden = state.messages.length > 0;
  for (const item of state.messages) {
    const article = node("article", undefined, `message ${item.role}`);
    article.append(node("div", t(item.role === "user" ? "you" : "assistant"), "message-label"), node("div", item.content, "message-body"));
    $("messages").append(article);
  }
  $("messages").scrollTop = $("messages").scrollHeight;
}
function renderCase() {
  $("case-fields").replaceChildren();
  for (const [key, labels] of Object.entries(fields)) {
    const value = state.case[key], unknown = value === null || value === undefined || value === "";
    let display = unknown ? t("unknown") : Array.isArray(value) ? (value.length ? value.join("\n") : t("noEntries")) : String(value);
    if (key === "amount_inr" && !unknown) display = `₹${value}`;
    $("case-fields").append(node("dt", labels[language() === "hi" ? 1 : 0]), node("dd", display, unknown ? "unknown" : ""));
  }
  const status = state.case.case_status || "not_started";
  $("case-status").textContent = ({not_started:["Not started","शुरू नहीं हुआ"],in_progress:["Intake in progress","विवरण जुट रहे हैं"],ready_for_review:["Review case facts","तथ्य जाँचें"]})[status]?.[language() === "hi" ? 1 : 0] || status;
  $("narrative-warning").hidden = !state.case.narrative_review_required;
  const missing = [...new Set([...(state.case.unanswered_questions || []), ...(state.case.evidence_missing || [])])];
  fillList($("missing-details"), missing.length ? missing : [t("noEntries")]);
}
function fillList(target, entries) { target.replaceChildren(...entries.map((item) => node("li", item))); }
function renderGuidance() {
  const container = $("guidance-content"); container.replaceChildren();
  if (!state.guidance) { container.append(node("p", t("noGuidance"), "muted small")); return; }
  if (!state.guidance.citations.length) { container.append(node("p", state.guidance.message, "alert")); return; }
  const official = new Set(["consumeraffairs.gov.in","consumerhelpline.gov.in","e-jagriti.gov.in","indiacode.nic.in","www.indiacode.nic.in"]);
  for (const citation of state.guidance.citations) {
    const card = node("article", undefined, "guidance-card"); card.append(node("p", citation.explanation));
    try {
      const url = new URL(citation.url);
      if (url.protocol !== "https:" || !official.has(url.hostname) || url.username || url.password || url.port) continue;
      const link = node("a", `${citation.source_id} · ${citation.title}`, "source-link");
      link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer"; card.append(link);
    } catch { continue; }
    card.append(node("p", `${citation.location} · ${t("checked")}: ${citation.date_checked}`, "small muted"), node("p", `${t("nextStep")}: ${citation.next_step}`, "guidance-next"), node("p", citation.limitation, "small muted"));
    container.append(card);
  }
}
function renderPackageStatus() {
  $("generate").textContent = t(state.package ? "regenerate" : "generate");
  const readinessKey = {ready:"ready",missing:"missingReadiness",insufficient:"insufficient",out_of_scope:"blocked"}[state.readiness?.status];
  $("readiness").textContent = t(readinessKey || "initialReadiness");
  $("outdated").hidden = !state.package || (state.package.fingerprint === state.fingerprint && state.package.language === $("document-language").value);
  updateControls();
}
function renderChecklist() {
  $("checklist").replaceChildren(); if (!state.package) return;
  for (const [key,label] of [["reported","reported"],["collect","collect"],["unknown","unknownEvidence"]]) {
    const group = node("div", undefined, "checklist-group"), list = node("ul", undefined, "plain-list");
    fillList(list, state.package.checklist[key].length ? state.package.checklist[key] : [t("noEntries")]);
    group.append(node("h3", t(label)), list); $("checklist").append(group);
  }
}
function translate() {
  document.documentElement.lang = language();
  document.querySelectorAll("[data-i18n]").forEach((element) => { element.textContent = t(element.dataset.i18n); });
  document.querySelectorAll("[data-placeholder]").forEach((element) => { element.placeholder = t(element.dataset.placeholder); });
  renderMessages(); renderCase(); renderGuidance(); renderPackageStatus(); renderChecklist();
}
async function submitMessage(text, voiceId = null) {
  text = text.trim(); if (!text || state.busy || state.recording || state.starting) return;
  if (voiceId && state.voice.submitted.has(voiceId)) return;
  const history = boundedHistory();
  if (voiceId) state.voice.submitted.add(voiceId);
  state.messages.push({role:"user",content:text}); state.guidance = null; $("message").value = "";
  renderMessages(); renderGuidance(); setBusy(true);
  try {
    const result = await api("/api/chat", {message:text, language:language(), case:state.case, history});
    state.case = result.case; state.guidance = result.guidance; state.readiness = result.readiness; state.fingerprint = result.fingerprint;
    if (result.reply) state.messages.push({role:"assistant",content:result.reply});
    renderMessages(); renderCase(); renderGuidance(); renderPackageStatus();
    if (result.error) showError(result.error);
  } catch (error) { showError(error); }
  finally {
    state.busy = false; $("request-status").hidden = true;
    if (voiceId) $("record-state").textContent = t("sentVoice");
    updateControls();
  }
}
$("chat-form").addEventListener("submit", (event) => { event.preventDefault(); submitMessage($("message").value); });
$("example").addEventListener("click", () => { $("message").value = language() === "hi" ? "₹2,999 के हेडफ़ोन खराब मिले और विक्रेता ने रिफंड देने से मना किया।" : "My ₹2,999 headphones arrived damaged and the seller refused a refund."; $("message").focus(); });
$("language").addEventListener("change", translate);
$("document-language").addEventListener("change", renderPackageStatus);
$("transcript").addEventListener("input", updateControls);
$("send-voice").addEventListener("click", () => submitMessage($("transcript").value, state.voice.id));

function clearVoice() {
  if (state.voice.url) URL.revokeObjectURL(state.voice.url);
  state.voice.blob = null; state.voice.url = null; state.voice.id = null; state.voice.transcribed = false;
  $("audio-preview").pause(); $("audio-preview").removeAttribute("src"); $("audio-preview").hidden = true;
  $("transcript").value = ""; $("transcript-section").hidden = true; $("transcribe").hidden = true;
  $("voice-error").hidden = true; $("record-state").textContent = ""; $("record-time").textContent = "00:00";
}
function recordingError(error) {
  state.recording = false; state.starting = false;
  $("record-time").classList.remove("recording");
  showError({message:t(error?.message === "unsupported_browser" ? "browserError" : error?.name === "NotAllowedError" || error?.name === "NotFoundError" ? "micError" : "audioError")}, true);
  updateControls();
}
async function finishedRecording(blob) {
  try {
    state.voice.blob = blob;
    const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
    state.voice.id = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2,"0")).join("");
    state.voice.url = URL.createObjectURL(blob); $("audio-preview").src = state.voice.url;
    $("audio-preview").hidden = false; $("transcribe").hidden = false; $("record-state").textContent = t("recorded");
    state.recording = false; $("record-time").classList.remove("recording"); updateControls();
  } catch (error) { recordingError(error); }
}
$("record").addEventListener("click", async () => {
  if (state.busy || state.starting) return;
  if (state.recording) { try { await state.recorder.stop(); } catch (error) { recordingError(error); } return; }
  clearVoice(); state.starting = true; $("record-state").textContent = t("permission"); updateControls();
  state.recorder = new WavRecorder((seconds) => {
    $("record-time").textContent = [Math.floor(seconds / 60), Math.floor(seconds % 60)].map((part) => String(part).padStart(2,"0")).join(":");
  }, finishedRecording, recordingError);
  try {
    await state.recorder.start(); state.recording = true; state.starting = false;
    $("record-state").textContent = t("recording"); $("record-time").classList.add("recording"); updateControls();
  } catch (error) { recordingError(error); }
});
$("transcribe").addEventListener("click", async () => {
  if (state.busy || !state.voice.blob || state.voice.transcribed || state.voice.submitted.has(state.voice.id)) return;
  setBusy(true, "transcribing"); $("voice-error").hidden = true;
  try {
    const result = await api("/api/transcribe", state.voice.blob, true);
    $("transcript").value = result.transcript; $("transcript-section").hidden = false; state.voice.transcribed = true;
  } catch (error) { showError(error, true); }
  finally { state.busy = false; $("request-status").hidden = true; updateControls(); }
});
$("generate").addEventListener("click", async () => {
  if (state.busy || state.recording || state.starting) return;
  setBusy(true, "generating");
  try {
    const result = await api("/api/action-package", {case:state.case, history:boundedHistory(), language:$("document-language").value, provisional:$("provisional").checked});
    state.readiness = result.readiness;
    if (result.package) {
      state.package = result.package; state.fingerprint = result.package.fingerprint;
      // The only assignment to existing document editors, other than explicit reset.
      $("complaint").value = result.package.complaint; $("nch-summary").value = result.package.summary;
      $("documents").hidden = false; renderChecklist();
    }
    renderPackageStatus();
  } catch (error) { showError(error); }
  finally { state.busy = false; $("request-status").hidden = true; updateControls(); }
});
function download(editor, name) {
  if (!state.package || state.busy || state.readiness?.status === "out_of_scope") return;
  const url = URL.createObjectURL(new Blob(["\ufeff", $(editor).value], {type:"text/plain;charset=utf-8"}));
  const anchor = node("a"); anchor.href = url; anchor.download = `nyaysaathi_${name}_${state.package.language}.txt`;
  document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("download-complaint").addEventListener("click", () => download("complaint", "complaint"));
$("download-summary").addEventListener("click", () => download("nch-summary", "nch_summary"));
$("new-case").addEventListener("click", () => {
  if (state.busy || state.recording || state.starting) return;
  clearVoice(); state.voice.submitted.clear(); state.case = {}; state.messages = []; state.guidance = null;
  state.readiness = null; state.fingerprint = null; state.package = null;
  $("message").value = ""; $("complaint").value = ""; $("nch-summary").value = "";
  $("documents").hidden = true; $("provisional").checked = false; $("request-error").hidden = true;
  translate();
});
window.addEventListener("pagehide", () => { state.recorder?.dispose().catch(() => {}); if (state.voice.url) URL.revokeObjectURL(state.voice.url); });
translate();
