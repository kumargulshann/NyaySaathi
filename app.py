"""Consumer case intake UI; provider calls and case merging live in the package."""

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from nyaysaathi.gemini import GeminiProvider
from nyaysaathi.intake import IntakeError, run_turn
from nyaysaathi.models import CaseFile
from nyaysaathi.settings import Settings, get_settings
from nyaysaathi.transcription import TranscriptionError, transcribe_audio, validate_audio
from nyaysaathi.consistency import REVIEW_NOTICE, protect_narratives
from nyaysaathi.action_package import (
    FIELDS, READINESS_LABELS, assess_readiness, case_fingerprint, download_bytes, generate_package,
)


st.set_page_config(page_title="NyaySaathi AI", page_icon="⚖️", layout="wide")

language = st.sidebar.selectbox(
    "Interface language / इंटरफ़ेस की भाषा", ["English", "हिन्दी"], key="ui_language"
)
is_hindi = language == "हिन्दी"


def text(english: str, hindi: str) -> str:
    return hindi if is_hindi else english


try:
    secret_values = dict(st.secrets)
except (FileNotFoundError, StreamlitSecretNotFoundError):
    # Missing secrets are normal locally; .env/environment remain available.
    secret_values = {}
try:
    settings = get_settings(secret_values)
except OSError:
    settings = Settings()
    st.error(text("Could not read local configuration. Check file permissions.",
                  "स्थानीय कॉन्फ़िगरेशन पढ़ा नहीं जा सका। फ़ाइल की अनुमति जाँचें।"))

ERROR_MESSAGES = {
    "missing_configuration": (
        "Set GEMINI_API_KEY and GEMINI_MODEL in .env, environment variables, or Streamlit secrets.",
        ".env, पर्यावरण चर या Streamlit secrets में GEMINI_API_KEY और GEMINI_MODEL सेट करें।",
    ),
    "rate_limit": (
        "Gemini's rate limit or quota was reached. Wait and check your quota before sending again.",
        "Gemini की उपयोग सीमा या कोटा पूरा हो गया है। दोबारा भेजने से पहले प्रतीक्षा करें और कोटा जाँचें।",
    ),
    "timeout": (
        "Gemini timed out. No automatic retry was made; you may send the message again.",
        "Gemini का समय समाप्त हो गया। अपने आप दोबारा प्रयास नहीं हुआ; आप संदेश फिर भेज सकते हैं।",
    ),
    "invalid_output": (
        "The proposed update could not be safely validated. Please clarify or resend your message.",
        "प्रस्तावित बदलाव की सुरक्षित जाँच नहीं हो सकी। कृपया संदेश स्पष्ट करें या फिर भेजें।",
    ),
    "model_error": (
        "Gemini could not complete intake. Check your key, model access, and connection before trying again.",
        "Gemini विवरण नहीं जुटा सका। दोबारा कोशिश से पहले API key, मॉडल की पहुँच और कनेक्शन जाँचें।",
    ),
}

if "messages" not in st.session_state:
    st.session_state.messages = []
if "case_file" not in st.session_state:
    st.session_state.case_file = CaseFile()
st.session_state.case_file = protect_narratives(st.session_state.case_file)
if "last_error" not in st.session_state:
    st.session_state.last_error = None
if "legal_guidance" not in st.session_state:
    st.session_state.legal_guidance = None
if "action_package" not in st.session_state:
    st.session_state.action_package = None
if "case_generation" not in st.session_state:
    st.session_state.case_generation = 0
if "voice_submitted_ids" not in st.session_state:
    st.session_state.voice_submitted_ids = set()


def start_new_case() -> None:
    """Explicitly discard this session's case, drafts and voice widget state."""
    st.session_state.case_generation += 1
    for key in list(st.session_state):
        if key.startswith(("voice_", "action_")):
            del st.session_state[key]
    st.session_state.update(
        messages=[], case_file=CaseFile(), last_error=None, legal_guidance=None,
        action_package=None, voice_submitted_ids=set(),
    )


