import os
import re
import random
import requests
from bs4 import BeautifulSoup
import streamlit as st
import google.generativeai as genai

# ---------------------------
# Page config
# ---------------------------
st.set_page_config(page_title="Trailhead Quiz Generator", layout="centered")

# ---------------------------
# API key (Streamlit Cloud: Settings → Secrets → gemini_api_key)
# ---------------------------
API_KEY = st.secrets.get("gemini_api_key", os.getenv("GEMINI_API_KEY"))
if API_KEY:
    genai.configure(api_key=API_KEY)

# ---------------------------
# Header + short description (kept from the earlier design)
# ---------------------------
st.title("Trailhead Quiz Generator 📝 (Gemini Edition)")
st.write(
    "Paste a **Trailhead URL** or **content text**, then generate a quick quiz to check your understanding.\n\n"
    "**How it works:**\n"
    "1) Provide a URL or paste the page text → 2) Click **Generate Quiz** → 3) Answer → 4) **Submit** to see your score → 5) **Retake** or **Generate New Quiz**."
)

# Sidebar help
with st.sidebar:
    st.header("How to use")
    st.markdown(
        "- Choose **Paste URL** or **Paste Text**.\n"
        "- Click **Preview Page Text** (for URL) to confirm extraction.\n"
        "- Click **Generate Quiz**.\n"
        "- Answer each question and click **Submit Answers**.\n"
        "- Use **Retake Quiz** to try the same set again (options reshuffled).\n"
        "- Use **Generate New Quiz** for a different set from the same content.\n"
        "- **Clear Inputs** resets URL/text and quiz state."
    )
    st.markdown("---")
    st.markdown("**Tip:** Some pages block scraping. If URL fails, copy & paste the content instead.")

# ---------------------------
# Utilities
# ---------------------------
def extract_text_from_url(url: str) -> str:
    """Best-effort extraction of readable text from a webpage."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=25)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        chunks = []
        for tag in soup.find_all(["h1", "h2", "h3", "p", "li"]):
            text = tag.get_text(separator=" ", strip=True)
            if text:
                chunks.append(text)
        text = "\n".join(chunks).strip()
        # Trim very long pages to keep prompts reliable
        return text[:15000]
    except Exception as e:
        st.error(f"Couldn't fetch the page: {e}")
        return ""

def parse_quiz_from_text(raw_quiz: str):
    """
    Parse Gemini output in the numbered format:
    1. Question
       A. ...
       B. ...
       C. ...
       D. ...
       Correct Answer: X
       Explanation: ...
    Returns: list of {question, options (raw strings), correct (letter), explanation}
    """
    parts = re.split(r"(?m)^\s*\d+\.\s+", raw_quiz)
    parts = [p.strip() for p in parts if p.strip()]
    quiz = []

    for block in parts:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        # First non-empty line is the question
        question_text = lines[0]

        # Options (accept 'A. ' or 'A) ')
        options = []
        for ln in lines:
            m = re.match(r"^([A-D])[\).]\s*(.*)$", ln)
            if m:
                options.append(f"{m.group(1)}. {m.group(2)}")

        # Correct answer letter
        correct_match = next((ln for ln in lines if ln.lower().startswith("correct answer")), None)
        correct_letter = None
        if correct_match and ":" in correct_match:
            candidate = correct_match.split(":", 1)[1].strip()
            m2 = re.match(r"^([A-D])\b", candidate, flags=re.IGNORECASE)
            if m2:
                correct_letter = m2.group(1).upper()

        # Explanation
        explanation_line = next((ln for ln in lines if ln.lower().startswith("explanation")), None)
        explanation = "No explanation provided."
        if explanation_line and ":" in explanation_line:
            explanation = explanation_line.split(":", 1)[1].strip()

        if question_text and options and correct_letter in {"A", "B", "C", "D"}:
            quiz.append(
                {
                    "question": question_text,
                    "options": options,   # keep original-lettered strings for now
                    "correct": correct_letter,
                    "explanation": explanation,
                }
            )

    return quiz

def _build_shuffled_quiz(original_quiz):
    """
    Build a shuffled version where:
    - option texts are shuffled
    - options are relabeled A-D consistently
    - 'correct' updated to the new letter
    Returns list of {"question","options": ["A. text"...], "correct": "A"/"B"..., "explanation"}
    """
    shuffled = []
    for q in original_quiz:
        # original options like "A. text"
        opt_texts = []
        for opt in q["options"]:
            m = re.match(r"^[A-D][\).]\s*(.*)$", opt)
            if m:
                opt_texts.append(m.group(1).strip())
            else:
                opt_texts.append(opt.strip())

        # find original correct text using original 'correct' letter
        orig_correct_text = None
        if q.get("correct"):
            letter = q["correct"]
            for opt in q["options"]:
                if opt.startswith(f"{letter}.") or opt.startswith(f"{letter})"):
                    m2 = re.match(r"^[A-D][\).]\s*(.*)$", opt)
                    orig_correct_text = m2.group(1).strip() if m2 else opt[2:].strip()
                    break

        # shuffle option texts
        random.shuffle(opt_texts)

        # re-label as A., B., C., D.
        new_options = []
        new_correct_letter = None
        for idx, txt in enumerate(opt_texts):
            letter = chr(65 + idx)
            labeled = f"{letter}. {txt}"
            new_options.append(labeled)
            if orig_correct_text is not None and txt == orig_correct_text:
                new_correct_letter = letter

        # fallback: if we couldn't locate correct_text match, try fallback deriving by position if lengths match
        if new_correct_letter is None and q.get("correct"):
            try:
                orig_idx = ord(q["correct"]) - 65
                if 0 <= orig_idx < len(opt_texts):
                    # map original index-to-text then find it in shuffled
                    target_text = q["options"][orig_idx]
                    m3 = re.match(r"^[A-D][\).]\s*(.*)$", target_text)
                    target_text = m3.group(1).strip() if m3 else target_text
                    for idx, txt in enumerate(opt_texts):
                        if txt == target_text:
                            new_correct_letter = chr(65 + idx)
                            break
            except Exception:
                new_correct_letter = None

        shuffled.append({
            "question": q["question"],
            "options": new_options,
            "correct": new_correct_letter,
            "explanation": q.get("explanation", "No explanation provided.")
        })
    return shuffled

def generate_quiz(content: str):
    """Ask Gemini to produce 5 MCQs in a strict, easy-to-parse format."""
    if not API_KEY:
        st.error("No Gemini API key found. Add it in Streamlit **Settings → Secrets** as `gemini_api_key`.")
        return []

    prompt = f"""
