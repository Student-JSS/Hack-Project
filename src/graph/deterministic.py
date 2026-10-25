"""Deterministic fallbacks for every agent step.

Demo Mode (and any run without an LLM key) uses these functions instead of the
model. They are intentionally simple: regular expressions, keyword scores and
templates that only ever restate facts the survivor supplied. Nothing here makes
a legal claim beyond the curated KB, and every citation is attached by the node.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from src.rag import CATEGORY_LABELS

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
HINDI_MONTHS = {
    "जनवरी": 1, "फरवरी": 2, "फ़रवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5,
    "जून": 6, "जुलाई": 7, "अगस्त": 8, "सितंबर": 9, "अक्टूबर": 10,
    "नवंबर": 11, "दिसंबर": 12,
}

SEVERE_PATTERNS = (
    r"will kill (me|her|you)",
    r"kill (me|her)",
    r"murder (me|her)",
    r"acid",
    r"set (me|her) on fire",
    r"burn (me|her)",
    r"strangle",
    r"choke (me|her)",
    r"rape",
    r"molest",
    r"suicide",
    r"kill myself",
    r"end my life",
    r"(maar|maar) daleg[ai]",
    r"jaan se maar",
    r"tezaab",
    r"aatmahatya",
    r"khudkhushi",
    r"मार डालेग",
    r"जान से मार",
    r"तेज़ाब",
    r"आत्महत्या",
    r"बलात्कार",
    r"फांसी",
)
DANGER_PATTERNS = SEVERE_PATTERNS + (
    r"threaten",
    r"threat",
    r"blackmail",
    r"leak (my|her) (photos|pictures|videos)",
    r"send (my|her) (photos|pictures|videos)",
    r"post (my|her) (photos|pictures|videos|images)",
    r"(show|share) (my|her) (photos|pictures|videos|images)",
    r"if (i|she) (leave|try to leave)",
    r"cannot (meet|see) (my|her) (parents|family)",
    r"viral",
    r"hit (me|her)",
    r"beat (me|her)",
    r"slap",
    r"locked (me|her) in",
    r"won't let (me|her) leave",
    r"not allowed to (go|leave)",
    r"follow(s|ing)? (me|her)",
    r"outside (my|her) (house|home|office)",
    r"stalking",
    r"dhamki",
    r"dara raha",
    r"peecha",
    r"धमकी",
    r"पीछा",
    r"मारपीट",
)

RELATIVE_TIME = (
    "yesterday", "today", "last night", "last week", "last month", "last year",
    "this morning", "day before", "kal", "parso", "raat", "subah", "pichle hafte",
    "कल", "परसों", "रात", "पिछले हफ्ते", "आज",
)
RELATION_WORDS = (
    "husband", "ex-husband", "boyfriend", "ex-boyfriend", "partner", "in-laws",
    "mother-in-law", "father-in-law", "brother-in-law", "sister-in-law", "boss",
    "manager", "colleague", "senior", "neighbour", "neighbor", "landlord",
    "teacher", "professor", "cousin", "uncle", "friend", "ex", "saas", "sasur",
    "pati", "devar", "nanad", "padosi", "बॉस", "पति", "सास", "ससुर", "देवर",
    "ननद", "पड़ोसी", "मालिक",
)
SAFETY_WORDS = (
    "safe", "unsafe", "danger", "threat", "scared", "afraid", "fear", "hurt",
    "safe hai", "dar", "darr", "khatra", "सुरक्षित", "डर", "खतरा", "धमकी",
)

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "domestic_violence": (
        "husband", "in-laws", "mother-in-law", "father-in-law", "saas", "sasural",
        "domestic", "hits me", "beats me", "martial", "maar", "pati", "घर", "पति",
        "सास", "मारपीट", "घरेलू", "married", "shaadi",
    ),
    "workplace_sexual_harassment": (
        "boss", "office", "colleague", "hr", "manager", "internship", "workplace",
        "appraisal", "posh", "company", "meeting", "काम", "ऑफिस", "बॉस", "सहकर्मी",
    ),
    "stalking": (
        "following", "follows me", "stalking", "waiting outside", "unknown number",
        "calls repeatedly", "tracking", "location", "peecha", "पीछा", "फोन",
    ),
    "cyber_harassment": (
        "instagram", "whatsapp", "facebook", "fake profile", "screenshot", "leak",
        "viral", "online", "email", "account", "morphed", "deepfake", "telegram",
        "इंटरनेट", "फोटो", "वीडियो", "मैसेज",
    ),
    "dowry_related": (
        "dowry", "dahej", "dowry demand", "gifts", "दहेज", "सामान", "car", "gold",
    ),
}
THREAT_WORDS = (
    "kill", "threat", "blackmail", "leak", "viral", "acid", "hurt", "beat", "hit",
    "dhamki", "jaan", "maar", "धमकी", "जान", "मार", "बदनाम",
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n+")


# --------------------------------------------------------------------- basics
def sentences(text: str) -> list[str]:
    """Split free text into trimmed, non-empty sentences."""
    return [part.strip() for part in SENTENCE_SPLIT.split(text or "") if part.strip()]


def trim(text: str, limit: int = 180) -> str:
    """Collapse whitespace and cut to ``limit`` characters."""
    cleaned = " ".join((text or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


@dataclass(frozen=True)
class DateHit:
    """A date found in text, normalised as far as possible."""

    iso: str
    raw: str
    has_year: bool


def _iso(year: int, month: int, day: int) -> str | None:
    """Build an ISO date string, rejecting impossible dates."""
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def extract_date_hits(text: str) -> list[DateHit]:
    """Find and normalise dates in English or Hindi text."""
    hits: list[DateHit] = []
    seen: set[str] = set()
    current_year = datetime.now(timezone.utc).year
    body = text or ""

    for match in re.finditer(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", body):
        iso = _iso(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if iso and iso not in seen:
            seen.add(iso)
            hits.append(DateHit(iso, match.group(0), True))

    for match in re.finditer(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b", body):
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        year = year + 2000 if year < 100 else year
        iso = _iso(year, month, day)
        if iso and iso not in seen:
            seen.add(iso)
            hits.append(DateHit(iso, match.group(0), True))

    month_names = "|".join(sorted(MONTHS, key=len, reverse=True))
    for match in re.finditer(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})\.?,?\s*(\d{{4}})?", body, re.IGNORECASE
    ):
        day = int(match.group(1))
        month = MONTHS[match.group(2).lower()]
        year = int(match.group(3)) if match.group(3) else current_year
        iso = _iso(year, month, day)
        if iso and iso not in seen:
            seen.add(iso)
            hits.append(DateHit(iso, match.group(0).strip(), bool(match.group(3))))

    for match in re.finditer(
        rf"\b({month_names})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})?", body, re.IGNORECASE
    ):
        month = MONTHS[match.group(1).lower()]
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else current_year
        iso = _iso(year, month, day)
        if iso and iso not in seen:
            seen.add(iso)
            hits.append(DateHit(iso, match.group(0).strip(), bool(match.group(3))))

    hindi_names = "|".join(sorted(HINDI_MONTHS, key=len, reverse=True))
    for match in re.finditer(rf"(\d{{1,2}})\s*({hindi_names})\s*(\d{{4}})?", body):
        day = int(match.group(1))
        month = HINDI_MONTHS[match.group(2)]
        year = int(match.group(3)) if match.group(3) else current_year
        iso = _iso(year, month, day)
        if iso and iso not in seen:
            seen.add(iso)
            hits.append(DateHit(iso, match.group(0).strip(), bool(match.group(3))))
    return hits


def extract_dates(text: str) -> list[str]:
    """Return ISO date strings found in ``text``."""
    return [hit.iso for hit in extract_date_hits(text)]


def extract_senders(text: str) -> list[str]:
    """Find names/handles that appear to be message senders."""
    found: list[str] = []
    for match in re.finditer(r"(?im)^\s*([A-Z][A-Za-z .'_-]{1,24})\s*[:\-]\s", text or ""):
        found.append(match.group(1).strip())
    for match in re.finditer(
        r"(?i)\b(?:from|sender)\s*[:\-]\s*([A-Za-z][A-Za-z .'_-]{1,24})", text or ""
    ):
        found.append(match.group(1).strip())
    cleaned: list[str] = []
    for name in found:
        if name.lower() in {"from", "sender", "to", "date", "time", "subject"}:
            continue
        if name not in cleaned:
            cleaned.append(name)
    return cleaned[:6]


def extract_threats(text: str) -> list[str]:
    """Return short quotes that contain threatening language."""
    threats: list[str] = []
    for sentence in sentences(text):
        lowered = sentence.lower()
        if any(word in lowered for word in THREAT_WORDS) and len(sentence) > 8:
            threats.append(trim(sentence, 160))
    return threats[:5]


def detect_danger(text: str) -> tuple[str, list[str]]:
    """Return a risk level and the danger signals found in the text."""
    lowered = (text or "").lower()
    signals: list[str] = []
    for pattern in DANGER_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            signals.append(match.group(0))
    severe = [signal for signal in signals if any(re.search(p, signal.lower()) for p in SEVERE_PATTERNS)]
    unique = list(dict.fromkeys(signals))
    if severe or len(unique) >= 2:
        return "high", unique[:5]
    if unique:
        return "medium", unique[:5]
    return "low", []


def urgent_help_lines(risk_level: str, language: str = "en") -> list[str]:
    """Short, actionable safety lines shown above everything else."""
    if risk_level != "high":
        return []
    if language == "hi":
        return [
            "अगर आप अभी खतरे में हैं तो 112 पर कॉल करें (पुलिस, एम्बुलेंस)।",
            "महिला हेल्पलाइन 181 - परामर्श, आश्रय और पुलिस सहायता।",
            "1091 - कई राज्यों में महिला/पुलिस सहायता हेल्पलाइन।",
            "साइबर धमकी या तस्वीरें फैलाने की धमकी हो तो 1930 या cybercrime.gov.in।",
            "कोई भरोसेमंद व्यक्ति को अभी बताएँ और सुरक्षित जगह पर जाएँ; मूल सबूत न मिटाएँ।",
        ]
    return [
        "If you are in immediate danger, call 112 (police, ambulance, fire).",
        "Women Helpline 181 - counselling, shelter and police coordination.",
        "1091 - women/police assistance helpline in several states.",
        "For cyber threats or image leaks call 1930 or use cybercrime.gov.in.",
        "Tell one trusted person now and move to a safer place if you can; keep the original files.",
    ]


# ------------------------------------------------------------------ analysis
def analyse_evidence(text: str, evidence_type: str = "screenshot") -> dict[str, Any]:
    """Heuristic analysis of one item's extracted text."""
    body = text or ""
    return {
        "summary": trim(body, 200) or f"{evidence_type.replace('_', ' ')} with no readable text",
        "dates": extract_dates(body),
        "senders": extract_senders(body),
        "threats": extract_threats(body),
        "key_quotes": [trim(sentence, 160) for sentence in sentences(body)[:3]],
        "people": extract_senders(body)[:3],
    }