st.sidebar.button(text("Start a new case", "नया केस शुरू करें"), key="new_case", on_click=start_new_case)


def submit_message(message: str) -> None:
    """Text and user-approved transcripts share exactly the same intake path."""
    st.session_state.messages.append({"role": "user", "content": message})
    st.session_state.last_error = None
    st.session_state.legal_guidance = None
    try:
        with st.spinner(text("Collecting case details…", "केस का विवरण जुटाया जा रहा है…")):
            turn = run_turn(
                st.session_state.case_file, st.session_state.messages,
                "hi" if is_hindi else "en", GeminiProvider(settings),
            )
        st.session_state.case_file = turn.case
        st.session_state.legal_guidance = turn.guidance
        st.session_state.last_error = turn.intake_error
        st.session_state.messages.append({"role": "assistant", "content": turn.reply})
    except IntakeError as error:
        st.session_state.last_error = error.code
    st.rerun()


VOICE_ERRORS = {
    "empty_audio": ("The recording is empty. Record again.", "रिकॉर्डिंग खाली है। फिर रिकॉर्ड करें।"),
    "audio_too_large": ("Recording must be below 2 MB. Record a shorter message.", "रिकॉर्डिंग 2 MB से छोटी होनी चाहिए। छोटा संदेश रिकॉर्ड करें।"),
    "audio_too_long": ("Recording exceeds 60 seconds. Record a shorter message.", "रिकॉर्डिंग 60 सेकंड से लंबी है। छोटा संदेश रिकॉर्ड करें।"),
    "unsupported_audio": ("Only 16-bit PCM WAV recordings are supported.", "केवल 16-bit PCM WAV रिकॉर्डिंग समर्थित हैं।"),
    "invalid_audio": ("Invalid or incomplete WAV audio. Record again.", "WAV ऑडियो अमान्य या अधूरा है। फिर रिकॉर्ड करें।"),
    "silent_audio": ("The recording contains only silence. Check your microphone and preview.", "रिकॉर्डिंग में केवल मौन है। माइक्रोफ़ोन और रिकॉर्डिंग जाँचें।"),
    "empty_transcription": ("The provider returned no transcript; this does not confirm silence. Check the preview and try again later.", "प्रदाता ने पाठ नहीं लौटाया; इससे मौन की पुष्टि नहीं होती। रिकॉर्डिंग सुनें और बाद में प्रयास करें।"),
    "unintelligible_audio": ("No usable transcript: speech was absent or marked unclear. Record again or type your message.", "उपयोगी पाठ नहीं मिला: आवाज़ अनुपस्थित या अस्पष्ट थी। फिर रिकॉर्ड करें या संदेश लिखें।"),
    "missing_configuration": ("Set GEMINI_API_KEY to enable transcription. Check GEMINI_TRANSCRIPTION_MODEL if overridden.", "लिप्यंतरण के लिए GEMINI_API_KEY सेट करें। बदला हो तो GEMINI_TRANSCRIPTION_MODEL भी जाँचें।"),
    "rate_limit": ("Transcription quota/rate limit reached. Check your quota before trying again.", "लिप्यंतरण की उपयोग सीमा पूरी हुई। फिर प्रयास करने से पहले कोटा जाँचें।"),
    "timeout": ("Transcription timed out; no retry was made. You can retry explicitly or type instead.", "लिप्यंतरण का समय समाप्त हुआ; अपने आप फिर प्रयास नहीं हुआ। दोबारा बटन दबाएँ या लिखें।"),
    "invalid_output": ("The provider returned an incomplete or invalid transcript. Nothing was sent to intake.", "प्रदाता से अधूरा या अमान्य पाठ मिला। केस के लिए कुछ नहीं भेजा गया।"),
    "model_error": ("Transcription failed. Check model access, configuration and connection. Nothing was sent to intake.", "लिप्यंतरण विफल हुआ। मॉडल की पहुँच, कॉन्फ़िगरेशन और कनेक्शन जाँचें। केस के लिए कुछ नहीं भेजा गया।"),
}

