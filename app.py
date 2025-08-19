# Create a ready-to-run Streamlit app package for the user
import os, textwrap, zipfile, json, pathlib

base_dir = "/mnt/data/trailhead_quiz_app"
os.makedirs(base_dir, exist_ok=True)
os.makedirs(os.path.join(base_dir, ".streamlit"), exist_ok=True)

app_py = textwrap.dedent(r'''
import os
import re
import requests
from bs4 import BeautifulSoup
import streamlit as st
import google.generativeai as genai

# --- API KEY SETUP ---
API_KEY = st.secrets.get("gemini_api_key", os.getenv("GEMINI_API_KEY"))
if not API_KEY:
    st.warning("Add your Gemini API key in Settings → Secrets as 'gemini_api_key' OR set environment variable GEMINI_API_KEY.")
else:
    genai.configure(api_key=API_KEY)

st.title("Trailhead Quiz Generator 📝 (Gemini Edition + Review + Retake + New Quiz)")

# --- HELP SIDEBAR ---
with st.sidebar:
    st.header("How to use")
    st.markdown(
        "- Choose **Paste URL** or **Paste Text**.\n"
        "- Click **Generate Quiz**.\n"
        "- Answer each question and click **Submit Answers**.\n"
        "- Use **Retake Quiz** to try again, or **Generate New Quiz** for a new set."
    )
    st.markdown("---")
    st.markdown("**Tip:** Some pages block scraping. If URL doesn't work, copy & paste the page text.")

# --- INPUT ---
option = st.radio("Choose input method:", ["Paste URL", "Paste Text"], horizontal=True)

def extract_text_from_url(url: str) -> str:
    """Best-effort extract readable text from a webpage."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Grab headings, paragraphs, list items
        chunks = []
        for tag in soup.find_all(["h1", "h2", "h3", "p", "li"]):
            text = tag.get_text(separator=" ", strip=True)
            if text:
                chunks.append(text)
        return "\n".join(chunks)
    except Exception as e:
        st.error(f"Couldn't fetch the page: {e}")
        return ""

if option == "Paste URL":
    url = st.text_input("Enter Trailhead page URL:")
    page_text = ""
    if url:
        if st.button("Preview Page Text"):
            page_text = extract_text_from_url(url)
            if page_text:
                st.success("Page text extracted. Scroll to preview below.")
                st.session_state.page_text_preview = page_text
            else:
                st.session_state.page_text_preview = ""
    page_text = st.session_state.get("page_text_preview", "")
    if page_text:
        with st.expander("Preview extracted text"):
            st.write(page_text)
else:
    page_text = st.text_area("Paste Trailhead page content here:", height=250)

# --- QUIZ GENERATION ---
def generate_quiz(content: str):
    """Ask Gemini to create 5 MCQs (A-D) with correct answer and explanation."""
    prompt = f"""
    You are a strict quiz generator. Based on the learning content below, create **exactly 5** multiple-choice questions.
    Format each question like this:
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

    model = genai.GenerativeModel("gemini-1.5-flash")
    result = model.generate_content(prompt)
    raw_quiz = result.text or ""

    # Parse questions, options, correct answers, explanations
    # Split on numbering at start of line e.g., "1. ", "2. "
    parts = re.split(r"(?m)^\s*\d+\.\s+", raw_quiz)
    parts = [p.strip() for p in parts if p.strip()]
    quiz = []

    for block in parts:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        # First line is the question
        question_text = lines[0]
        options = [ln for ln in lines if re.match(r"^[A-D][\).]\s", ln)]
        # Accept formats like "A. foo" or "A) foo"
        # Normalize options to "A. text"
        norm_opts = []
        for opt in options:
            m = re.match(r"^([A-D])[\).]\s*(.*)$", opt)
            if m:
                norm_opts.append(f"{m.group(1)}. {m.group(2)}")

        correct_match = next((ln for ln in lines if ln.lower().startswith("correct answer")), None)
        correct_letter = None
        if correct_match and ":" in correct_match:
            correct_letter = correct_match.split(":", 1)[1].strip()
            # In case model returns like "Correct Answer: B. Option text", keep only the letter
            m2 = re.match(r"^([A-D])\b", correct_letter, flags=re.IGNORECASE)
            if m2:
                correct_letter = m2.group(1).upper()

        explanation_line = next((ln for ln in lines if ln.lower().startswith("explanation")), None)
        explanation = "No explanation provided."
        if explanation_line and ":" in explanation_line:
            explanation = explanation_line.split(":", 1)[1].strip()

        if question_text and norm_opts and correct_letter in {"A","B","C","D"}:
            quiz.append({
                "question": question_text,
                "options": norm_opts,
                "correct": correct_letter,
                "explanation": explanation
            })

    return quiz

# Generate initial quiz
if st.button("Generate Quiz"):
    if not page_text:
        st.warning("Please provide content (paste text or fetch from URL).")
    elif not API_KEY:
        st.error("No API key detected. Add your Gemini API key first.")
    else:
        st.session_state.quiz = generate_quiz(page_text)
        st.session_state.answers = {}
        st.session_state.submitted = False
        st.session_state.page_text_source = page_text  # Save for "Generate New Quiz"

# --- QUIZ UI ---
if "quiz" in st.session_state and st.session_state.get("quiz"):
    st.write("### Quiz")
    for i, q in enumerate(st.session_state.quiz):
        st.write(f"**Q{i+1}: {q['question']}**")
        st.session_state.answers[i] = st.radio(
            f"Select answer for Q{i+1}",
            q["options"],
            key=f"q{i}",
            index=None
        )

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Submit Answers"):
            st.session_state.submitted = True
            score = 0
            st.write("### Results")
            for i, q in enumerate(st.session_state.quiz):
                selected = st.session_state.answers.get(i)
                # Determine the correct option line from the letter
                correct_option = next((opt for opt in q["options"] if opt.startswith(f"{q['correct']}.")), None)
                if selected == correct_option:
                    st.success(f"✅ Q{i+1}: Correct")
                    score += 1
                else:
                    st.error(f"❌ Q{i+1}: Wrong. Correct answer: {correct_option}")
            st.write(f"## 🎯 Your Score: {score}/{len(st.session_state.quiz)}")

    with col2:
        if st.button("Retake Quiz"):
            # Reset selections but keep same quiz
            for i in range(len(st.session_state.quiz)):
                st.session_state[f"q{i}"] = None
            st.session_state.answers = {}
            st.session_state.submitted = False
            st.experimental_rerun()

    with col3:
        if st.button("Generate New Quiz"):
            if st.session_state.get("page_text_source") and API_KEY:
                st.session_state.quiz = generate_quiz(st.session_state.page_text_source)
                st.session_state.answers = {}
                st.session_state.submitted = False
                st.experimental_rerun()
            else:
                st.warning("No source content available to regenerate a new quiz.")

    if st.session_state.get("submitted"):
        st.write("### 🔍 Review Mode")
        for i, q in enumerate(st.session_state.quiz):
            st.info(f"Q{i+1}: {q['question']}\n\nExplanation: {q['explanation']}")

elif "quiz" in st.session_state and not st.session_state["quiz"]:
    st.error("Quiz generation returned no questions. Try pasting the text instead of URL or click 'Generate New Quiz'.")
''')

