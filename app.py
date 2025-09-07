import os
import re
import random
import requests
from bs4 import BeautifulSoup
import streamlit as st
import google.generativeai as genai
import time

# ---------------------------
# Page config
# ---------------------------
st.set_page_config(
    page_title="Trailhead Quiz Generator", 
    layout="centered",
    initial_sidebar_state="expanded"
)

# ---------------------------
# API key with better error handling
# ---------------------------
API_KEY = st.secrets.get("gemini_api_key", os.getenv("GEMINI_API_KEY"))
if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
    except Exception as e:
        st.error(f"Failed to configure Gemini API: {e}")
        API_KEY = None

# ---------------------------
# Header + short description
# ---------------------------
st.title("Trailhead Quiz Generator 📝")
st.write(
    "Paste a **Trailhead URL** or **content text**, then generate a quick quiz to check your understanding.\n\n"
    "**How it works:**\n"
    "Provide content → Generate Quiz → Answer → Submit → Review → Retake or Generate New Quiz."
)

# Sidebar help (numbered steps) ---------------------------
with st.sidebar:
    st.header("How to use")
    st.markdown(
        "1. Choose **Paste URL** or **Paste Text**.\n"
        "2. If using URL, click **Preview Page Text** to confirm extraction.\n"
        "3. Click **Generate Quiz**.\n"
        "4. Answer each question.\n"
        "5. Click **Submit Answers** to see your score.\n"
        "6. Use **Retake Quiz** to try again (questions + options reshuffled).\n"
        "7. Use **Generate New Quiz** for a different set."
    )
    st.markdown("---")
    st.markdown("**Tip:** Some pages block scraping. If URL fails, copy & paste the content instead.")
    
    # API status indicator
    if API_KEY:
        st.success("✅ Gemini API configured")
    else:
        st.error("❌ Gemini API key missing")
        st.info("Add `gemini_api_key` in Streamlit Settings → Secrets")

# ---------------------------
# Utilities with better error handling
# ---------------------------
def extract_text_from_url(url: str) -> tuple[str, str]:
    """
    Extract readable text from a webpage.
    Returns: (text_content, error_message)
    """
    try:
        # Validate URL format
        if not url.startswith(('http://', 'https://')):
            return "", "Please enter a valid URL starting with http:// or https://"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        
        resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        
        if resp.status_code == 403:
            return "", "Access forbidden (403). The website may be blocking automated requests. Try copying the content manually."
        elif resp.status_code == 404:
            return "", "Page not found (404). Please check the URL."
        elif resp.status_code != 200:
            return "", f"HTTP {resp.status_code} error. The website may be temporarily unavailable."
            
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        chunks = []
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "div"], recursive=True):
            text = tag.get_text(separator=" ", strip=True)
            if text and len(text) > 10:  # Filter out very short text
                chunks.append(text)
        
        text = "\n".join(chunks).strip()
        
        if not text:
            return "", "No readable content found on this page. Try copying the content manually."
            
        return text[:15000], ""  # limit length, no error
        
    except requests.exceptions.Timeout:
        return "", "Request timed out. The website may be slow or unresponsive."
    except requests.exceptions.ConnectionError:
        return "", "Connection error. Please check your internet connection and the URL."
    except requests.exceptions.RequestException as e:
        return "", f"Network error: {str(e)}"
    except Exception as e:
        return "", f"Unexpected error: {str(e)}"

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

        question_text = lines[0]
        options = []
        for ln in lines:
            m = re.match(r"^([A-D])[\).]\s*(.*)$", ln)
            if m:
                options.append(f"{m.group(1)}. {m.group(2)}")

        correct_match = next((ln for ln in lines if ln.lower().startswith("correct answer")), None)
        correct_letter = None
        if correct_match and ":" in correct_match:
            candidate = correct_match.split(":", 1)[1].strip()
            m2 = re.match(r"^([A-D])\b", candidate, flags=re.IGNORECASE)
            if m2:
                correct_letter = m2.group(1).upper()

        explanation_line = next((ln for ln in lines if ln.lower().startswith("explanation")), None)
        explanation = "No explanation provided."
        if explanation_line and ":" in explanation_line:
            explanation = explanation_line.split(":", 1)[1].strip()

        if question_text and len(options) >= 3 and correct_letter in {"A", "B", "C", "D"}:
            quiz.append(
                {
                    "question": question_text,
                    "options": options,
                    "correct": correct_letter,
                    "explanation": explanation,
                }
            )

    return quiz

