# NyaySaathi AI · Walkthrough script

Aim for **2:45–3:00** including clicks. Rehearse once, use your own phrasing, and use fictional details on screen. Bracketed lines are screen cues. Record the successful path you actually observe.

## 0:00–0:25 · Problem and user

[Open the public prototype and start a new case.]

“I chose Problem 2. NyaySaathi is for someone in India who ordered something online and now has a damaged product, missing delivery or refund dispute. I wanted to make it easier to turn that story into a case they can review and a complaint they can edit.”

## 0:25–1:00 · Text or voice and the Case File

[Paste the fictional example below. While intake runs, point out the voice controls, or show a short recording and its editable transcript if it fits your rehearsal.]

“You can type or speak in English, Hindi or Hinglish. I tried transcription manually in all three. The user reviews the transcript before sending it. Here the Case File should capture the washing machine, eighteen thousand rupees and the three evidence items. The refusal belongs in the timeline. The assistant still asks the user to confirm the seller and remedy.”

## 1:00–1:35 · Guidance and documents

[Show the actual extracted fields and an official source link. Choose the provisional option and generate the Action Package. Point to the unknown year and seller and remedy placeholders.]

“The options panel shows a checked explanation and its official source. The complaint and National Consumer Helpline summary are editable. Here the year, seller and remedy can stay open. The checklist separates what the user reports having from useful items to look for. The user decides what to send.”

## 1:35–2:15 · How it works

[Keep the draft in view or briefly show the architecture in the solution PDF.]

“Gemini proposes case facts, a follow-up and relevant source selections. Python checks the quotes and the structured changes. A legal statement has to match a record retrieved for this turn. The server signs the Case File, and templates produce the documents without another model call. I can swap Gemini models and keep the same checks.”

## 2:15–2:55 · What failed and what I learned

[Show the evaluation report and point to T05.]

“I ran ten fictional scenarios with twelve live requests. Eight passed the predefined checks. One draft repeated two thousand rupees after the amount had been corrected to twenty-five hundred. The fix clears stale prose, and the offline replay verified that behavior. I also tested a purchase-year correction on the deployed app. Chat moved on to useful follow-up responses. These were small tests, and the guidance still needs review.”

## 2:55–3:00 · Close

“That’s NyaySaathi: a starting point for preparing and reviewing a consumer complaint.”

### Fictional demo text to paste

> I ordered a washing machine worth ₹18,000 from an online seller on October 15. It arrived damaged. I have the invoice, photographs and customer support emails. The seller has refused a replacement. What are my options, and can you prepare a complaint?

Use the result you actually see during recording. The three-language voice check was manual and did not measure recognition accuracy. A walkthrough video has yet to be recorded.
