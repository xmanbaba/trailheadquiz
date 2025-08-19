import streamlit as st
import requests
import google.generativeai as genai

# ----------------------------
# CONFIGURE GOOGLE GEMINI API
# ----------------------------
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# ----------------------------
# HELPER FUNCTION: CALL GEMINI
# ----------------------------
def generate_quiz(content):
    prompt = f"""
    Based on the following content, generate 5 multiple-choice quiz questions.
    Each question should have 4 options (A, B, C, D) with one correct answer.
    Return the quiz in JSON format with this structure:
    {{
      "questions": [
        {{
          "question": "text",
          "options": ["A", "B", "C", "D"],
          "answer": "A"
        }}
      ]
    }}

    Content:
    {content}
    """
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)

    import json
    try:
        quiz = json.loads(response.text)
        return quiz
    except Exception:
        st.error("Failed to parse quiz from AI response. Please try again.")
        return None

# ----------------------------
# APP TITLE
# ----------------------------
st.set_page_config(page_title="Trailhead Quiz Generator", layout="wide")
st.title("📘 Trailhead Quiz Generator with Gemini AI")

# ----------------------------
# INPUT SECTION
# ----------------------------
st.subheader("Step 1: Provide Trailhead Page or Paste Content")

url = st.text_input("🔗 Enter Trailhead Page URL (optional):", key="url_input")
content_text = st.text_area("📝 Or paste the content directly:", height=200, key="content_input")

# Clear button
if st.button("Clear Input"):
    st.session_state.url_input = ""
    st.session_state.content_input = ""

# Fetch content from URL
page_content = ""
if url:
    try:
        response = requests.get(url)
        if response.status_code == 200:
            page_content = response.text
        else:
            st.warning("Could not fetch content from the URL. Try pasting manually.")
    except Exception as e:
        st.warning(f"Error fetching URL: {e}")

if content_text:
    page_content = content_text

# ----------------------------
# QUIZ GENERATION
# ----------------------------
if st.button("Generate Quiz"):
    if page_content.strip() == "":
        st.warning("Please provide content from URL or paste it.")
    else:
        quiz = generate_quiz(page_content)
        if quiz:
            st.session_state.quiz = quiz
            st.session_state.quiz_submitted = False
            st.session_state.quiz_score = None

if "quiz" in st.session_state:
    quiz = st.session_state.quiz

    st.subheader("Step 2: Take the Quiz")

    answers = []
    for i, q in enumerate(quiz["questions"]):
        st.write(f"**Q{i+1}. {q['question']}**")
        choice = st.radio("Choose an answer:", q["options"], key=f"q{i}")
        answers.append(choice)

    if st.button("Submit Answers"):
        score = 0
        results = []
        for i, q in enumerate(quiz["questions"]):
            correct = q["answer"]
            user_ans = answers[i]
            if user_ans == correct:
                score += 1
                results.append((q["question"], True, correct, user_ans))
            else:
                results.append((q["question"], False, correct, user_ans))

        st.session_state.quiz_submitted = True
        st.session_state.quiz_score = score
        st.session_state.results = results

    # ----------------------------
    # REVIEW MODE
    # ----------------------------
    if st.session_state.get("quiz_submitted", False):
        st.subheader("Review Your Results")
        st.write(f"✅ Your Score: {st.session_state.quiz_score}/{len(quiz['questions'])}")

        for q, correct, ans, user in st.session_state.results:
            if correct:
                st.success(f"✔️ {q} - Correct! ({ans})")
            else:
                st.error(f"❌ {q} - Your answer: {user}, Correct answer: {ans}")

        # Retake Quiz
        if st.button("Retake Quiz"):
            for i in range(len(st.session_state.quiz["questions"])):
                key = f"q{i}"
                if key in st.session_state:
                    del st.session_state[key]

            st.session_state.quiz_submitted = False
            st.session_state.quiz_score = None
            st.session_state.results = []
            st.rerun()

        # Regenerate Quiz
        if st.button("Regenerate Quiz"):
            quiz = generate_quiz(page_content)
            if quiz:
                st.session_state.quiz = quiz
                for i in range(len(quiz["questions"])):
                    key = f"q{i}"
                    if key in st.session_state:
                        del st.session_state[key]
                st.session_state.quiz_submitted = False
                st.session_state.quiz_score = None
                st.session_state.results = []
                st.rerun()