def _build_shuffled_quiz(original_quiz):
    """Shuffle both questions and options but keep labels A–D consistent."""
    if not original_quiz:
        return []
        
    # Shuffle question order
    shuffled_questions = original_quiz[:]
    random.shuffle(shuffled_questions)

    shuffled = []
    for q in shuffled_questions:
        opt_texts = []
        for opt in q["options"]:
            m = re.match(r"^[A-D][\).]\s*(.*)$", opt)
            if m:
                opt_texts.append(m.group(1).strip())
            else:
                opt_texts.append(opt.strip())

        orig_correct_text = None
        if q.get("correct"):
            letter = q["correct"]
            for opt in q["options"]:
                if opt.startswith(f"{letter}.") or opt.startswith(f"{letter})"):
                    m2 = re.match(r"^[A-D][\).]\s*(.*)$", opt)
                    orig_correct_text = m2.group(1).strip() if m2 else opt[2:].strip()
                    break

        random.shuffle(opt_texts)

        new_options = []
        new_correct_letter = None
        for idx, txt in enumerate(opt_texts):
            letter = chr(65 + idx)
            labeled = f"{letter}. {txt}"
            new_options.append(labeled)
            if orig_correct_text is not None and txt == orig_correct_text:
                new_correct_letter = letter

        shuffled.append({
            "question": q["question"],
            "options": new_options,
            "correct": new_correct_letter,
            "explanation": q.get("explanation", "No explanation provided.")
        })
    return shuffled

def generate_quiz(content: str):
    """Ask Gemini to produce 5 MCQs in strict format with retry logic."""
    if not API_KEY:
        st.error("No Gemini API key found. Add it in Streamlit **Settings → Secrets** as `gemini_api_key`.")
        return []

    if not content or len(content.strip()) < 50:
        st.error("Content is too short to generate a meaningful quiz. Please provide more content.")
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

Make sure questions test understanding of key concepts. Only produce the quiz in the format above. No extra commentary.

Content:
{content[:10000]}
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            with st.spinner(f"Generating quiz... (attempt {attempt + 1}/{max_retries})"):
                result = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.7,
                        top_p=0.8,
                        top_k=40,
                        max_output_tokens=2048,
                    )
                )

            raw = (result.text or "").strip()
            if not raw:
                if attempt < max_retries - 1:
                    st.warning(f"Empty response on attempt {attempt + 1}. Retrying...")
                    time.sleep(1)
                    continue
                else:
                    st.error("Gemini returned empty responses. Please try again later.")
                    return []

            quiz = parse_quiz_from_text(raw)
            if not quiz:
                if attempt < max_retries - 1:
                    st.warning(f"Could not parse quiz on attempt {attempt + 1}. Retrying...")
                    time.sleep(1)
                    continue
                else:
                    st.error("Could not parse quiz output after multiple attempts. Please try again.")
                    return []

            if len(quiz) < 3:
                if attempt < max_retries - 1:
                    st.warning(f"Only {len(quiz)} questions generated on attempt {attempt + 1}. Retrying...")
                    time.sleep(1)
                    continue
                else:
                    st.warning(f"Only generated {len(quiz)} questions. Proceeding anyway.")

            return {"original": quiz, "shuffled": _build_shuffled_quiz(quiz)}
            
        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg or "forbidden" in error_msg.lower():
                st.error("API access forbidden. Please check your API key and quota.")
                return []
            elif "quota" in error_msg.lower() or "limit" in error_msg.lower():
                st.error("API quota exceeded. Please try again later.")
                return []
            elif attempt < max_retries - 1:
                st.warning(f"Error on attempt {attempt + 1}: {error_msg}. Retrying...")
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            else:
                st.error(f"Quiz generation failed after {max_retries} attempts: {error_msg}")
                return []

    return []

def clear_all_state():
    """Reset session state fully."""
    keys_to_keep = {'input_mode'}  # Keep input mode selection
    for k in list(st.session_state.keys()):
        if k not in keys_to_keep:
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
    url_col, info_col = st.columns([15, 1])
    with url_col:
        url = st.text_input("Enter Trailhead page URL:", value=st.session_state.get("url", ""))
    with info_col:
        # Simplified info icon without complex JavaScript
        st.markdown("ℹ️", help="Paste URL → press Preview Page Text\n(See sidebar for details)")

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Preview Page Text", type="primary"):
            if not url:
                st.warning("Please enter a URL.")
            else:
                st.session_state.url = url
                with st.spinner("Extracting text from webpage..."):
                    text, error = extract_text_from_url(url)
                
                if error:
                    st.error(error)
                    st.session_state.page_text = ""
                else:
                    st.session_state.page_text = text
                    st.success("Page text extracted successfully!")
                    
    with c2:
        if st.button("Clear Inputs"):
            clear_all_state()

    if st.session_state.page_text:
        with st.expander("Preview extracted text", expanded=False):
            st.text_area("Extracted content:", st.session_state.page_text, height=200, disabled=True)

