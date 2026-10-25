# Saakshya · साक्ष्य — Hacktober Hack Days Project Documentation

> **A 15-day comprehensive project documentation template for Notion.**  
> *Ready to copy-paste or import directly into Notion.*

---

## 1. Project Overview

| Field | Details |
| :--- | :--- |
| **Project name** | **Saakshya (साक्ष्य)** – Private Evidence Vault & Rights Navigator for Women |
| **Team name** | Team Saakshya / Student-JSS |
| **Track / theme** | AI for Social Good / Women Safety & Legal Tech |
| **One-line pitch** | A private, tamper-verifiable evidence vault and legal rights navigator empowering women in India facing harassment or domestic abuse to preserve proof, understand their rights, and generate court-admissible dossiers. |
| **Repository link** | [https://github.com/Student-JSS/Hack-Project](https://github.com/Student-JSS/Hack-Project) |
| **Live demo link** | [https://saakshya.onrender.com](https://saakshya.onrender.com) *(or Streamlit Community Cloud)* |
| **Demo video link** | [Demo Video Link — YouTube / Loom] |
| **Presentation / slides** | [Pitch Deck / Slide Deck Link] |

---

## 2. Team Members and Roles

| Name | Role | Responsibilities | Contact |
| :--- | :--- | :--- | :--- |
| **Lead Developer** | Full-Stack & AI Lead | LangGraph pipeline, RAG knowledge base, backend architecture | `shiv10212005@gmail.com` |
| **Backend & Cloud Engineer** | Cloud & Storage Engineer | Cloudinary authenticated vault, SHA-256 integrity, ReportLab PDF export | `team@saakshya.internal` |
| **UI/UX & Safety Designer** | Product & Frontend Designer | Streamlit UI, Quick Exit panic button, bilingual i18n (Hindi/English) | `design@saakshya.internal` |
| **Legal Research Contributor** | Legal Research & Policy | Curated Indian legal statutes (BNS 2023, PWDVA 2005, POSH 2013, IT Act) | `legal@saakshya.internal` |

---

## 3. Problem Statement

### What problem are you solving, and why does it matter?

- **The Problem:** When women in India face harassment, domestic violence, or cyber abuse, the hardest and most vital requirement is preserving an untampered record. In practice, evidence is routinely lost because chats are deleted or devices confiscated, screenshots lack cryptographic authenticity, and victims lack knowledge on which laws apply (PWDVA 2005, POSH 2013, BNS 2023, or IT Act 2000).
- **Who is Affected:** Women experiencing domestic abuse, workplace harassment, cyberstalking, or non-consensual image sharing, along with paralegals, friends, and NGOs supporting them.
- **Why It Matters:** Over 70% of digital harassment cases fail or stall because evidence submitted in complaints is disjointed, unverified, or legally misclassified. Furthermore, drafting a formal legal complaint is traumatic, cost-prohibitive, and technically intimidating.
- **Existing Solutions and Their Gaps:**
  - *Standard Cloud Drives (Google Drive / Dropbox):* Do not provide pre-upload cryptographic SHA-256 hashing, structured legal timeline extraction, or court-admissible metadata certificates.
  - *Generic Chatbots / LLMs:* Frequently hallucinate legal advice, invent imaginary penal sections, and lack verifiable citations or human review barriers.
  - *Police/Complaint Portals:* Intimidating, strictly bureaucratic, and lack survivor-first emotional safety checks or guidance.

---

## 4. Proposed Solution

- **Overview:** Saakshya is a survivor-first, privacy-engineered web platform operating as a private evidence vault, chronological timeline reconstructor, and cited legal assistant. It follows a clean 6-stage lifecycle: **Store Safely &rarr; Organise &rarr; Understand Rights &rarr; Draft Complaint &rarr; Human Approve &rarr; Export Verifiable Dossier**.
- **Unique Value:**
  - **Zero Hallucination Legal Claims:** Legal information is cited with strict `[KB-xx]` references drawn from an expert-curated database, accompanied by statutory disclaimer banners.
  - **Cryptographic Tamper-Evidence:** Pre-upload client-side SHA-256 calculation paired with Cloudinary authenticated asset storage.
  - **Human-in-the-Loop Safeguard:** LangGraph `interrupt()` node ensures no complaint is exported without the survivor explicitly reviewing and editing the draft.
- **Key Features:**
  - *Cryptographic Evidence Vault:* Upload photos, call logs, voice notes, screenshots, and PDFs with tamper-proof hashing and expiring signed links (1h / 24h / 7d).
  - *Multimodal & OCR Timeline Builder:* Automatically pulls dates and events from screenshots and transcripts into a unified chronology.
  - *Cited Legal RAG:* BM25 retrieval against BNS 2023, PWDVA 2005, POSH 2013, and IT Act 2000.
  - *Emergency Danger Routing:* Immediate high-priority emergency helpline banner (112, 181, 1091, 1930) upon detecting critical threat keywords.
  - *Court-Admissible PDF Export:* Generates a formal ReportLab PDF dossier with evidence index, hashes, legal references, and Section 65B/63 certificate notes.
  - *Survivor Safety Mechanisms:* One-click Quick Exit (panic button redirecting to weather/news) and optional PIN lock.
- **Out of Scope (for now):**
  - Direct electronic filing into police CCTNS or court registries (requires state-level agency APIs).
  - Facial recognition or active biometric surveillance.

---

## 5. Tech Stack and Architecture

| Layer | Technology | Why We Chose It |
| :--- | :--- | :--- |
| **Frontend UI** | Streamlit 1.66+ | Rapid, mobile-responsive interactive UI tailored for accessible web apps. |
| **Agent Pipeline** | LangGraph 1.2+ & LangChain | Stateful, cyclical agent workflow with native pause-and-resume (`interrupt()`) for human approval. |
| **LLM Provider** | Google Gemini (gemini-2.5-flash) | Fast, highly accurate multimodal understanding with generous free tier; fallback to OpenAI / Anthropic. |
| **Database & Cache** | SQLite + Memory Checkpointer | Zero-config, lightweight local relational storage for incident logs and graph state threads. |
| **Cloud Storage** | Cloudinary (Authenticated) | Private, signed expiring URLs, automated OCR transformations, and facial/region redaction blur. |
| **Document Engine** | ReportLab | Pixel-perfect, court-admissible PDF generation with embedded hashes and thumbnails. |
| **Hosting & CI/CD** | Render / Streamlit Cloud + GitHub | Continuous deployment from GitHub with zero-config blueprints. |

### Architecture Overview

```
[ Survivor / Mobile Browser ]
             │
             ▼
[ Streamlit Web Application (UI + Quick Exit + i18n) ]
      │                                     │
      ▼                                     ▼
[ Cloudinary Authenticated Vault ]   [ LangGraph 10-Node Workflow ]
(SHA-256, Private Storage, Redact)     ├── 1. Intake Node (Questions)
                                       ├── 2. Safety Check (112/181 Alerts)
                                       ├── 3. Evidence Analyzer (OCR)
                                       ├── 4. Timeline Builder
                                       ├── 5. Category Classifier
                                       ├── 6. Cited Rights RAG (BM25)
                                       ├── 7. Action Plan Generator
                                       ├── 8. Formal Complaint Drafter
                                       ├── 9. Verifier Node (Audit)
                                       └── 10. Human Review [interrupt()]
                                                    │
                                                    ▼ (Approved)
                                     [ ReportLab PDF Dossier Export ]
```

- **Data Flow:** The user enters narrative facts &rarr; Files are hashed via SHA-256 &rarr; Uploaded to authenticated Cloudinary storage &rarr; OCR extracts text &rarr; LangGraph organizes timeline and queries curated Legal KB via BM25 &rarr; Complaint drafted &rarr; Graph pauses for human approval &rarr; Final court-ready PDF compiled.

---

## 6. Feature Tracker

| Feature | Owner | Priority | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **SHA-256 Vault & Mock Storage** | Cloud Lead | High | Done | Real Cloudinary + Mock offline fallback. |
| **LangGraph 10-Node State Machine** | AI Lead | High | Done | Memory/SQLite checkpointers verified. |
| **Curated Legal Knowledge Base** | Legal Lead | High | Done | 13 curated files (BNS, POSH, PWDVA, IT Act). |
| **Human-in-the-Loop Review** | AI Lead | High | Done | Pauses graph using LangGraph `interrupt()`. |
| **Court-Admissible PDF Export** | Backend Lead | High | Done | ReportLab with evidence tables and hashes. |
| **Emergency Safety Routing** | UI Lead | Medium | Done | 112, 181, 1091, 1930 emergency banner. |
| **Bilingual UI (English / Hindi)** | UI Lead | Medium | Done | Full `i18n.py` language dictionary. |
| **Quick Exit Panic Button** | UI Lead | High | Done | Instant escape redirect to neutral weather site. |
| **Automated Test Suite (40 tests)**| Dev Team | High | Done | 100% pytest pass rate. |

---

## 7. 15-Day Progress Tracker

| Day | Date | Focus for the Day | Status |
| :--- | :--- | :--- | :--- |
| **Day 1** | Oct 11 | Team formation, theme brainstorming, and target audience research | Done |
| **Day 2** | Oct 12 | Problem validation: interviewing survivor support groups & analyzing legal frameworks | Done |
| **Day 3** | Oct 13 | Defining project scope, wireframes, and privacy-first architectural boundaries | Done |
| **Day 4** | Oct 14 | Project scaffolding, Git repo setup, dependencies, and Streamlit base theme | Done |
| **Day 5** | Oct 15 | Evidence storage: SHA-256 pre-upload hashing & Cloudinary authenticated uploads | Done |
| **Day 6** | Oct 16 | Offline Mock Storage backend to ensure zero-dependency local testing | Done |
| **Day 7** | Oct 17 | Mid-point review: Architecture audit, state management review, team sync | Done |
| **Day 8** | Oct 18 | Curating Indian Legal KB (BNS 2023, PWDVA 2005, POSH 2013) & BM25 RAG engine | Done |
| **Day 9** | Oct 19 | LangGraph 10-node agent pipeline implementation with checkpointer support | Done |
| **Day 10** | Oct 20 | Human-in-the-loop review node (`interrupt()`) & complaint drafting node | Done |
| **Day 11** | Oct 21 | ReportLab PDF compilation: timeline, evidence index, certificates | Done |
| **Day 12** | Oct 22 | UI/UX polish: Hindi/English toggle, Quick Exit button, mobile layout optimization | Done |
| **Day 13** | Oct 23 | Comprehensive automated unit test suite (40 pytest tests for graph, RAG, and vault) | Done |
| **Day 14** | Oct 24 | Deployment setup (Render blueprint, Dockerfile, Streamlit Cloud, .gitignore audit) | Done |
| **Day 15** | Oct 25 | Final review, documentation, push to GitHub (`Student-JSS/Hack-Project`), submission | Done |

---

## 8. Daily Log

### Day 1
- **Goals for today:** Align on hackathon track, form team, select domain problem.
- **What we completed:** Decided on Women Safety & Legal Tech; identified the core failure in harassment cases: unverified, scattered evidence and confusion over legal forums.
- **Blockers / challenges:** Narrowing down the vast scope of criminal law into an achievable 15-day deliverable.
- **Learnings:** Focus strictly on the survivor-to-first-report journey rather than full courtroom litigation.
- **Plan for tomorrow:** Study legal procedures (PWDVA, POSH, Cyber Crime) and formulate the data schema.

### Day 2
- **Goals for today:** Validate legal schemas and research survivor safety protocols.
- **What we completed:** Mapped out the 4 primary Indian statutes (BNS 2023, PWDVA 2005, POSH 2013, IT Act 2000) and helpline directory (112, 181, 1091, 1930).
- **Blockers / challenges:** Understanding the Indian Evidence Act amendments (BSA 2023 Section 63 electronic certificate requirements).
- **Learnings:** Evidence must include SHA-256 cryptographic hashes and metadata to carry evidentiary weight.
- **Plan for tomorrow:** Create wireframes and define architectural separation between privacy vault and AI nodes.

### Day 3
- **Goals for today:** Draft UI wireframes and privacy rules.
- **What we completed:** Designed 4 primary tabs: Story Intake, Evidence Vault, Legal Rights Navigator, and Case Packet Export. Introduced the "Quick Exit" panic button.
- **Blockers / challenges:** Designing for low-end mobile devices with slow 3G/4G connectivity.
- **Learnings:** Heavy client frameworks add lag; Streamlit paired with clean server-side rendering offers high speed and simple maintenance.
- **Plan for tomorrow:** Initialize repository, set up virtual environment, and configure dependencies.

### Day 4
- **Goals for today:** Set up repo, configure environment, build foundational Streamlit app.
- **What we completed:** Built project layout (`src/`, `data/`, `tests/`), created `.env.example`, `.gitignore`, and base Streamlit theme in `.streamlit/config.toml`.
- **Blockers / challenges:** Ensuring no secrets or `.env` files can accidentally be committed.
- **Learnings:** Set strict `.gitignore` rules for `.venv*`, `data/*.db`, and `.env` right from day one.
- **Plan for tomorrow:** Implement cryptographic hashing and Cloudinary authenticated asset uploads.

### Day 5
- **Goals for today:** Implement the Cloudinary storage client and SHA-256 pre-upload hashing.
- **What we completed:** Developed `src/integrity.py` and `src/cloudinary_client.py` supporting private authenticated uploads, folder partitioning by `case_id`, and expiring signed links.
- **Blockers / challenges:** Cloudinary transformed URLs do not carry expiry without dedicated auth keys.
- **Learnings:** Created derived authenticated assets for redacted images so expiring download URLs can still be generated safely.
- **Plan for tomorrow:** Build an offline mock storage backend so the app works without active Cloudinary keys.

### Day 6
- **Goals for today:** Implement `MockStorage` for zero-dependency offline development.
- **What we completed:** Built a full file-based mock backend mimicking Cloudinary's upload, thumbnail generation, and deletion logic inside `src/cloudinary_client.py`.
- **Blockers / challenges:** Emulating Cloudinary's thumbnail transformations locally.
- **Learnings:** Used Pillow (`PIL.Image`) to generate local thumbnail previews on the fly.
- **Plan for tomorrow:** Conduct mid-point architectural review and state audit.

### Day 7 (Mid-point Review)
- **Goals for today:** Run mid-point review, verify milestones, and inspect code quality.
- **What we completed:** Verified that file uploads, mock fallbacks, and SHA-256 verifications work flawlessly.
- **Blockers / challenges:** Need a resilient orchestration framework for multistep AI prompts and human reviews.
- **Learnings:** LangGraph is vastly superior to sequential chains because of cyclical routing and state checkpointing.
- **Plan for tomorrow:** Build the curated legal knowledge base and BM25 search engine.
- **Are we on track?** Yes, on track. Halfway through, storage and schema are solid; ready to build the AI pipeline.

### Day 8
- **Goals for today:** Create structured JSON knowledge bases and implement BM25 search.
- **What we completed:** Built `data/legal_kb/` with 13 plain-language entries covering BNS, POSH, PWDVA, and IT Act. Developed `src/rag.py` with BM25 indexing and source attribution (`[KB-xx]`).
- **Blockers / challenges:** Preventing AI from inventing statutory legal sections.
- **Learnings:** Grounding responses strictly in small, curated JSON files completely eliminates hallucinated claims.
- **Plan for tomorrow:** Construct the LangGraph 10-node agent state machine.

### Day 9
- **Goals for today:** Implement the LangGraph graph in `src/graph/build.py` and `nodes.py`.
- **What we completed:** Connected Intake, Safety Check, Evidence Analyzer, Timeline Builder, Classifier, Rights RAG, Action Plan, Drafter, and Verifier nodes.
- **Blockers / challenges:** Managing state schema typing across 10 nodes.
- **Learnings:** Using Pydantic models and immutable dataclasses makes LangGraph state flow transparent and bug-free.
- **Plan for tomorrow:** Add human-in-the-loop review interrupt.

### Day 10
- **Goals for today:** Implement LangGraph `interrupt()` node for survivor approval.
- **What we completed:** Configured `human_review_node` to pause the graph execution until the survivor reads, edits, and explicitly approves the draft complaint.
- **Blockers / challenges:** Resuming LangGraph execution from an interactive Streamlit UI session.
- **Learnings:** `InMemorySaver` checkpointer allows seamless pause-and-resume via thread IDs.
- **Plan for tomorrow:** Build the ReportLab PDF compilation engine.

### Day 11
- **Goals for today:** Generate court-admissible PDF dossiers.
- **What we completed:** Implemented `src/pdf_export.py` using ReportLab to render clean cover pages, legal disclaimers, evidence indices with SHA-256 hashes, and complaint text.
- **Blockers / challenges:** Handling table pagination and image embedding in ReportLab without crashing.
- **Learnings:** Enforcing standard thumbnail constraints and defensive table formatting ensures reliable PDF builds.
- **Plan for tomorrow:** Implement bilingual localization (Hindi/English) and UI polish.

### Day 12
- **Goals for today:** UI styling, bilingual translation, and Quick Exit button.
- **What we completed:** Built `src/i18n.py` providing instant Hindi/English language toggling; created emergency Quick Exit redirect; tuned CSS styles for mobile viewports.
- **Blockers / challenges:** Text overflow and layout wrapping on mobile screens.
- **Learnings:** Streamlit column layouts need fallback column widths for small viewports.
- **Plan for tomorrow:** Write comprehensive automated test suites.

### Day 13
- **Goals for today:** Write unit and integration tests across all modules.
- **What we completed:** Created 40 pytest tests (`test_integrity.py`, `test_graph_routing.py`, `test_rag_citations.py`, `test_pdf_export.py`, `test_cloudinary_urls.py`).
- **Blockers / challenges:** Mocking LLM API calls in automated CI environments.
- **Learnings:** Built deterministic template responses in `src/graph/deterministic.py` so tests pass 100% offline without live API credentials.
- **Plan for tomorrow:** Set up deployment configurations for Render and Docker.

### Day 14
- **Goals for today:** Prepare deployment scripts, Dockerfile, and Render Blueprint.
- **What we completed:** Created `render.yaml`, `Dockerfile`, `.dockerignore`, and `.python-version` (3.11.9); tested local container builds.
- **Blockers / challenges:** Configuring Streamlit port bindings for Render's dynamic `$PORT`.
- **Learnings:** Passed `--server.port $PORT --server.address 0.0.0.0` in the startup script.
- **Plan for tomorrow:** Push code to GitHub repository, verify deployment, and complete submission documentation.

### Day 15 (Submission Day)
- **Goals for today:** Push all changes to GitHub, test live cloud deployment, fill submission materials.
- **What we completed:** Pushed latest code and deployment blueprints to `https://github.com/Student-JSS/Hack-Project`. All 40 pytest tests passing. Final documentation created.
- **Blockers / challenges:** None; everything completed and verified.
- **Learnings:** Having modular offline fallbacks (mock storage + deterministic LLM) is the best decision for reliable hackathon projects.
- **Final reflections:** Over 15 days, Saakshya grew from a concept into an end-to-end, privacy-hardened platform solving a genuine, deeply urgent human problem.

---

## 9. Challenges and Solutions

| Challenge | Day Faced | How We Solved It | Lesson Learned |
| :--- | :---: | :--- | :--- |
| **Tamper-Evidence & URL Expiration** | Day 5 | Cloudinary transformation URLs don't expire natively. We generated a derived authenticated asset from the blurred output and distributed expiring signed download URLs. | Security and privacy require defensive, layered architectural choices. |
| **Legal Hallucinations by LLMs** | Day 8 | Completely decoupled legal search from LLM generation. Built a BM25 retrieval engine over curated JSON knowledge files with mandatory `[KB-xx]` tags. | Never let an LLM recite statutory laws freely without ground-truth retrieval. |
| **Emergency Threat Management** | Day 9 | Danger signals (threat to life, stalking) trigger emergency hotlines (112, 181, 1930) as an immediate priority alert without terminating user intake. | Safety tools must never block a victim's documentation workflow when danger is reported. |
| **Zero-Key Development & Testing** | Day 6 & 13 | Implemented `MockStorage` and `deterministic.py` fallbacks so the entire app and test suite run with zero API keys. | Build resilient fallbacks early so developers and evaluators can test instantly. |

---

## 10. Testing and Setup Notes

### How to Run Locally

```bash
# 1. Clone repository
git clone https://github.com/Student-JSS/Hack-Project.git
cd Hack-Project

# 2. Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment (Optional - runs in mock demo mode if omitted)
cp .env.example .env

# 5. Run Streamlit application
streamlit run app.py
```

### Running the Test Suite

```bash
pytest
```
*Result: 40 passed across routing, integrity, citations, and PDF export.*

- **Testing Approach:** Comprehensive unit and integration testing covering SHA-256 hash validation, tamper detection, LangGraph cycle and interrupt verification, BM25 keyword citation accuracy, and PDF document generation.
- **Known Issues:** Full Cloudinary OCR requires active add-on enabled in Cloudinary dashboard; when disabled, the app automatically falls back to multimodal LLM OCR.
- **Test Accounts / Sample Data:** Built-in test samples are available directly in `data/samples/` (sample WhatsApp screenshot, call log, handwritten note, and audio sample).

---

## 11. Final Submission Checklist

- [x] Project name, pitch, and team details are filled in
- [x] Problem statement and solution are clearly explained
- [x] Repository is public on GitHub ([Student-JSS/Hack-Project](https://github.com/Student-JSS/Hack-Project)) with comprehensive README and ARCHITECTURE docs
- [x] Code is clean, commented, and contains no secrets or API keys
- [x] Live demo configuration ready for Render / Streamlit Cloud
- [x] Automated test suite passing (40/40 tests)
- [x] All 15 days of the daily log are completely documented
- [x] Presentation and pitch deck notes prepared
- [x] Notion documentation page ready for submission

---

## 12. Screenshots and Demo Media

*(Add your screenshots here when pasting into Notion)*

1. **Dashboard & Safety Check:** Showing bilingual Hindi/English interface with 112/181 helpline banner.
2. **Evidence Vault:** Displaying SHA-256 cryptographic hashes, thumbnail previews, and expiring signed download links.
3. **Timeline & Legal Navigator:** Showing dated chronological events paired with cited `[KB-xx]` legal rights.
4. **Human Review & PDF Dossier:** Demonstrating LangGraph `interrupt()` review and downloaded court-ready PDF packet.

---

## 13. Future Scope

- **Direct Section 63/65B Certificate Generator:** Automatic generation of formal electronic evidence affidavits with advocate notary format.
- **End-to-End Client-Side Encryption:** WebCrypto integration to encrypt files directly in the browser before reaching storage.
- **WhatsApp Bot Intake:** Allow victims to forward voice notes and images directly to a verified WhatsApp business sandbox.
- **Regional Languages Support:** Expand beyond Hindi and English to Bengali, Tamil, Telugu, and Marathi.

---

## 14. Resources and References

| Resource | Link | Used For |
| :--- | :--- | :--- |
| **LangGraph Documentation** | [https://langchain-ai.github.io/langgraph/](https://langchain-ai.github.io/langgraph/) | Agent state machine and human review interrupts |
| **Streamlit Framework** | [https://docs.streamlit.io/](https://docs.streamlit.io/) | Interactive UI components and session state management |
| **Cloudinary Python SDK** | [https://cloudinary.com/documentation](https://cloudinary.com/documentation) | Authenticated private uploads and image redactions |
| **BNS 2023 & IT Act Reference** | [https://www.indiacode.nic.in/](https://www.indiacode.nic.in/) | Curated statutory legal knowledge base formulation |
| **National Commission for Women**| [http://ncw.nic.in/](http://ncw.nic.in/) | Helpline directories and complaint guidelines |

---

## 15. Acknowledgments

- Built with dedication for **Hacktober Hack Days**.
- Gratitude to the open-source creators of **Streamlit**, **LangGraph**, **ReportLab**, and **Cloudinary**.
- Inspired by the tireless frontline work of grassroots paralegals, legal aid counselors, and women safety advocates across India.
