# Saakshya · साक्ष्य

**A private evidence vault and rights navigator for women facing harassment, domestic violence or cyber abuse in India.**

Saakshya (Hindi for *evidence*) helps a woman preserve screenshots, photos, voice notes and videos in a private,
verifiable vault; turns them into a dated timeline; tells her which curated rights information applies; and drafts a
complaint she edits and approves before anything leaves the app.

> **Saakshya provides general information, not legal advice.** Every legal claim in the app is a plain-language
> summary from a small curated knowledge base, cites its source id, and is marked *verify with a lawyer*.

---

## The problem

When harassment escalates, the most useful thing a woman can do is also the hardest: keep a clean record. In practice
she loses it in three ways.

1. **Evidence disappears.** Chats get deleted, phones are taken away or replaced, screenshots sit unnamed in a gallery,
   and there is no proof that a file was not edited later.
2. **She does not know which law applies.** Domestic violence, workplace harassment, stalking and image-based abuse
   sit under different laws and different forums (Protection Officer, Internal Committee, cyber crime portal, police).
3. **She does not know what to write.** A police complaint or an Internal Committee complaint needs dates, names, an
   evidence index and a clear ask. Most templates online are either intimidating or wrong.

Saakshya narrows the problem to one flow: **store it safely → organise it → understand your rights → draft it → approve it → share a packet**.

## Who it is for

- A woman documenting domestic violence who needs a dated record and the Protection Officer route.
- A woman facing workplace sexual harassment who needs the Internal Committee process and a written complaint.
- A woman facing stalking or image-based abuse who needs a cyber crime report and a takedown trail.
- A friend, NGO worker or paralegal helping her organise a case on her behalf (with her consent).

It is designed for a low-end Android phone on a slow connection, in Hindi or English, with a real fear that someone
else may pick up the device.

## What it does

| Step | What happens |
| --- | --- |
| **1. Story** | She writes what happened in Hindi, English or Hinglish. The intake node asks up to three follow-up questions (what / when / who / are you safe). |
| **2. Safety** | Danger signals (threats to kill, acid, stalking, blackmail, image leaks) trigger an urgent-help block **first**: 112, 181, 1091, 1930. The pipeline then continues, it does not stop. |
| **3. Evidence vault** | Upload images, audio, video, PDFs. Each file is hashed with **SHA-256 before upload**, stored as a **private (authenticated) Cloudinary asset** in a per-case folder, and can be re-downloaded and re-checked with one button. |
| **4. OCR** | Screenshots are read by Cloudinary's OCR add-on; if the add-on is not enabled the image goes to the multimodal LLM; the UI always shows which engine produced the text. |
| **5. Timeline** | Story sentences and evidence text are merged into one chronological timeline; items without a date are flagged as gaps instead of being guessed. |
| **6. Rights** | A BM25 search over 13 curated plain-language entries (PWDVA 2005, POSH 2013, BNS 2023, IT Act 2000, FIR/Zero FIR, NCW, NALSA, cybercrime.gov.in, evidence certificates, helplines). Every entry carries `[KB-xx]`, `last_reviewed` and *verify with a lawyer*. |
| **7. Action plan** | Prioritised steps in her language: immediate safety, preserve evidence, who to contact, documents to carry, free legal aid. |
| **8. Complaint** | A formal complaint using only facts she supplied or the evidence shows, with `E1, E2…` references and the SHA-256 hashes. |
| **9. Human approval** | A LangGraph `interrupt()` pauses the graph. Nothing is exported until she edits and approves the draft. |
| **10. Packet** | A reportlab PDF: cover + disclaimer, timeline, evidence index with hashes, thumbnails, approved draft, cited rights summary, and the court-certificate note. |
| **Always** | Signed expiring share links (1h / 24h / 7d), privacy-safe blurred copies, per-item delete, delete-whole-case, delete-everything, Quick Exit, optional PIN. |

## Quick Start