else:
    st.session_state.page_text = st.text_area(
        "Paste Trailhead page content here:",
        value=st.session_state.get("page_text", ""),
        height=240,
        help="Copy and paste the content from the Trailhead page here"
    )
    if st.button("Clear Inputs"):
        clear_all_state()

# ---------------------------
# Generate quiz
# ---------------------------
if st.button("Generate Quiz", type="primary", disabled=not API_KEY):
    if not API_KEY:
        st.error("Gemini API key is required to generate quizzes.")
    elif not st.session_state.page_text:
        st.warning("Please provide content first.")
    else:
        result = generate_quiz(st.session_state.page_text)
        if result:
            st.session_state.quiz = result
            st.session_state.answers = {}
            st.session_state.submitted = False
            st.success(f"Generated {len(result.get('original', []))} questions!")
            st.rerun()

# ---------------------------
# Quiz UI
# ---------------------------
if st.session_state.quiz and "shuffled" in st.session_state.quiz:
    st.write("### 📝 Quiz")
    shuffled = st.session_state.quiz["shuffled"]

    if not shuffled:
        st.error("No valid questions in the quiz. Please try generating again.")
    else:
        for i, q in enumerate(shuffled):
            st.write(f"**Q{i+1}: {q['question']}**")
            
            # Check if question has enough options
            if len(q.get('options', [])) < 2:
                st.error(f"Question {i+1} has insufficient options. Skipping...")
                continue
                
            selected_option = st.radio(
                f"Select answer for Q{i+1}",
                q["options"],
                key=f"q{i}",
                index=None,
            )
            st.session_state.answers[i] = selected_option

        st.write("---")
        c1, c2, c3 = st.columns(3)
        
        with c1:
            if st.button("Submit Answers", type="primary"):
                # Check if all questions are answered
                unanswered = [i+1 for i in range(len(shuffled)) if st.session_state.answers.get(i) is None]
                if unanswered:
                    st.warning(f"Please answer all questions. Missing: Q{', Q'.join(map(str, unanswered))}")
                else:
                    st.session_state.submitted = True
                    st.rerun()

        with c2:
            if st.button("Retake Quiz"):
                if st.session_state.quiz and "original" in st.session_state.quiz:
                    st.session_state.quiz["shuffled"] = _build_shuffled_quiz(st.session_state.quiz["original"])
                # Clear radio widget keys
                for i in range(len(st.session_state.quiz.get("shuffled", []))):
                    key = f"q{i}"
                    if key in st.session_state:
                        try:
                            del st.session_state[key]
                        except Exception:
                            pass
                st.session_state.answers = {}
                st.session_state.submitted = False
                st.rerun()

        with c3:
            if st.button("Generate New Quiz"):
                if st.session_state.page_text:
                    # Clear old radio keys
                    for i in range(50):
                        key = f"q{i}"
                        if key in st.session_state:
                            try:
                                del st.session_state[key]
                            except Exception:
                                pass
                    
                    result = generate_quiz(st.session_state.page_text)
                    if result:
                        st.session_state.quiz = result
                        st.session_state.answers = {}
                        st.session_state.submitted = False
                        st.rerun()
                else:
                    st.warning("No source content to regenerate from.")

# ---------------------------
# Review mode
# ---------------------------
if st.session_state.submitted and st.session_state.quiz and "shuffled" in st.session_state.quiz:
    st.write("### 🔍 Review Mode")
    score = 0
    shuffled = st.session_state.quiz["shuffled"]
    
    for i, q in enumerate(shuffled):
        selected = st.session_state.answers.get(i)
        correct_letter = q.get("correct")
        correct_option = next((opt for opt in q["options"] if opt.startswith(f"{correct_letter}.")), None) if correct_letter else None
        
        st.write(f"**Q{i+1}: {q['question']}**")
        
        if selected == correct_option:
            st.success(f"✅ **Correct!** Your answer: {selected}")
            score += 1
        else:
            st.error(f"❌ **Incorrect.** Your answer: {selected or 'No answer'}")
            if correct_option:
                st.info(f"✔️ **Correct answer:** {correct_option}")
        
        if q.get('explanation'):
            st.info(f"💡 **Explanation:** {q['explanation']}")
        
        st.write("---")
    
    # Final score with better formatting
    percentage = (score / len(shuffled)) * 100 if shuffled else 0
    st.write(f"## 🎯 Final Score: {score}/{len(shuffled)} ({percentage:.1f}%)")
    
    if percentage >= 80:
        st.balloons()
        st.success("🎉 Excellent work!")
    elif percentage >= 60:
        st.success("👍 Good job!")
    else:
        st.info("📚 Keep studying and try again!")