def contains_keyword(text: str, keyword: str) -> bool:
    """Whole-word match for Latin keywords, substring match for Devanagari."""
    if keyword.isascii():
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None
    return keyword in text


def classify(text: str) -> list[dict[str, Any]]:
    """Keyword multi-label classification with confidence scores."""
    lowered = (text or "").lower()
    scores: list[tuple[str, int]] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if contains_keyword(lowered, keyword))
        if hits:
            scores.append((category, hits))
    scores.sort(key=lambda item: item[1], reverse=True)
    if not scores:
        return [{"category": "other", "confidence": 0.4}]
    results = [
        {"category": category, "confidence": round(min(0.92, 0.45 + 0.12 * hits), 2)}
        for category, hits in scores[:3]
    ]
    return results


def category_label(category: str, language: str = "en") -> str:
    """Human label for a category slug."""
    labels_hi = {
        "domestic_violence": "घरेलू हिंसा",
        "workplace_sexual_harassment": "कार्यस्थल पर यौन उत्पीड़न",
        "stalking": "पीछा करना / स्टॉकिंग",
        "cyber_harassment": "साइबर उत्पीड़न / तस्वीरों का दुरुपयोग",
        "dowry_related": "दहेज संबंधी मांग",
        "other": "अन्य उत्पीड़न",
    }
    if language == "hi":
        return labels_hi.get(category, CATEGORY_LABELS.get(category, category))
    return CATEGORY_LABELS.get(category, category)