st.title("NyaySaathi AI — न्यायसाथी")
st.write(text(
    "A multilingual consumer grievance assistant for refunds, online shopping, "
    "and consumer services in India.",
    "भारत में रिफंड, ऑनलाइन खरीदारी और उपभोक्ता सेवाओं की शिकायतों के लिए "
    "एक बहुभाषी सहायक।",
))
st.warning(text(
    "Legal information assistance only. This is not a substitute for a qualified lawyer.",
    "केवल कानूनी जानकारी में सहायता। यह योग्य वकील की सलाह का विकल्प नहीं है।",
))
st.info(text(
    "Gemini collects case details and asks one follow-up question at a time. "
    "Consumer-law information is limited to checked official source records. "
    "The Action Package uses local templates and makes no additional AI requests.",
    "Gemini केस का विवरण जुटाता है और एक बार में एक प्रश्न पूछता है। "
    "उपभोक्ता कानून की जानकारी जाँचे गए आधिकारिक स्रोतों तक सीमित है। "
    "Action Package स्थानीय टेम्पलेट से बनता है; इसके लिए अतिरिक्त AI अनुरोध नहीं होते।",
))
if st.session_state.last_error:
    st.error(text(*ERROR_MESSAGES[st.session_state.last_error]) + " " + text(
        "Your message is kept; the case was not changed.",
        "आपका संदेश सुरक्षित है; केस में कोई बदलाव नहीं किया गया।",
    ))

conversation, case_panel = st.columns([3, 2])