requirements_txt = textwrap.dedent('''
streamlit
beautifulsoup4
requests
google-generativeai
''')

secrets_toml = textwrap.dedent('''
# Rename this file to secrets.toml and put it under a local ".streamlit" folder next to app.py
# Or set an environment variable instead of using this file.
gemini_api_key = "PASTE_YOUR_KEY_HERE"
''')

readme_md = textwrap.dedent('''
# Trailhead Quiz Generator (Gemini)

Generate interactive multiple-choice quizzes from Salesforce Trailhead pages (or any learning content).

## What you need
- A Google **Gemini API key** (free tier available).
- Python 3.10+

## Get your Gemini API key
1. Go to Google **AI Studio**.
2. Sign in with your Google account.
3. Create a new API key and copy it.

> You can supply the key in two ways:
> - **Recommended (local secrets file):** Create a folder named `.streamlit` next to `app.py` and put a file `secrets.toml` inside with:  
>   `gemini_api_key = "YOUR_KEY_HERE"`  
> - **Or Environment variable:** set `GEMINI_API_KEY`

---

## Option A — Run on your Windows laptop
1. Install **Python** from python.org. Check "Add Python to PATH" during install.
2. Open **PowerShell** and run:
   ```powershell
   cd PATH\\TO\\FOLDER
   python -m venv .venv
   .\\.venv\\Scripts\\activate
   pip install -r requirements.txt