# -------------------------------------------------------------------- intake
def missing_intake_info(text: str) -> list[str]:
    """Return the critical pieces of information still missing."""
    body = text or ""
    lowered = body.lower()
    missing: list[str] = []
    if len(body.split()) < 8:
        missing.append("what")
    if not extract_date_hits(body) and not any(word in lowered for word in RELATIVE_TIME):
        missing.append("when")
    if not any(word in lowered for word in RELATION_WORDS) and not extract_senders(body):
        missing.append("who")
    if not any(word in lowered for word in SAFETY_WORDS):
        missing.append("safety")
    return missing


FOLLOWUPS = {
    "en": {
        "what": "In one or two lines, what happened most recently?",
        "when": "When did this happen? A date, or 'last week' / 'last night' is enough.",
        "who": "Who is doing this? (for example husband, in-laws, boss, colleague, neighbour, an online account)",
        "safety": "Are you safe right now? Do you fear the person will harm you or someone close to you?",
    },
    "hi": {
        "what": "सबसे हाल में क्या हुआ? एक-दो पंक्तियों में बताइए।",
        "when": "यह कब हुआ? तारीख या 'पिछले हफ्ते' / 'कल रात' लिखना काफी है।",
        "who": "यह कौन कर रहा है? (जैसे पति, ससुराल वाले, बॉस, सहकर्मी, पड़ोसी, कोई ऑनलाइन अकाउंट)",
        "safety": "क्या आप अभी सुरक्षित हैं? क्या आपको डर है कि वह व्यक्ति आपको या आपके किसी अपने को नुकसान पहुँचा सकता है?",
    },
}