with conversation:
    st.subheader(text("Conversation", "बातचीत"))
    st.caption(text(
        "Write in English, Hindi, or Hinglish. Your messages stay across reruns "
        "in this session; a browser refresh or server restart may clear them. "
        "Submitting sends the text conversation and case details to Google's Gemini API.",
        "अंग्रेज़ी, हिन्दी या हिंग्लिश में लिखें। इसी सत्र में संदेश बने रहते हैं; "
        "ब्राउज़र रीफ़्रेश या सर्वर रीस्टार्ट होने पर मिट सकते हैं। संदेश भेजने पर बातचीत "
        "का पाठ और केस का विवरण Google के Gemini API को भेजा जाता है।",
    ))
    history = st.container(border=True)
    with history:
        if not st.session_state.messages:
            st.caption(text("No messages yet.", "अभी कोई संदेश नहीं है।"))
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.text(message["content"])

    prompt = st.chat_input(
        text("Describe your consumer problem…", "अपनी उपभोक्ता समस्या लिखें…"),
        key="problem_input",
    )
    if prompt and prompt.strip():
        submit_message(prompt)

    st.subheader(text("Voice input", "आवाज़ से संदेश"))
    recording = st.audio_input(
        text("Record your problem (stop within 60 seconds)", "अपनी समस्या रिकॉर्ड करें (60 सेकंड में रोकें)"),
        key=f"voice_input_{st.session_state.case_generation}", sample_rate=16000,
    )
    st.caption(text(
        "English, Hindi or Hinglish. 16-bit PCM WAV only, at most 60 seconds and below 2 MB. "
        "Audio goes to Google only when you click Transcribe Audio. Review names, amounts and dates before sending. "
        "Use fictional details for this demo. If microphone permission is unavailable, type above.",
        "अंग्रेज़ी, हिन्दी या हिंग्लिश। केवल 16-bit PCM WAV, अधिकतम 60 सेकंड और 2 MB से छोटा। "
        "लिप्यंतरण बटन दबाने पर ही ऑडियो Google को जाएगा। भेजने से पहले नाम, राशि और तारीख जाँचें। "
        "डेमो में काल्पनिक विवरण दें। माइक्रोफ़ोन की अनुमति न मिले तो ऊपर लिखें।",
    ))
    audio_info, audio_bytes, audio_error = None, None, None
    if recording is not None:
        audio_bytes = recording.getvalue()
        try:
            audio_info = validate_audio(audio_bytes, recording.type)
        except TranscriptionError as error:
            audio_error = error.code
    recording_id = audio_info.recording_id if audio_info else None
    if st.session_state.get("voice_recording_id") != recording_id:
        for key in ("voice_result", "voice_transcript", "voice_error"):
            st.session_state.pop(key, None)
        st.session_state.voice_recording_id = recording_id
    if audio_error:
        st.error(text(*VOICE_ERRORS[audio_error]))
    if audio_info:
        st.audio(audio_bytes, format=audio_info.mime_type)
        st.info(text(
            f"Recording ready ({audio_info.duration_seconds:.1f} seconds). Nothing has been sent to intake.",
            f"रिकॉर्डिंग तैयार है ({audio_info.duration_seconds:.1f} सेकंड)। केस के लिए कुछ नहीं भेजा गया है।",
        ))
        submitted = recording_id in st.session_state.voice_submitted_ids
        if st.button(
            text("Transcribe Audio", "ऑडियो का लिप्यंतरण करें"), key="transcribe_audio",
            disabled=st.session_state.get("voice_result") is not None or submitted,
        ):
            st.session_state.voice_error = None
            try:
                with st.spinner(text("Transcribing audio…", "ऑडियो का लिप्यंतरण हो रहा है…")):
                    result = transcribe_audio(audio_bytes, audio_info.mime_type, settings)
                st.session_state.voice_result = result
                st.session_state.voice_transcript = result.transcript
            except TranscriptionError as error:
                st.session_state.voice_error = error.code
            st.rerun()
        if st.session_state.get("voice_error"):
            st.error(text(*VOICE_ERRORS[st.session_state.voice_error]))
        if st.session_state.get("voice_result") is not None:
            st.success(text("Transcript ready. Review and edit before sending.", "पाठ तैयार है। भेजने से पहले जाँचें और सुधारें।"))
            approved_text = st.text_area(
                text("Review and edit transcript", "पाठ जाँचें और सुधारें"),
                key="voice_transcript", max_chars=12000, disabled=submitted,
            )
            st.caption(text(
                "Only the text you approve is processed by case intake; the intake assistant does not receive audio.",
                "केस में केवल आपके द्वारा स्वीकृत पाठ का उपयोग होता है; केस सहायक को ऑडियो नहीं मिलता।",
            ))
            if submitted:
                st.info(text("This recording's transcript was already sent. Record a new message or use text chat.", "इस रिकॉर्डिंग का पाठ पहले ही भेजा गया है। नया संदेश रिकॉर्ड करें या लिखें।"))
            if st.button(
                text("Send to NyaySaathi", "न्यायसाथी को भेजें"), key="send_voice",
                disabled=submitted or not approved_text.strip(),
            ):
                # Consume before calling intake, including on failure: reruns never resend.
                st.session_state.voice_submitted_ids.add(recording_id)
                submit_message(approved_text.strip())

with case_panel:
    st.subheader(text("Case File", "केस फ़ाइल"))
    st.caption(text(
        "Your evolving case. null means unknown; [] means no entries recorded. "
        "Facts are user-reported, not independently verified. Review and explicitly correct any mistakes.",
        "आपके केस का विवरण। null का अर्थ अज्ञात है; [] का अर्थ कोई प्रविष्टि दर्ज नहीं है। "
        "तथ्य उपयोगकर्ता द्वारा बताए गए हैं; स्वतंत्र रूप से सत्यापित नहीं हैं। त्रुटियों को स्पष्ट रूप से सुधारें।",
    ))
    st.json(st.session_state.case_file.model_dump(mode="json"))
    if st.session_state.case_file.narrative_review_required:
        st.warning(REVIEW_NOTICE["hi" if is_hindi else "en"])

