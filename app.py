# app.py
import os
import re
import random
import requests
import streamlit as st
import google.generativeai as genai
from bs4 import BeautifulSoup

# ---------------------------
# Page + API setup
# ---------------------------
st.set_page_config(page_title="Trailhead Quiz Generator", layout="centered")
st.title("Trailhead Quiz Generator 📝 (Gemini Edition)")

# Look up key from Streamlit Secrets or env var
API_KEY = st.secrets.get("gemini_api_key", os.getenv("GEMINI_API_KEY"))
if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
    except Exception as e:
        st.error(f"Failed to configure Gemini client: {e}")
else:
    st.warning(
        "No Gemini API key found. Add it in Streamlit → Settings → Secrets as `gemini_api_key`, "
        "or set environment variable GEMINI_API_KEY (local)."
    )

# ---------------------------
# Sidebar help
# ---------------------------
with st.sidebar:
    st.header("How to use")
    st.markdown(
        "- Choose **Paste URL** or **Paste Text** on the main page.\n"
        "- For URL: click **Preview Page Text** to extract page content (some pages block scraping).\n"
        "- Click **Generate Quiz** to ask Gemini to create 5 MCQs.\n"
        "- Answer questions and click **Submit Answers** to score.\n"
        "- Use **Retake Quiz** to retry the same questions (options will be reshuffled and answers cleared).\n"
        "- Use **Generate New Quiz** to ask for a different set from the same content.\n"
        "- **Clear Inputs** resets the app so you can paste a new page.\n"
    )
    st.markdown("---")
    st.markdown("Tip: If Preview fails for a URL, copy the page text and use Paste Text.")

# ---------------------------
# Helper: extract text from URL
# ---------------------------
def extract_text_from_url(url: str, max_chars: int = 15000) -> str:
    """
    Best-effort extraction of readable text from a webpage.
    Returns trimmed text or empty string on failure.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
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
        if not text:
            return ""
        # Trim to keep prompt sizes reasonable
        return text[:max_chars]
    except Exception as e:
        # Return empty so caller can decide fallback
        return ""

# ---------------------------
# Helper: parse Gemini output into structured quiz
# ---------------------------
def parse_quiz_from_text(raw_quiz: str):
    """
    Expect Gemini to produce numbered questions of the form:
    1. Question text
       A. option
       B. option
       C. option
       D. option
       Correct Answer: X
       Explanation: one sentence

    This returns a list of dicts:
    {
      "question": "text",
      "choices": [{"text":"...","is_correct":True/False}, ...],
      "explanation": "..."
    }
    """
    if not raw_quiz:
        return []

    parts = re.split(r"(?m)^\s*\d+\.\s+", raw_quiz)
    parts = [p.strip() for p in parts if p.strip()]
    quiz = []

    for block in parts:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        question_text = lines[0]

        # Extract options texts (handles "A. ..." or "A) ...")
        option_texts = []
        for ln in lines:
            m = re.match(r"^([A-D])[\).]\s*(.*)$", ln)
            if m:
                option_texts.append((m.group(1).upper(), m.group(2).strip()))

        # Find correct letter
        correct_letter = None
        correct_line = next((ln for ln in lines if ln.lower().startswith("correct answer")), None)
        if correct_line and ":" in correct_line:
            candidate = correct_line.split(":", 1)[1].strip()
            m2 = re.match(r"^([A-D])\b", candidate, flags=re.IGNORECASE)
            if m2:
                correct_letter = m2.group(1).upper()

        # Explanation
        explanation_line = next((ln for ln in lines if ln.lower().startswith("explanation")), None)
        explanation = "No explanation provided."
        if explanation_line and ":" in explanation_line:
            explanation = explanation_line.split(":", 1)[1].strip()

        # Build choices list preserving which is correct
        choices = []
        for letter, txt in option_texts:
            is_correct = (letter == correct_letter)
            choices.append({"text": txt, "is_correct": is_correct})

        # Only accept if we found 4 choices and a correct mark
        if len(choices) >= 2 and any(c["is_correct"] for c in choices):
            # If more than 4 exist (rare), trim to first 4
            if len(choices) > 4:
                choices = choices[:4]
            quiz.append({"question": question_text, "choices": choices, "explanation": explanation})

    return quiz

# ---------------------------
# Helper: generate quiz using Gemini
# ---------------------------
def generate_quiz(content: str, num_questions: int = 5):
    """
    Send prompt to Gemini and parse the result. Returns list of structured questions.
    """
    if not API_KEY:
        st.error("No Gemini key configured (see sidebar). Can't generate quiz.")
        return []

    # Prompt: strict, easy-to-parse format
    prompt = f"""
You are a strict quiz-maker. Based on the content below, create exactly {num_questions} multiple-choice questions.
Format each question exactly like this:

1. Question text
   A. option
   B. option
   C. option
   D. option
   Correct Answer: X
   Explanation: one short sentence