def followup_questions(text: str, language: str = "en") -> list[str]:
    """Up to three questions for whatever the story does not cover yet."""
    missing = missing_intake_info(text)
    table = FOLLOWUPS["hi" if language == "hi" else "en"]
    ordered = ["safety", "what", "when", "who"]
    questions = [table[key] for key in ordered if key in missing]
    return questions[:3]


# ------------------------------------------------------------------- timeline
def build_timeline(
    story: str, evidence_items: Iterable[dict[str, Any]], language: str = "en"
) -> tuple[list[dict[str, Any]], list[str]]:
    """Merge story sentences and evidence into one chronological list."""
    items: list[dict[str, Any]] = []
    gaps: list[str] = []
    story_items: list[dict[str, Any]] = []

    for sentence in sentences(story):
        hits = extract_date_hits(sentence)
        if not hits:
            continue
        story_items.append(
            {
                "date": hits[0].iso,
                "date_display": hits[0].raw,
                "title": trim(sentence, 70),
                "detail": trim(sentence, 400),
                "source": "story",
                "evidence_label": None,
                "confidence": 0.7 if hits[0].has_year else 0.5,
                "year_known": hits[0].has_year,
                "sort_key": hits[0].iso if hits[0].has_year else f"9999-{hits[0].iso[5:]}",
            }
        )
    if not story_items and (story or "").strip():
        gaps.append(
            "आपकी कहानी में कोई तारीख नहीं मिली - तारीख जोड़ने से समयरेखा मजबूत होगी।"
            if language == "hi"
            else "No date was found in your story - adding dates will make the timeline stronger."
        )

    for item in evidence_items:
        label = item.get("label") or "evidence"
        text = " ".join(
            filter(None, [item.get("ocr_text") or "", item.get("transcript") or "", item.get("ocr_note") or ""])
        )
        analysis = item.get("analysis") or {}
        dates = [DateHit(iso, iso, True) for iso in analysis.get("dates", [])] or extract_date_hits(text)
        if dates:
            for hit in dates[:3]:
                items.append(
                    {
                        "date": hit.iso,
                        "date_display": hit.raw,
                        "title": f"{label}: {trim(analysis.get('summary') or text, 70) or 'evidence'}",
                        "detail": trim(text, 400),
                        "source": "evidence",
                        "evidence_label": label,
                        "confidence": 0.8,
                        "year_known": hit.has_year,
                        "sort_key": hit.iso if hit.has_year else f"9999-{hit.iso[5:]}",
                    }
                )
        else:
            uploaded = str(item.get("uploaded_at") or "")[:10]
            gap = (
                f"{label} में कोई तारीख नहीं मिली; इसे अपलोड तारीख {uploaded} पर रखा गया है।"
                if language == "hi"
                else f"No date found in {label}; placed at upload date {uploaded}."
            )
            gaps.append(gap)
            if text.strip():
                items.append(
                    {
                        "date": uploaded or None,
                        "date_display": uploaded or "date unknown",
                        "title": f"{label}: {trim(analysis.get('summary') or text, 70)}",
                        "detail": trim(text, 400),
                        "source": "evidence",
                        "evidence_label": label,
                        "confidence": 0.4,
                        "year_known": True,
                        "sort_key": uploaded or "9999-12-31",
                    }
                )

    items.extend(story_items)
    items.sort(key=lambda entry: str(entry.get("sort_key") or ""))
    for entry in items:
        entry.pop("sort_key", None)
    return items, gaps