### 1. Setup Environment
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On macOS / Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
```bash
cp .env.example .env
```
Add your Google Gemini API key or Cloudinary credentials to `.env`.
*Note: If no API keys are provided, Saakshya runs automatically using deterministic templates and offline mock storage for instant testing.*

### 3. Run the App
```bash
streamlit run app.py
```

## How Cloudinary is used

Cloudinary is not a decoration here: it is the storage layer, the privacy layer and the integrity layer.

| Feature | Cloudinary capability | Where |
| --- | --- | --- |
| Private uploads in per-case folders | `uploader.upload(resource_type="auto", type="authenticated", folder="saakshya/<case_id>/")` with `tags` and `context` (case_id, evidence_type, uploaded_at) | `src/cloudinary_client.py` |
| Integrity record | SHA-256 computed locally before upload; `public_id`, `version`, `etag`, `bytes` stored in SQLite; "Verify integrity" re-downloads and compares | `src/integrity.py`, `src/ingest.py` |
| Expiring share links | `utils.private_download_url(..., type="authenticated", expires_at=now+1h/24h/7d)` | `signed_url()` |
| Redacted sharing | `e_blur_faces:1200` plus an optional region blurred by layering a blurred crop of the same asset (`l_<public_id>`, `c_crop`, `e_blur:900`, `fl_layer_apply`); the result is fetched and stored as a **separate** authenticated asset so the share link itself can expire | `redaction_transformation()`, `create_redacted_copy()` |
| OCR | `uploader.explicit(public_id, type="authenticated", ocr="adv_ocr")`, results parsed defensively, LLM fallback on any failure | `src/ocr.py` |
| Thumbnails / video poster | Signed transformation URLs (`w_480,h_360,c_fill`; `so_0` for video posters) | `transformed_url()` |
| Delete | `uploader.destroy(..., invalidate=True)` per asset, `api.delete_resources_by_prefix("saakshya/<case_id>/")` per case, plus derived-copy cleanup | `delete_asset`, `delete_derived`, `delete_case_assets` |

**Why a derived asset for redacted shares?** Cloudinary signs transformation URLs, but a signed delivery URL does not
carry an expiry unless the account has an auth-token key configured. `private_download_url` *does* expire, but the
download endpoint does not apply transformations. So Saakshya renders the blurred transformation once, stores it as a
second authenticated asset (tagged `redacted`), and shares *that* through an expiring `private_download_url`. The
transformation URL is still shown in the UI so the blur is auditable. See ARCHITECTURE.md for the full trade-off.

## How LangGraph is used

Typed state (`SaakshyaState`), ten nodes, two conditional edges, a real human-in-the-loop interrupt and a checkpointer.

```mermaid
graph TD
    START([start]) --> intake[intake<br/>story + up to 3 questions]
    intake -->|missing info| WAIT([pause: UI asks, then re-runs])
    intake -->|enough info| safety[safety_check]
    safety -->|risk = high| evidence[evidence_analyzer<br/>urgent help shown first]
    safety -->|risk = low/medium| evidence
    evidence --> timeline[timeline_builder]
    timeline --> classify[classifier]
    classify --> rights[rights_rag<br/>cited KB]
    rights --> plan[action_plan]
    plan --> draft[complaint_drafter]
    draft --> verify{verifier}
    verify -->|failed, retries ≤ 2| draft
    verify -->|passed or retries exhausted| review[[human_review<br/>interrupt]]
    review -->|approved| END([end])
    review -->|changes requested| END
```

| Node | Job |
| --- | --- |
| `intake_node` | Merges the story and follow-up answers, decides whether critical info is missing, asks up to 3 questions. |
| `safety_check_node` | Detects danger signals, sets `risk_level`, attaches urgent-help lines. Never blocks the pipeline. |
| `evidence_analyzer_node` | Extracts dates, senders, threats and quotes per item (Pydantic `EvidenceAnalysis`, LLM or heuristic). |
| `timeline_builder_node` | Merges story and evidence chronologically, records gaps. |
| `classifier_node` | Multi-label category + confidence (domestic violence, workplace, stalking, cyber, dowry, other). |
| `rights_rag_node` | BM25 retrieval, one citation per match, category coverage guarantee. |
| `action_plan_node` | 4-6 prioritised steps in her language. |
| `complaint_drafter_node` | Draft with evidence refs and hashes; appends sources if the model forgot citations. |
| `verifier_node` | Checks every `[KB-xx]` exists and every date is traceable; loops back to the drafter (max 2 retries) then flags uncertainty. |
| `human_review_node` | `interrupt()` payload with the draft; resumes only with her decision. |