st.subheader(text("Legal Guidance / Your Options", "कानूनी जानकारी / आपके विकल्प"))
guidance = st.session_state.legal_guidance
if guidance is None:
    st.caption(text(
        "Ask a consumer question in chat. Options appear only when supported by the checked sources.",
        "बातचीत में उपभोक्ता संबंधी प्रश्न पूछें। जाँचे गए स्रोतों से समर्थित होने पर ही विकल्प दिखेंगे।",
    ))
elif guidance.entries:
    st.caption(text(
        "AI-selected explanations from checked official records. Your case facts remain unverified user allegations.",
        "जाँचे गए आधिकारिक रिकॉर्ड से AI द्वारा चुनी गई व्याख्याएँ। आपके केस के तथ्य असत्यापित उपयोगकर्ता कथन हैं।",
    ))
    account = st.session_state.case_file.user_summary or next(
        (message["content"] for message in reversed(st.session_state.messages) if message["role"] == "user"), "",
    )
    if account:
        st.write(text("Based on your account: ", "आपके बताए अनुसार: ") + account)
    for entry in guidance.entries:
        st.write(entry.guidance[guidance.language])
        st.markdown(f"[{entry.source_id} — {entry.source_title}]({entry.source_url})")
        st.caption(f"{entry.provision_or_location} · {text('Checked', 'जाँच की तारीख')}: {entry.date_checked}")
        st.write(text("Practical next step: ", "व्यावहारिक अगला कदम: ") + entry.next_step[guidance.language])
        st.caption(entry.limitation[guidance.language])
    if st.session_state.case_file.unanswered_questions:
        st.write(text("Important missing details:", "महत्वपूर्ण अज्ञात विवरण:"))
        for question in st.session_state.case_file.unanswered_questions[:5]:
            st.text(question)
else:
    # Safety/uncertainty notices contain no purported verified legal conclusion.
    st.info(guidance.message)

st.subheader(text("Action Package", "कार्रवाई के लिए दस्तावेज़"))
st.caption(text(
    "Local templates only; no Gemini calls. Review every fact and placeholder before use. "
    "These are consumer preparation documents, not a lawyer-issued legal notice. Nothing is sent or filed.",
    "केवल स्थानीय टेम्पलेट; कोई Gemini कॉल नहीं। उपयोग से पहले हर तथ्य और खाली स्थान की समीक्षा करें। "
    "ये उपभोक्ता तैयारी दस्तावेज़ हैं, वकील द्वारा जारी कानूनी नोटिस नहीं। कुछ भेजा या दाखिल नहीं किया जाता।",
))
document_language = st.selectbox(
    text("Formal document language", "औपचारिक दस्तावेज़ की भाषा"),
    ["English", "हिन्दी"],
    index=1 if st.session_state.case_file.user_language == "hi" else 0,
    key="action_language",
)
doc_language = "hi" if document_language == "हिन्दी" else "en"
st.caption(text(
    "Hinglish users can choose either template. Case wording is retained as supplied; it is not automatically translated. "
    "The generic incident date is not assumed to be the purchase date.",
    "हिंग्लिश उपयोगकर्ता कोई भी टेम्पलेट चुन सकते हैं। केस की भाषा जैसी दी गई है वैसी रहेगी; अपने आप अनुवाद नहीं होगा। "
    "घटना की तारीख को खरीद की तारीख नहीं माना जाता।",
))
scope_blocked = guidance is not None and guidance.status in ("out_of_scope", "urgent_notice", "threat_or_crime")
readiness = assess_readiness(st.session_state.case_file, out_of_scope=scope_blocked)
st.write(text("Document readiness: ", "दस्तावेज़ की तैयारी: ") + READINESS_LABELS[readiness.status]["hi" if is_hindi else "en"])
if readiness.missing:
    st.caption(text("Missing/review: ", "अधूरी जानकारी/समीक्षा: ") + ", ".join(
        FIELDS[name]["hi" if is_hindi else "en"] for name in readiness.missing
    ))