# ---------------------------------------------------------------- action plan
def build_action_plan(
    risk_level: str, categories: Iterable[str], language: str = "en"
) -> list[dict[str, Any]]:
    """Prioritised, plain-language steps (offline template)."""
    category_set = set(categories)
    hindi = language == "hi"
    steps: list[dict[str, Any]] = []

    if risk_level == "high":
        steps.append(
            {
                "priority": 1,
                "title": "अभी सुरक्षा" if hindi else "Safety first, right now",
                "detail": (
                    "112 पर कॉल करें या 181 से बात करें। किसी भरोसेमंद व्यक्ति को बताएँ और सुरक्षित जगह जाएँ।"
                    if hindi
                    else "Call 112 or 181. Tell one trusted person where you are and move to a safer place."
                ),
                "contact": "112 / 181",
            }
        )
    else:
        steps.append(
            {
                "priority": 1,
                "title": "एक भरोसेमंद व्यक्ति को बताएँ" if hindi else "Tell one trusted person",
                "detail": (
                    "किसी ऐसे व्यक्ति को बताएँ जो आपकी बात सुने और ज़रूरत पड़ने पर साथ आए।"
                    if hindi
                    else "Share what is happening with someone who will listen and can accompany you if needed."
                ),
                "contact": "",
            }
        )

    steps.append(
        {
            "priority": 2,
            "title": "सबूत सुरक्षित रखें" if hindi else "Preserve the evidence",
            "detail": (
                "मूल फोटो, वीडियो और चैट न मिटाएँ। इस ऐप में अपलोड करें और 'अखंडता जाँचें' दबाएँ ताकि हर फ़ाइल का SHA-256 हैश दर्ज हो जाए।"
                if hindi
                else "Do not delete original photos, videos or chats. Upload them here and use 'Verify integrity' so every file gets a stored SHA-256 hash."
            ),
            "contact": "",
        }
    )

    if "domestic_violence" in category_set or "dowry_related" in category_set:
        steps.append(
            {
                "priority": 3,
                "title": "जिला संरक्षण अधिकारी से मिलें" if hindi else "Contact the district Protection Officer",
                "detail": (
                    "घरेलू हिंसा अधिनियम के तहत घरेलू घटना रिपोर्ट (DIR) दर्ज कराएँ और मजिस्ट्रेट के सामने आवेदन दें। वन स्टॉप सेंटर भी मदद करता है।"
                    if hindi
                    else "Ask for a Domestic Incident Report (DIR) and an application before the magistrate under the Domestic Violence Act. A One Stop Centre can help."
                ),
                "contact": "181 / One Stop Centre",
            }
        )
    if "workplace_sexual_harassment" in category_set:
        steps.append(
            {
                "priority": 3,
                "title": "आंतरिक समिति (IC) को लिखित शिकायत" if hindi else "Write to the Internal Committee (IC)",
                "detail": (
                    "HR से IC की अध्यक्ष और सदस्यों के नाम माँगें। लिखित शिकायत में तारीख, जगह, गवाह और सबूत लिखें। IC न हो तो जिला स्तर की स्थानीय समिति (LC) से संपर्क करें।"
                    if hindi
                    else "Ask HR for the IC chairperson and members. Put dates, place, witnesses and evidence in writing. If no IC exists, contact the district Local Committee (LC)."
                ),
                "contact": "SHe-Box",
            }
        )
    if "cyber_harassment" in category_set or "stalking" in category_set:
        steps.append(
            {
                "priority": 3,
                "title": "साइबर शिकायत दर्ज करें" if hindi else "Report to the cyber crime portal",
                "detail": (
                    "cybercrime.gov.in पर शिकायत करें और पावती संख्या रखें। प्रोफ़ाइल लिंक, यूज़रनेम और तारीख के साथ स्क्रीनशॉट सुरक्षित रखें; प्लेटफ़ॉर्म पर भी रिपोर्ट करें।"
                    if hindi
                    else "File at cybercrime.gov.in and keep the acknowledgement number. Save screenshots with profile links, usernames and dates, and also report to the platform."
                ),
                "contact": "1930 / cybercrime.gov.in",
            }
        )

    steps.append(
        {
            "priority": 4,
            "title": "ये दस्तावेज़ साथ रखें" if hindi else "Keep these documents ready",
            "detail": (
                "पहचान पत्र, इस ऐप से बना PDF पैकेट, टाइमलाइन की प्रति, स्क्रीनशॉट, और चोट हो तो मेडिकल रिकॉर्ड। मूल फ़ाइलें किसी को न दें, प्रति दें।"
                if hindi
                else "ID proof, the PDF packet from this app, a printed timeline, screenshots, and medical records if you were injured. Hand over copies, never your only originals."
            ),
            "contact": "",
        }
    )
    steps.append(
        {
            "priority": 5,
            "title": "मुफ़्त कानूनी सहायता लें" if hindi else "Get free legal aid",
            "detail": (
                "जिला विधिक सेवा प्राधिकरण (DLSA) में महिलाओं के लिए मुफ़्त वकील मिलता है। NALSA हेल्पलाइन 15100। किसी भी कानूनी कदम से पहले वकील से पुष्टि करें।"
                if hindi
                else "The District Legal Services Authority (DLSA) provides a free lawyer to women. NALSA helpline 15100. Confirm every legal step with a lawyer before filing."
            ),
            "contact": "15100",
        }
    )
    return steps