You are a strict quiz generator. Based on the content below, create **exactly 5** multiple-choice questions.
Format each question EXACTLY like this:

1. Question text
   A. option
   B. option
   C. option
   D. option
   Correct Answer: X
   Explanation: one short sentence

Only produce the quiz in the format above. No extra commentary.

Content:
{content}
"""

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        with st.spinner("Generating quiz..."):
            result = model.generate_content(prompt)

        raw = (result.text or "").strip()
        if not raw:
            st.error("Gemini returned an empty response. Try again or paste text instead of URL.")
            return []

        quiz = parse_quiz_from_text(raw)

        if not quiz:
            st.error("Could not parse the quiz output. Please try Generate New Quiz or paste shorter content.")
            return []

        # Build a shuffled, labeled version that keeps letters A-D consistent
        shuffled = _build_shuffled_quiz(quiz)
        return {"original": quiz, "shuffled": shuffled}
    except Exception as e:
        st.error(f"Quiz generation error: {e}")
        return []

def clear_all_state():
    """Fully reset inputs and quiz state."""
    for k in list(st.session_state.keys()):
        try:
            del st.session_state[k]
        except Exception:
            pass
    st.rerun()

# ---------------------------
# Session state init
# ---------------------------
if "input_mode" not in st.session_state:
    st.session_state.input_mode = "Paste URL"
if "page_text" not in st.session_state:
    st.session_state.page_text = ""
if "quiz" not in st.session_state:
    st.session_state.quiz = {}
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "submitted" not in st.session_state:
    st.session_state.submitted = False

# ---------------------------
# Input mode + fields
# ---------------------------
st.session_state.input_mode = st.radio("Choose input method:", ["Paste URL", "Paste Text"], horizontal=True)

if st.session_state.input_mode == "Paste URL":
    url = st.text_input("Enter Trailhead page URL:", value=st.session_state.get("url", ""))
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Preview Page Text"):
            if not url:
                st.warning("Please enter a URL.")
            else:
                st.session_state.url = url
                st.session_state.page_text = extract_text_from_url(url)
                if st.session_state.page_text:
                    st.success("Page text extracted. Scroll to preview below.")
                else:
                    st.warning("No text extracted. Try copying the page text manually.")
    with c2:
        if st.button("Clear Inputs"):
            clear_all_state()

    if st.session_state.page_text:
        with st.expander("Preview extracted text"):
            st.write(st.session_state.page_text)

else:
    st.session_state.page_text = st.text_area(
        "Paste Trailhead page content here:",
        value=st.session_state.get("page_text", ""),
        height=240,
    )
    if st.button("Clear Inputs"):
        clear_all_state()

# ---------------------------
# Generate quiz
# ---------------------------
if st.button("Generate Quiz"):
    if not st.session_state.page_text:
        st.warning("Please provide content (paste text or preview URL first).")
    else:
        result = generate_quiz(st.session_state.page_text)
        # store both original parse and shuffled display version
        st.session_state.quiz = result  # result = {"original": [...], "shuffled": [...]}
        st.session_state.answers = {}
        st.session_state.submitted = False
        st.rerun()

# ---------------------------
# Quiz UI (display using shuffled, labeled options)
# ---------------------------
if st.session_state.quiz and "shuffled" in st.session_state.quiz:
    st.write("### Quiz")
    shuffled = st.session_state.quiz["shuffled"]

    for i, q in enumerate(shuffled):
        st.write(f"**Q{i+1}: {q['question']}**")
        # radio choices will be strings like "A. text", "B. text", ...
        # Keep storing selection in answers dict keyed by index (as before)
        st.session_state.answers[i] = st.radio(
            f"Select answer for Q{i+1}",
            q["options"],
            key=f"q{i}",
            index=0 if (f"q{i}" in st.session_state and st.session_state.get(f"q{i}") in q["options"]) else 0
        )

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Submit Answers"):
            st.session_state.submitted = True
            st.rerun()

    with c2:
        if st.button("Retake Quiz"):
            # Recreate shuffled display options from original (so we remove label-letters from previous shuffle)
            if st.session_state.quiz and "original" in st.session_state.quiz:
                st.session_state.quiz["shuffled"] = _build_shuffled_quiz(st.session_state.quiz["original"])
            # Remove radio widget keys so they rebuild with no preselection
            for i in range(len(st.session_state.quiz.get("shuffled", []))):
                key = f"q{i}"
                if key in st.session_state:
                    try:
                        del st.session_state[key]
                    except Exception:
                        pass
            # Clear stored answers and submission state
            st.session_state.answers = {}
            st.session_state.submitted = False
            st.rerun()

    with c3:
        if st.button("Generate New Quiz"):
            if st.session_state.page_text:
                result = generate_quiz(st.session_state.page_text)
                st.session_state.quiz = result
                st.session_state.answers = {}
                st.session_state.submitted = False
                # clear old answer widget keys
                for i in range(50):
                    key = f"q{i}"
                    if key in st.session_state:
                        try:
                            del st.session_state[key]
                        except Exception:
                            pass
                st.rerun()
            else:
                st.warning("No source content to regenerate from. Provide URL/text again.")

# ---------------------------
# Review mode
# ---------------------------
if st.session_state.submitted and st.session_state.quiz and "shuffled" in st.session_state.quiz:
    st.write("### 🔍 Review Mode")
    score = 0
    shuffled = st.session_state.quiz["shuffled"]
    for i, q in enumerate(shuffled):
        selected = st.session_state.answers.get(i)
        # selected is like "A. text" or None
        correct_letter = q.get("correct")
        correct_option = next((opt for opt in q["options"] if opt.startswith(f"{correct_letter}.")), None) if correct_letter else None
        if selected == correct_option:
            st.success(f"✅ Q{i+1}: Correct")
            score += 1
        else:
            st.error(f"❌ Q{i+1}: Wrong. Correct answer: {correct_option}")
        # Show explanation
        st.info(f"**Explanation:** {q.get('explanation', 'No explanation provided.')}")
    st.write(f"## 🎯 Your Score: {score}/{len(shuffled)}")