if "narrative" in readiness.review:
    st.warning(REVIEW_NOTICE["hi" if is_hindi else "en"])
elif readiness.review:
    st.warning(text(
        "Some text contains legal claims or non-neutral wording and will be replaced with review placeholders.",
        "कुछ विवरण में कानूनी दावे या अनुचित भाषा है; उनकी जगह समीक्षा के लिए खाली स्थान दिए जाएँगे।",
    ))
if readiness.status == "out_of_scope":
    st.warning(text(
        "Generation and downloads are disabled for out-of-scope or professional-review safety cases. Any earlier edits remain below.",
        "दायरे से बाहर या पेशेवर जाँच वाले मामलों में दस्तावेज़ बनाना और डाउनलोड बंद हैं। पहले किए बदलाव नीचे सुरक्षित हैं।",
    ))
provisional = False
if readiness.status in ("missing", "insufficient"):
    provisional = st.checkbox(
        text("Create a provisional draft with clearly marked placeholders", "स्पष्ट खाली स्थानों के साथ अस्थायी मसौदा बनाएँ"),
        key="action_provisional", disabled=not readiness.provisional_allowed,
    )
package = st.session_state.action_package
if st.button(
    text("Regenerate package (replaces your edits)", "दस्तावेज़ फिर बनाएँ (आपके बदलाव बदलेंगे)") if package else
    text("Generate complaint package", "शिकायत के दस्तावेज़ बनाएँ"),
    key="generate_action_package",
    disabled=readiness.status == "out_of_scope" or not readiness.provisional_allowed or
    (readiness.status != "ready" and not provisional),
):
    package = generate_package(
        st.session_state.case_file, doc_language, provisional=provisional, out_of_scope=scope_blocked,
    )
    st.session_state.action_package = package
    # Assign ONLY after an explicit button action, before creating the editors.
    st.session_state.action_complaint_text = package.complaint
    st.session_state.action_summary_text = package.summary
    st.rerun()  # Show the explicit regeneration/replacement label immediately.
