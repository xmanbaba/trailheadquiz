import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import random

# --------------------
# Gemini Setup
# --------------------
GEMINI_API_KEY = st.secrets.get("gemini_api_key", None)

if not GEMINI_API_KEY:
    st.error("⚠️ No Gemini API key found. Please add it to `.streamlit/secrets.toml`.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

# --------------------
# Helper: Extract text from URL
# --------------------
def extract_text_from_url(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = [p.get_text() for p in soup.find_all("p")]
        return "\n".join(paragraphs)
    except Exception as e:
        return f"Error extracting content: {e}"

# --------------------
# Helper: Generate quiz with Gemini
# --------------------
def generate_quiz(text, num_questions=5):
    prompt = f"""
    You are a quiz generator. Based on the content below, create {num_questions} multiple-choice questions.
    Each question should have 1 correct answer and 3 incorrect options. Format strictly as JSON:

    [
      {{
        "question": "Sample question?",
        "options": ["A", "B", "C", "D"],
        "answer": "B"
      }},
      ...
    ]

    Content:
    {text}
    """

    try:
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)

        import json
        quiz_data = json.loads(response.text)

        # Shuffle options for each question
        for q in quiz_data:
            random.shuffle(q["options"])

        return quiz_data
    except Exception as e:
        st.error(f"Error generating quiz: {e}")
        return []

# --------------------
# Streamlit UI
# --------------------
st.set_page_config(page_title="Trailhead Quiz Generator", layout="centered")
st.title("📘 Trailhead Quiz Generator")
st.write("Paste a Trailhead URL or text, and test your understanding with a quiz!")

# Input method selection
mode = st.radio("Choose input method:", ["Paste URL", "Paste Text"])

if "user_input" not in st.session_state:
    st.session_state.user_input = ""

# Input fields
if mode == "Paste URL":
    url = st.text_input("Enter Trailhead URL:", value=st.session_state.user_input)
    if st.button("Clear"):
        st.session_state.user_input = ""
        st.rerun()
else:
    text_input = st.text_area("Paste content here:", value=st.session_state.user_input, height=200)
    if st.button("Clear"):
        st.session_state.user_input = ""
        st.rerun()

# Initialize session state
if "quiz" not in st.session_state:
    st.session_state.quiz = []
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}
if "submitted" not in st.session_state:
    st.session_state.submitted = False

# Generate quiz
if st.button("Generate Quiz"):
    if mode == "Paste URL" and url:
        content = extract_text_from_url(url)
        st.session_state.user_input = url
    elif mode == "Paste Text" and text_input:
        content = text_input
        st.session_state.user_input = text_input
    else:
        st.warning("Please provide input.")
        st.stop()

    st.session_state.quiz = generate_quiz(content)
    st.session_state.user_answers = {}
    st.session_state.submitted = False
    st.rerun()

# Show quiz
if st.session_state.quiz:
    st.header("📝 Quiz")
    for i, q in enumerate(st.session_state.quiz):
        st.write(f"**Q{i+1}: {q['question']}**")
        st.session_state.user_answers[i] = st.radio(
            f"Answer Q{i+1}", 
            q["options"], 
            key=f"q{i}"
        )

    # Submit button
    if st.button("Submit Answers"):
        st.session_state.submitted = True
        st.rerun()

# Review mode
if st.session_state.submitted:
    st.header("✅ Review")
    score = 0
    for i, q in enumerate(st.session_state.quiz):
        user_answer = st.session_state.user_answers.get(i, "")
        correct_answer = q["answer"]
        if user_answer == correct_answer:
            st.success(f"Q{i+1}: Correct ✅ ({user_answer})")
            score += 1
        else:
            st.error(f"Q{i+1}: Incorrect ❌ (Your answer: {user_answer}, Correct: {correct_answer})")
    st.info(f"Final Score: {score}/{len(st.session_state.quiz)}")

    # Retake quiz (reset answers only)
    if st.button("Retake Quiz"):
        st.session_state.user_answers = {}
        st.session_state.submitted = False
        st.rerun()

    # Generate new quiz (reset everything but keep input)
    if st.button("Generate New Quiz"):
        content = (
            extract_text_from_url(st.session_state.user_input)
            if mode == "Paste URL"
            else st.session_state.user_input
        )
        st.session_state.quiz = generate_quiz(content)
        st.session_state.user_answers = {}
        st.session_state.submitted = False
        st.rerun()