Only return the questions in the format above. No extra commentary.

Content:
{content}
"""

    try:
        with st.spinner("Generating quiz from Gemini..."):
            model = genai.GenerativeModel("gemini-1.5-flash")
            result = model.generate_content(prompt)

        raw = (result.text or "").strip()
        if not raw:
            st.error("Gemini returned an empty response. Try again or paste the content instead.")
            return []

        parsed = parse_quiz_from_text(raw)

        if not parsed:
            st.error(
                "Could not parse the quiz generated by Gemini. "
                "Try Generate New Quiz, or paste a shorter/simpler portion of the page."
            )
        else:
            # For more learning value, randomize order of choices on initial generation
            for q in parsed:
                random.shuffle(q["choices"])
        return parsed
    except Exception as e:
        st.error(f"Error generating quiz: {e}")
        return []

# ---------------------------
# Helper: clear all session state (safe)
# ---------------------------
def clear_all_state():
    keys = list(st.session_state.keys())
    for k in keys:
        # keep Streamlit's internal state keys safe — but session_state keys are ours, safe to delete
        try:
            del st.session_state[k]
        except Exception:
            pass
    # reload fresh UI
    st.experimental_rerun()

# ---------------------------
# Session default init
# ---------------------------
if "page_text" not in st.session_state:
    st.session_state.page_text = ""
if "page_url" not in st.session_state:
    st.session_state.page_url = ""
if "quiz" not in st.session_state:
    st.session_state.quiz = []
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "results" not in st.session_state:
    st.session_state.results = {}
if "score" not in st.session_state:
    st.session_state.score = None

# ---------------------------
# Input UI
# ---------------------------
st.markdown("### 1) Provide a Trailhead page or paste text")
input_mode = st.radio("Input method:", ["Paste URL", "Paste Text"], horizontal=True)

col1, col2 = st.columns([3, 1])

if input_mode == "Paste URL":
    with col1:
        url = st.text_input("Trailhead page URL", value=st.session_state.get("page_url", ""))
    with col2:
        if st.button("Preview Page Text"):
            if not url:
                st.warning("Please enter a URL.")
            else:
                st.session_state.page_url = url
                st.session_state.page_text = extract_text_from_url(url)
                if st.session_state.page_text:
                    st.success("Page text extracted. Scroll to preview below.")
                else:
                    st.warning("No text extracted (page may block scraping). Try paste text.")
        if st.button("Clear Inputs"):
            clear_all_state()
else:
    with col1:
        pasted = st.text_area(
            "Paste Trailhead page content here (or a portion):",
            value=st.session_state.get("page_text", ""),
            height=260,
        )
    with col2:
        if st.button("Clear Inputs"):
            clear_all_state()
    # Save pasted text immediately in session for later use
    if pasted is not None:
        st.session_state.page_text = pasted

if st.session_state.get("page_text"):
    with st.expander("Preview extracted/pasted text (first 4000 chars)"):
        st.write(st.session_state.page_text[:4000])

# ---------------------------
# Generate quiz button
# ---------------------------
st.markdown("### 2) Generate / regenerate quiz")
gen_col1, gen_col2, gen_col3 = st.columns([1, 1, 1])

with gen_col1:
    if st.button("Generate Quiz"):
        if not st.session_state.page_text:
            st.warning("Provide page text (paste it or preview from URL) before generating a quiz.")
        else:
            st.session_state.quiz = generate_quiz(st.session_state.page_text)
            # Reset any prior result info
            st.session_state.submitted = False
            st.session_state.results = {}
            st.session_state.score = None
            # Remove any per-question radio keys so widgets rebuild cleanly
            for i in range(50):  # clear a reasonable range of possible question keys
                k = f"q{i}"
                if k in st.session_state:
                    del st.session_state[k]
            st.experimental_rerun()

with gen_col2:
    if st.button("Generate New Quiz"):
        if not st.session_state.page_text:
            st.warning("No source content. Paste text or preview URL first.")
        else:
            st.session_state.quiz = generate_quiz(st.session_state.page_text)
            st.session_state.submitted = False
            st.session_state.results = {}
            st.session_state.score = None
            for i in range(50):
                k = f"q{i}"
                if k in st.session_state:
                    del st.session_state[k]
            st.experimental_rerun()

with gen_col3:
    if st.button("Clear All"):
        clear_all_state()

# ---------------------------
# Display quiz (interactive)
# ---------------------------
if st.session_state.quiz:
    st.markdown("### 3) Take the quiz")
    quiz = st.session_state.quiz

    # Render each question. We'll include a placeholder as the first option so no real option is pre-selected.
    placeholder = "— Select an answer —"

    for i, q in enumerate(quiz):
        st.write(f"**Q{i+1}: {q['question']}**")

        # Build display options with letter prefixes
        display_options = [placeholder]
        for j, choice in enumerate(q["choices"]):
            label = f"{chr(65 + j)}. {choice['text']}"
            display_options.append(label)

        # If user had previously selected, keep it, otherwise radio will show placeholder
        selected = st.radio(
            f"Answer for Q{i+1}",
            display_options,
            index=0,
            key=f"q{i}",
        )

    # ---------------------------
    # Submit answers
    # ---------------------------
    submit_col1, submit_col2, submit_col3 = st.columns([1, 1, 1])
    with submit_col1:
        if st.button("Submit Answers"):
            total = len(quiz)
            score = 0
            results = {}
            for i, q in enumerate(quiz):
                sel = st.session_state.get(f"q{i}", placeholder)
                if sel == placeholder:
                    # treat as unanswered -> incorrect
                    results[i] = {"correct": False, "selected": None, "correct_text": None}
                    # compute correct option text:
                    for idx, ch in enumerate(q["choices"]):
                        if ch.get("is_correct"):
                            correct_idx = idx
                            break
                    correct_text = q["choices"][correct_idx]["text"]
                    results[i]["correct_text"] = f"{chr(65 + correct_idx)}. {correct_text}"
                else:
                    # selected is like "A. option text"
                    letter = sel.split(".", 1)[0].strip()
                    try:
                        idx = ord(letter.upper()) - 65
                        is_correct = False
                        if 0 <= idx < len(q["choices"]):
                            is_correct = q["choices"][idx].get("is_correct", False)
                        if is_correct:
                            score += 1
                        results[i] = {
                            "correct": is_correct,
                            "selected": sel,
                            "correct_text": None,
                        }
                        # store correct text if needed
                        if not is_correct:
                            for ci, ch in enumerate(q["choices"]):
                                if ch.get("is_correct"):
                                    results[i]["correct_text"] = f"{chr(65 + ci)}. {ch['text']}"
                                    break
                    except Exception:
                        results[i] = {"correct": False, "selected": sel, "correct_text": None}

            st.session_state.submitted = True
            st.session_state.score = score
            st.session_state.results = results
            st.experimental_rerun()

    # ---------------------------
    # Retake: reshape choices & clear answers
    # ---------------------------
    with submit_col2:
        if st.button("Retake Quiz"):
            # Shuffle choices for each question so retake is fresh
            for q in st.session_state.quiz:
                random.shuffle(q["choices"])
            # Remove radio selections so they rebuild with placeholder selected
            for i in range(len(st.session_state.quiz)):
                key = f"q{i}"
                if key in st.session_state:
                    try:
                        del st.session_state[key]
                    except Exception:
                        pass
            # Reset submission metadata
            st.session_state.submitted = False
            st.session_state.score = None
            st.session_state.results = {}
            st.experimental_rerun()

    # ---------------------------
    # Regenerate from same content
    # ---------------------------
    with submit_col3:
        if st.button("Regenerate (Different set)"):
            if not st.session_state.page_text:
                st.warning("No source content saved. Paste or preview URL first.")
            else:
                new_quiz = generate_quiz(st.session_state.page_text)
                if new_quiz:
                    st.session_state.quiz = new_quiz
                    # clear old widget keys
                    for i in range(50):
                        key = f"q{i}"
                        if key in st.session_state:
                            try:
                                del st.session_state[key]
                            except Exception:
                                pass
                    st.session_state.submitted = False
                    st.session_state.results = {}
                    st.session_state.score = None
                    st.experimental_rerun()

# ---------------------------
# Review Mode (after submission)
# ---------------------------
if st.session_state.submitted and st.session_state.quiz:
    st.markdown("### 4) Review Mode")
    st.write(f"**Your score: {st.session_state.score}/{len(st.session_state.quiz)}**")

    for i, q in enumerate(st.session_state.quiz):
        res = st.session_state.results.get(i, {})
        sel = res.get("selected")
        correct_flag = res.get("correct", False)
        correct_text = res.get("correct_text")

        st.write(f"**Q{i+1}: {q['question']}**")
        if sel is None:
            st.warning("You did not select an answer for this question.")
        else:
            if correct_flag:
                st.success(f"Your answer: {sel} — Correct ✅")
            else:
                st.error(f"Your answer: {sel} — Incorrect ❌")
                if correct_text:
                    st.info(f"Correct answer: {correct_text}")
        # show explanation
        expl = q.get("explanation", "No explanation provided.")
        st.info(f"Explanation: {expl}")

# ---------------------------
# Footer / troubleshooting tips
# ---------------------------
st.markdown("---")
st.markdown(
    "If the quiz generator fails or returns no questions, try these:\n"
    "- Paste a shorter portion of the page into Paste Text (some sites are large/complex).\n"
    "- Regenerate a new quiz (Generate New Quiz) to get a slightly different output.\n"
    "- Confirm your `gemini_api_key` is in Streamlit Secrets (Settings → Secrets)."
)