Checkpointing: `InMemorySaver` by default, `SqliteSaver` when `CHECKPOINT_BACKEND=sqlite` (so an approval can survive a
process restart). LangSmith tracing is a two-variable toggle (`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`).

## Tech stack

- Python 3.11+ (tested on 3.14), Streamlit 1.66
- LangGraph 1.2 + LangChain 1.7, provider-agnostic (`google` default, `openai`, `anthropic`)
- Cloudinary Python SDK 1.46 (authenticated assets, signed URLs, transformations, OCR add-on, deletes)
- SQLite (stdlib `sqlite3`) for cases, evidence metadata, integrity records, share links, approvals, audit log
- reportlab 5 for the PDF packet
- Local RAG: BM25 over curated JSON (no vector DB, no key required)
- pydantic 2, python-dotenv, pytest, Pillow (synthetic demo files)

## Quick start (5 commands)

```bash
git clone <your-fork-url> && cd saakshya
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # then paste your Cloudinary + Gemini keys
streamlit run app.py
```

Open <http://localhost:8501>, tick the consent box, then press **Load demo case** in the sidebar. No LLM key? The app
falls back to deterministic templates and still runs the whole flow. No Cloudinary account (or a typo in `.env`)? The
app logs a warning, shows it in the sidebar and falls back to `USE_MOCK_CLOUDINARY` behaviour - local storage, HMAC-signed
`mock://` links with real expiry - so a fresh clone never crashes.

Detailed beginner steps, a 14-case manual test script, troubleshooting and a 3-minute demo script are in
[RUN_AND_TEST.md](RUN_AND_TEST.md).

## Environment variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `LLM_PROVIDER` | no | `google` | `google` \| `openai` \| `anthropic` |
| `LLM_MODEL` | no | provider default | e.g. `gemini-2.5-flash` |
| `LLM_ENABLED` | no | `true` | `false` forces the offline templates |
| `GOOGLE_API_KEY` | for Google | – | free tier at aistudio.google.com |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | only if used | – | other providers |
| `CLOUDINARY_URL` | yes (real mode) | – | `cloudinary://key:secret@cloud_name` |
| `CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | alternative | – | used when `CLOUDINARY_URL` is empty |
| `USE_MOCK_CLOUDINARY` | no | `false` | offline storage in `data/mock_cloudinary`, HMAC-signed mock URLs |
| `CLOUDINARY_OCR_ENABLED` | no | `false` | `true` only after enabling the OCR add-on in your account |
| `DEMO_MODE` | no | `false` | force canned deterministic output |
| `DB_PATH` | no | `data/saakshya.db` | SQLite file |
| `CHECKPOINT_BACKEND` | no | `memory` | `memory` \| `sqlite` |
| `SHARE_DEFAULT_HOURS` | no | `24` | default share lifetime |
| `MOCK_STORAGE_DIR` | no | `data/mock_cloudinary` | where mock-mode assets live |
| `EXPORTS_DIR` | no | `data/exports` | where PDF packets are written |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` | no | `false` / – / `saakshya` | tracing |
| `LOG_LEVEL` | no | `INFO` | log verbosity |

Secrets live only in `.env` (git-ignored). `Settings.describe()` returns booleans, never secret values.

## Demo Mode

`Load demo case` creates a case with a synthetic story and four generated files (`data/samples/`): a WhatsApp-style
screenshot, a missed-call log, a photo of a handwritten note, and a short audio note. Every name, number and message
is fake. Demo Mode works with no LLM key (deterministic template brain) and with `USE_MOCK_CLOUDINARY=true` entirely
offline.