# -------------------------------------------------------------- complaint draft
def build_complaint(
    case_title: str,
    story: str,
    evidence: Iterable[dict[str, Any]],
    timeline: Iterable[dict[str, Any]],
    categories: Iterable[str],
    legal_matches: Iterable[dict[str, Any]],
    language: str = "en",
    feedback: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Compose a complaint using only supplied facts, evidence refs and citations."""
    hindi = language == "hi"
    category_list = list(categories) or ["other"]
    label = ", ".join(category_label(category, language) for category in category_list)
    facts = [sentence for sentence in sentences(story) if len(sentence.split()) > 2][:10]
    evidence_list = list(evidence)
    citations = [match.get("kb_id") for match in legal_matches if match.get("kb_id")]
    evidence_refs = [item.get("label", "E?") for item in evidence_list]
    timeline_list = list(timeline)

    lines: list[str] = []
    if hindi:
        lines.append("सेवा में,")
        lines.append("थाना प्रभारी / संरक्षण अधिकारी")
        lines.append("")
        lines.append(f"विषय: {label} के संबंध में शिकायत - {case_title}")
        lines.append("")
        lines.append("महोदय/महोदया,")
        lines.append("")
        lines.append(
            "मैं नीचे लिखी घटनाओं की शिकायत कर रही हूँ। यह विवरण केवल उन बातों पर आधारित है जो मैंने स्वयं बताई हैं।"
        )
        lines.append("")
        for index, fact in enumerate(facts, start=1):
            lines.append(f"{index}. {fact}")
        lines.append("")
        lines.append("मेरे पास निम्नलिखित साक्ष्य सुरक्षित हैं (हर फ़ाइल का SHA-256 हैश दर्ज है):")
        for item in evidence_list:
            excerpt = trim(item.get("ocr_text") or item.get("transcript") or "", 120)
            lines.append(
                f"- {item.get('label')} ({item.get('evidence_type', 'साक्ष्य')}, "
                f"अपलोड {str(item.get('uploaded_at', ''))[:10]}): "
                f"SHA-256 {str(item.get('sha256', ''))[:32]}…"
                + (f"; विवरण: \"{excerpt}\"" if excerpt else "")
            )
        if timeline_list:
            lines.append("")
            lines.append("समयरेखा:")
            for event in timeline_list[:12]:
                lines.append(
                    f"- {event.get('date_display') or event.get('date') or 'तारीख नहीं'}: "
                    f"{event.get('title') or event.get('detail', '')}"
                )
        lines.append("")
        lines.append("सामान्य जानकारी जो मेरी स्थिति पर लागू हो सकती है (वकील से पुष्टि के बाद):")
        for match in legal_matches:
            lines.append(f"- [{match.get('kb_id')}] {match.get('act')} - {match.get('title')}")
        lines.append("")
        lines.append(
            "मैं अनुरोध करती हूँ कि यह शिकायत दर्ज की जाए और मुझे इसकी प्रति दी जाए। मैं मूल फ़ाइलें दिखाने और बयान देने के लिए तैयार हूँ।"
        )
        lines.append("")
        lines.append("स्थान:")
        lines.append("दिनांक:")
        lines.append("हस्ताक्षर:")
    else:
        lines.append("To,")
        lines.append("The Station House Officer / The Protection Officer")
        lines.append("")
        lines.append(f"Subject: Complaint regarding {label} - {case_title}")
        lines.append("")
        lines.append("Respected Sir/Madam,")
        lines.append("")
        lines.append(
            "I am reporting the incidents described below. This statement is based only on facts I have provided."
        )
        lines.append("")
        for index, fact in enumerate(facts, start=1):
            lines.append(f"{index}. {fact}")
        lines.append("")
        lines.append(
            "I have preserved the following evidence. Each file was hashed with SHA-256 when it was stored, "
            "so any later change to the file can be detected:"
        )
        for item in evidence_list:
            excerpt = trim(item.get("ocr_text") or item.get("transcript") or "", 120)
            lines.append(
                f"- {item.get('label')} ({item.get('evidence_type', 'evidence')}, "
                f"uploaded {str(item.get('uploaded_at', ''))[:10]}): "
                f"SHA-256 {str(item.get('sha256', ''))[:32]}…"
                + (f"; content: \"{excerpt}\"" if excerpt else "")
            )
        if timeline_list:
            lines.append("")
            lines.append("Timeline:")
            for event in timeline_list[:12]:
                lines.append(
                    f"- {event.get('date_display') or event.get('date') or 'date not stated'}: "
                    f"{event.get('title') or event.get('detail', '')}"
                )
        lines.append("")
        lines.append(
            "General information that may apply to my situation (to be confirmed with a lawyer before filing):"
        )
        for match in legal_matches:
            lines.append(f"- [{match.get('kb_id')}] {match.get('act')} - {match.get('title')}")
        lines.append("")
        lines.append(
            "I request that this complaint be registered and that I be given a copy. I am willing to show the "
            "original files and to give a statement."
        )
        lines.append("")
        lines.append("Place:")
        lines.append("Date:")
        lines.append("Signature:")

    if feedback:
        lines.append("")
        lines.append(
            "Note (added by the self-check, please review): " + "; ".join(dict.fromkeys(feedback))
        )

    subject = (
        f"{'शिकायत' if hindi else 'Complaint'}: {label} - {case_title}"
    )
    return {
        "subject": subject,
        "body": "\n".join(lines),
        "evidence_refs": evidence_refs,
        "citations": [citation for citation in citations if citation],
        "facts_used": facts,
    }


# ------------------------------------------------------------------- verifier
CITATION_RE = re.compile(r"\[(KB-\d+)\]")
EVIDENCE_REF_RE = re.compile(r"\bE\d+\b")
DATE_IN_DRAFT_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def verify(draft_text: str, input_text: str, known_kb_ids: Iterable[str]) -> dict[str, Any]:
    """Check citations, evidence references and dates against the inputs."""
    known = {str(kb_id) for kb_id in known_kb_ids}
    problems: list[str] = []
    missing_citations: list[str] = []
    unsupported: list[str] = []
    found = CITATION_RE.findall(draft_text or "")
    if not found:
        problems.append("The draft does not cite any knowledge-base entry.")
    for kb_id in found:
        if kb_id not in known:
            missing_citations.append(kb_id)
    if missing_citations:
        problems.append(f"Unknown KB citations: {', '.join(sorted(set(missing_citations)))}.")
    for date in DATE_IN_DRAFT_RE.findall(draft_text or ""):
        if date not in (input_text or ""):
            unsupported.append(date)
    if unsupported:
        problems.append(
            "Dates in the draft that are not traceable to your inputs: "
            + ", ".join(sorted(set(unsupported)))
        )
    return {
        "passed": not problems,
        "problems": problems,
        "missing_citations": sorted(set(missing_citations)),
        "unsupported_facts": sorted(set(unsupported)),
    }