if package is not None:
    if package.fingerprint != case_fingerprint(st.session_state.case_file) or package.language != doc_language:
        st.warning(text(
            "This package may be outdated: case facts or the selected document language changed. "
            "Your edits are preserved. Regenerate explicitly to replace them.",
            "केस के तथ्य या चुनी गई दस्तावेज़ भाषा बदली है; दस्तावेज़ पुराने हो सकते हैं। "
            "आपके बदलाव सुरक्षित हैं। उन्हें बदलने के लिए स्पष्ट रूप से फिर बनाएँ।",
        ))
    st.caption(text(
        "Ready to draft means core case details are present, not ready to send. Fill [Order ID], product/service, purchase date, name/contact and any other placeholders. "
        "The recorded amount does not by itself confirm a payment.",
        "मसौदा बनाने के लिए तैयार होने का अर्थ भेजने के लिए तैयार होना नहीं है। ऑर्डर आईडी, उत्पाद/सेवा, खरीद की तारीख, नाम/संपर्क और अन्य खाली स्थान भरें। "
        "केवल दर्ज राशि से भुगतान की पुष्टि नहीं होती।",
    ))
    st.caption(text(
        "Commit edits by leaving the field or pressing Ctrl+Enter before downloading.",
        "डाउनलोड से पहले फ़ील्ड से बाहर क्लिक करें या Ctrl+Enter दबाकर बदलाव सहेजें।",
    ))
    complaint_text = st.text_area(text("Editable complaint to seller/company", "विक्रेता/कंपनी के लिए संपादन योग्य शिकायत"),
                                  key="action_complaint_text", height=340)
    st.download_button(text("Download complaint (.txt)", "शिकायत डाउनलोड करें (.txt)"),
                       data=download_bytes(complaint_text), file_name=f"nyaysaathi_complaint_{package.language}.txt",
                       mime="text/plain; charset=utf-8", key="download_action_complaint", disabled=readiness.status == "out_of_scope")
    st.info(text(
        "NCH preparation summary only: not automatically submitted and not officially validated.",
        "यह केवल NCH की तैयारी का सारांश है: अपने आप प्रस्तुत नहीं हुआ और आधिकारिक रूप से सत्यापित नहीं है।",
    ))
    summary_text = st.text_area(text("Editable NCH preparation summary", "NCH के लिए संपादन योग्य तैयारी सारांश"),
                                key="action_summary_text", height=300)
    st.download_button(text("Download summary (.txt)", "सारांश डाउनलोड करें (.txt)"),
                       data=download_bytes(summary_text), file_name=f"nyaysaathi_nch_summary_{package.language}.txt",
                       mime="text/plain; charset=utf-8", key="download_action_summary", disabled=readiness.status == "out_of_scope")
    st.write(text("Personalized evidence checklist", "आपके केस के लिए साक्ष्य सूची"))
    st.caption(text(
        "Potentially useful items, not a mandatory legal checklist. Suggested items are not confirmed available; none have been inspected.",
        "ये संभावित उपयोगी चीज़ें हैं, अनिवार्य कानूनी सूची नहीं। सुझाए गए साक्ष्यों की उपलब्धता की पुष्टि नहीं हुई है; कोई साक्ष्य जाँचा नहीं गया है।",
    ))
    for heading, items in (
        (text("You report having", "आपके अनुसार उपलब्ध"), package.checklist.reported),
        (text("You may want to collect/check", "आप जुटाने/जाँचने पर विचार कर सकते हैं"), package.checklist.collect),
        (text("Other standard items: availability unknown", "अन्य सामान्य चीज़ें: उपलब्धता अज्ञात"), package.checklist.unknown),
    ):
        st.write(heading)
        st.text("\n".join(f"- {item}" for item in items) or text("No entries recorded in this group.", "इस समूह में कोई प्रविष्टि दर्ज नहीं है।"))
    with st.expander(text("Copy-ready text", "कॉपी करने योग्य पाठ")):
        st.caption(text("Copy the reviewed text; download buttons use your current edits.", "समीक्षा के बाद पाठ कॉपी करें; डाउनलोड में आपके वर्तमान बदलाव शामिल होते हैं।"))
        st.code(complaint_text, language=None)
        st.code(summary_text, language=None)

st.subheader(text("Next Steps", "अगले कदम"))
st.write(text(
    "1. Describe your problem in the conversation.\n"
    "2. Answer the follow-up question and review your Case File.\n"
    "3. Explicitly correct any inaccurate detail and review the sources and limitations "
    "under Your Options. Review and download an Action Package when ready.",
    "1. बातचीत में अपनी समस्या लिखें।\n"
    "2. अगले प्रश्न का उत्तर दें और अपनी केस फ़ाइल देखें।\n"
    "3. गलत विवरण को स्पष्ट रूप से सुधारें और आपके विकल्प में स्रोत तथा सीमाएँ पढ़ें। "
    "तैयार होने पर कार्रवाई दस्तावेज़ों की समीक्षा करें और डाउनलोड करें।",
))
st.sidebar.caption(text(
    "One Gemini request per submitted message; no automatic retries. "
    "Set both GEMINI_API_KEY and GEMINI_MODEL to enable intake.",
    "हर भेजे गए संदेश पर एक Gemini अनुरोध; अपने आप दोबारा प्रयास नहीं। "
    "विवरण जुटाने के लिए GEMINI_API_KEY और GEMINI_MODEL दोनों सेट करें।",
))
if not settings.gemini_api_key or not settings.gemini_model:
    st.sidebar.warning(text("Gemini is not configured yet.", "Gemini अभी कॉन्फ़िगर नहीं है।"))