## Safety and privacy (summary)

- **Consent first.** A plain-language notice is shown before any case can be created; the acknowledgement is a flag,
  not personal data.
- **Quick Exit.** One button clears the Streamlit session and redirects the tab to a neutral weather page.
- **Optional PIN.** A salted PBKDF2 hash stored in SQLite gates the app (`src/ui/components.py`). It is a shoulder-surfing
  deterrent, not encryption - see the threat model.
- **Private assets by default.** Every upload is `type="authenticated"`; nothing is publicly reachable, and shares are
  signed links with a chosen expiry.
- **Integrity by hash.** The SHA-256 is computed on the device before upload and stored next to the Cloudinary ids.
- **Data minimisation.** Only metadata is logged (action names, evidence labels). Story text, OCR text and draft text
  are never written to logs.
- **Control.** Delete one item, delete a whole case (remote folder + local rows), or delete everything.
- **Honest labels.** The OCR method, the risk level, integrity status, verifier status and "not legal advice" are always
  visible rather than implied.

The full threat model (device sharing, link leakage, abuser access, LLM data exposure, local database, logs) is in
[ARCHITECTURE.md](ARCHITECTURE.md).

## Limitations and honest disclaimers

- **Not legal advice, not a lawyer.** 13 curated entries reviewed only by the team (last reviewed 2026-09-30). Section
  numbers changed when the BNS/BNSS/BSA replaced the IPC/CrPC/Evidence Act in 2023; where the team was not certain the
  KB says so explicitly instead of guessing.
- **Hindi PDF needs a font.** reportlab's default font cannot render Devanagari. Drop a Noto Sans Devanagari TTF into
  `assets/fonts/` to fix it (`assets/fonts/README.md`). Until then the PDF prints a warning and English is safer for print.
- **No audio transcription.** Cloudinary and the LLM are not used for speech-to-text; she can type a description or
  transcript per item, which the pipeline uses.
- **The PIN does not encrypt the database.** Streamlit keeps the SQLite file on the same device; an attacker with file
  access can read it. Use full-disk encryption and a device only she can unlock.
- **Uploads are not virus-scanned.** Only let her upload her own files.
- **BM25, not embeddings.** The KB is 13 entries, so a keyword index is more predictable and needs no model download or
  key. `LegalKB.search` is the single seam to swap in FAISS/Chroma later.
- **One round of follow-up questions**, not an unbounded interrogation loop - deliberate, to avoid re-traumatising her.
- **Mock storage is not Cloudinary.** `USE_MOCK_CLOUDINARY=true` writes files under `data/mock_cloudinary` and signs
  `mock://` URLs with HMAC; it proves the flow, not Cloudinary's CDN behaviour.
- **Cloudinary backend:** Real authenticated Cloudinary storage and signed expiring links are enabled when credentials are set in `.env`. If no credentials are provided, the app runs gracefully using the offline mock backend.
- **Single-device, single-user.** No accounts, no multi-device sync, no NGO dashboard.
- **Court admissibility depends on process.** A hash trail helps; a certificate and the original device still matter.

## Roadmap

1. **Audio transcription** with a Cloudinary add-on or a speech model, with a visible consent step.
2. **Vector retrieval** (Chroma/FAISS) with a lawyer-reviewed KB of 150+ entries and a review workflow with dates.
3. **NGO/lawyer hand-off** - a revocable, expiring "packet link" scoped to one case, with an access log she can see.
4. **Evidence certificate generator** matching the current BNS/BSA format, reviewed by a lawyer.
5. **Offline-first mobile client** (PWA) with an encrypted local queue, so uploads survive a 2G connection.
6. **Multilingual** beyond Hindi/English: Marathi, Bengali, Tamil, Kannada, with KB translations.
7. **Trauma-informed UX research** with a women's rights organisation before any public pilot.



## License

MIT - see [LICENSE](LICENSE). The legal summaries are original plain-language writing; linked source pages belong to
their respective publishers.
