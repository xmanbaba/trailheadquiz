import os
import re
import random
import requests
from bs4 import BeautifulSoup
import streamlit as st
import time

# Multiple AI providers support
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# ---------------------------
# Page config
# ---------------------------
st.set_page_config(
    page_title="Multi-AI Quiz Generator", 
    layout="centered",
    initial_sidebar_state="expanded"
)

# ---------------------------
# API Configuration
# ---------------------------
def configure_ai_providers():
    """Configure available AI providers"""
    providers = {}
    
    # Gemini API
    if GEMINI_AVAILABLE:
        gemini_key = st.secrets.get("gemini_api_key", os.getenv("GEMINI_API_KEY"))
        if gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                providers["Gemini"] = {"key": gemini_key, "status": "✅ Active"}
            except Exception as e:
                providers["Gemini"] = {"key": None, "status": f"❌ Error: {e}"}
        else:
            providers["Gemini"] = {"key": None, "status": "❌ No API key"}
    
    # OpenAI API (for comparison)
    if OPENAI_AVAILABLE:
        openai_key = st.secrets.get("openai_api_key", os.getenv("OPENAI_API_KEY"))
        if openai_key:
            try:
                openai.api_key = openai_key
                providers["OpenAI"] = {"key": openai_key, "status": "✅ Active"}
            except Exception as e:
                providers["OpenAI"] = {"key": None, "status": f"❌ Error: {e}"}
        else:
            providers["OpenAI"] = {"key": None, "status": "❌ No API key"}
    
    # Moonshot (Kimi) API - Free tier with high limits
    kimi_key = st.secrets.get("kimi_api_key", os.getenv("KIMI_API_KEY"))
    if kimi_key:
        providers["Kimi (Moonshot)"] = {"key": kimi_key, "status": "✅ Active"}
    else:
        providers["Kimi (Moonshot)"] = {"key": None, "status": "❌ No API key"}
    
    return providers

# ---------------------------
# Header
# ---------------------------
st.title("Multi-AI Quiz Generator 🤖")
st.write(
    "Generate quizzes using multiple AI providers. Automatically switches to available providers when quota limits are reached.\n\n"
    "**Supported AI Providers:**\n"
    "- 🔥 **Gemini**: 50-100 requests/day (free)\n"
    "- 🌙 **Kimi (Moonshot)**: Higher free limits\n"
    "- 🤖 **OpenAI**: Paid (more reliable)\n\n"
    "⚠️ **Note**: Each quiz generates **5 questions**. Free tier users should monitor usage to avoid quota limits."
)

# ---------------------------
# Sidebar - AI Provider Status
# ---------------------------
providers = configure_ai_providers()

with st.sidebar:
    st.header("🤖 AI Provider Status")
    
    available_providers = []
    for provider, config in providers.items():
        if provider == "Gemini":
            # Enhanced Gemini status with quota info
            if config['key']:
                st.write(f"**{provider}**: {config['status']}")
                st.caption("📊 Free Tier: 50-100 requests/day | 5-15 requests/minute")
                st.caption("⏰ Quota resets at midnight Pacific time")
                available_providers.append(provider)
            else:
                st.write(f"**{provider}**: {config['status']}")
                st.caption("❌ Add gemini_api_key in Streamlit Secrets")
        else:
            st.write(f"**{provider}**: {config['status']}")
            if config['key']:
                available_providers.append(provider)
    
    if not available_providers:
        st.error("❌ No AI providers configured!")
        st.info("""
        **Setup Instructions:**
        
        Add API keys in Streamlit Settings → Secrets:
        
        ```toml
        gemini_api_key = "your-gemini-key"
        kimi_api_key = "your-kimi-key" 
        openai_api_key = "your-openai-key"
        ```
        """)
    else:
        st.success(f"✅ {len(available_providers)} provider(s) ready")
        
        # Provider selection with Gemini preference and warning
        selected_provider = st.selectbox(
            "Choose AI Provider:",
            available_providers,
            help="Gemini: Limited free tier but reliable. Alternatives: Higher free limits."
        )
        
        # Special guidance for Gemini users
        if selected_provider == "Gemini":
            st.info("""
            🔥 **Gemini Tips:**
            - 50-100 requests/day (free tier)
            - Resets at midnight PT
            - For more usage: Enable billing for 1000+ requests/day
            """)
            
            # Show upgrade path
            st.markdown("""
            💡 **Need more requests?** 
            
            [📈 Upgrade to Paid Tier](https://aistudio.google.com/apikey) for:
            - 1,000+ requests/day
            - Higher rate limits
            - Priority access
            """)
        else:
            st.success(f"✅ Using {selected_provider} - Better free tier limits!")
    
    st.markdown("---")
    
    # Instructions with Gemini education
    st.header("📋 How to use")
    st.markdown(
        "1. Choose your AI provider above\n"
        "2. Paste URL or text content\n"
        "3. Generate quiz (5 questions)\n"
        "4. Answer questions\n"
        "5. Get your score!\n\n"
        "💡 **Multiple providers** = More daily usage!"
    )
    
    # Gemini-specific education
    with st.expander("🔥 Gemini Free Tier Guide"):
        st.markdown("""
        **Current Limits (2025):**
        - Gemini 1.5 Flash: 15 RPM, 50 RPD
        - Gemini 2.5 Pro: 5 RPM, 100 RPD
        - Resets: Midnight Pacific Time
        
        **If Quota Exceeded:**
        1. ⏰ Wait for reset (midnight PT)
        2. 🔑 Create new API key in new project
        3. 💳 Enable billing ($1+ = Tier 1)
        4. 🌙 Try Kimi provider
        
        **Tier 1 Benefits:**
        - 1,000+ requests/day
        - 150+ requests/minute
        - Better reliability
        """)
    
    # API Key Setup Guide
    with st.expander("🔑 Free API Keys Setup"):
        st.markdown("""
        **Fresh Gemini Key:**
        1. Visit: https://aistudio.google.com/apikey
        2. "Create API key in NEW project"
        3. Fresh quota: 50-100 requests/day
        
        **Kimi (Moonshot)** - High free limits:
        1. Visit: https://platform.moonshot.cn/
        2. Sign up & get free tokens
        3. Higher daily limits than Gemini
        """)
    
    # Quota management tips
    with st.expander("📊 Managing Quotas"):
        st.markdown("""
        **Best Practices:**
        - Use shorter content (under 5000 chars)
        - Space out quiz generations
        - Set up multiple providers
        - Monitor usage in Google Cloud Console
        
        **When to Upgrade:**
        - Regular daily usage
        - Multiple users
        - Production applications
        - Need reliability
        """)

# ---------------------------
# Utility Functions
# ---------------------------
def extract_text_from_url(url: str) -> tuple[str, str]:
    """Extract text from URL"""
    try:
        if not url.startswith(('http://', 'https://')):
            return "", "Please enter a valid URL starting with http:// or https://"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
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
            
        return text[:8000], ""  # limit length, no error
        
    except requests.exceptions.Timeout:
        return "", "Request timed out. The website may be slow or unresponsive."
    except requests.exceptions.ConnectionError:
        return "", "Connection error. Please check your internet connection and the URL."
    except requests.exceptions.RequestException as e:
        return "", f"Network error: {str(e)}"
    except Exception as e:
        return "", f"Unexpected error: {str(e)}"

def parse_quiz_from_text(raw_quiz: str):
    """Parse quiz from AI response"""
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

        correct_match = next((ln for ln in lines if "correct" in ln.lower()), None)
        correct_letter = None
        if correct_match and ":" in correct_match:
            candidate = correct_match.split(":", 1)[1].strip()
            m2 = re.match(r"^([A-D])\b", candidate, flags=re.IGNORECASE)
            if m2:
                correct_letter = m2.group(1).upper()

        explanation_line = next((ln for ln in lines if "explanation" in ln.lower()), None)
        explanation = "No explanation provided."
        if explanation_line and ":" in explanation_line:
            explanation = explanation_line.split(":", 1)[1].strip()

        if question_text and len(options) >= 3 and correct_letter:
            quiz.append({
                "question": question_text,
                "options": options,
                "correct": correct_letter,
                "explanation": explanation,
            })

    return quiz

def shuffle_quiz(original_quiz):
    """Shuffle questions and options"""
    if not original_quiz:
        return []
        
    shuffled_questions = original_quiz[:]
    random.shuffle(shuffled_questions)

    shuffled = []
    for q in shuffled_questions:
        opt_texts = []
        for opt in q["options"]:
            m = re.match(r"^[A-D][\).]\s*(.*)$", opt)
            if m:
                opt_texts.append(m.group(1).strip())

        orig_correct_text = None
        if q.get("correct"):
            letter = q["correct"]
            for opt in q["options"]:
                if opt.startswith(f"{letter}."):
                    m2 = re.match(r"^[A-D][\).]\s*(.*)$", opt)
                    orig_correct_text = m2.group(1).strip() if m2 else opt[2:].strip()
                    break

        random.shuffle(opt_texts)

        new_options = []
        new_correct_letter = None
        for idx, txt in enumerate(opt_texts):
            letter = chr(65 + idx)
            new_options.append(f"{letter}. {txt}")
            if orig_correct_text and txt == orig_correct_text:
                new_correct_letter = letter

        shuffled.append({
            "question": q["question"],
            "options": new_options,
            "correct": new_correct_letter,
            "explanation": q["explanation"]
        })
    return shuffled

# ---------------------------
# AI Provider Functions
# ---------------------------
def generate_with_gemini(content: str):
    """Generate quiz using Gemini with enhanced error handling"""
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"""Create exactly 5 multiple-choice questions from this content:

{content[:4000]}

Format:
1. Question
   A. option
   B. option  
   C. option
   D. option
   Correct Answer: X
   Explanation: brief explanation

Only return the quiz, no extra text."""

        result = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                top_p=0.8,
                top_k=40,
                max_output_tokens=2048,
            )
        )
        return result.text, None
    except Exception as e:
        error_msg = str(e).lower()
        if "quota" in error_msg or "limit" in error_msg or "exceeded" in error_msg:
            return None, """🚫 **Gemini Quota Exceeded!**
            
**Free Tier Limits Reached:**
- Daily: 50-100 requests per day
- Per minute: 5-15 requests per minute

**Solutions:**
1. ⏰ **Wait**: Quotas reset at midnight Pacific time
2. 🔑 **New API Key**: Create in new Google Cloud project
3. 💳 **Upgrade**: Enable billing for 1000+ daily requests
4. 🌙 **Switch**: Try Kimi provider

**Upgrade Link**: https://aistudio.google.com/apikey"""
        elif "403" in error_msg or "forbidden" in error_msg:
            return None, "🔑 API key invalid or lacks permissions. Check your Gemini API key."
        else:
            return None, f"Gemini error: {str(e)}"

def generate_with_kimi(content: str, api_key: str):
    """Generate quiz using Kimi (Moonshot) API"""
    try:
        url = "https://api.moonshot.cn/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""Create exactly 5 multiple-choice questions from this content:

{content[:4000]}

Format each question exactly like this:
1. Question text
   A. option
   B. option
   C. option
   D. option
   Correct Answer: X
   Explanation: brief explanation

Only return the quiz, no extra text."""

        data = {
            "model": "moonshot-v1-8k",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 1500
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"], None
        else:
            return None, f"Kimi API error: {response.status_code}"
            
    except Exception as e:
        return None, f"Kimi error: {str(e)}"

def generate_with_openai(content: str, api_key: str):
    """Generate quiz using OpenAI"""
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""Create exactly 5 multiple-choice questions from this content:

{content[:4000]}

Format each question exactly like this:
1. Question text
   A. option
   B. option
   C. option
   D. option
   Correct Answer: X
   Explanation: brief explanation

Only return the quiz, no extra text."""

        data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 1500
        }
        
        response = requests.post("https://api.openai.com/v1/chat/completions", 
                               headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"], None
        else:
            return None, f"OpenAI error: {response.status_code}"
            
    except Exception as e:
        return None, f"OpenAI error: {str(e)}"

def generate_quiz(content: str, provider: str, providers: dict):
    """Generate quiz using selected provider"""
    if not content or len(content.strip()) < 50:
        st.error("Content too short. Please provide more content.")
        return []
    
    with st.spinner(f"Generating quiz using {provider}..."):
        if provider == "Gemini" and GEMINI_AVAILABLE:
            raw_quiz, error = generate_with_gemini(content)
        elif provider == "Kimi (Moonshot)":
            raw_quiz, error = generate_with_kimi(content, providers[provider]["key"])
        elif provider == "OpenAI":
            raw_quiz, error = generate_with_openai(content, providers[provider]["key"])
        else:
            return []
    
    if error:
        # Enhanced error display for Gemini
        if provider == "Gemini" and ("quota" in error.lower() or "exceeded" in error.lower()):
            st.error("❌ **Gemini Quota Exceeded**")
            st.info("""
            **Free Tier Limits Reached:**
            - **Daily limit**: 50-100 requests per day
            - **Per minute**: 5-15 requests per minute
            
            **Immediate Solutions:**
            1. ⏰ **Wait**: Quotas reset at midnight Pacific time
            2. 🔑 **New Key**: Create API key in new Google Cloud project
            3. 🌙 **Switch Provider**: Try Kimi (select above)
            
            **Long-term Solution:**
            💳 **Enable Billing**: $1+ spending = 1000+ requests/day
            
            [🚀 Upgrade Here](https://aistudio.google.com/apikey)
            """)
        else:
            st.error(f"❌ {error}")
        
        # Suggest alternatives for any quota error
        if "quota" in error.lower() or "exceeded" in error.lower() or "limit" in error.lower():
            other_providers = [p for p in providers.keys() if p != provider and providers[p]["key"]]
            if other_providers:
                st.success(f"💡 **Try switching to**: {', '.join(other_providers)}")
                st.info("These providers have higher free tier limits!")
        return []
    
    if not raw_quiz:
        st.error("Empty response from AI provider.")
        return []
    
    quiz = parse_quiz_from_text(raw_quiz)
    if not quiz:
        st.error("Could not parse quiz. Please try again.")
        return []
    
    st.success(f"✅ Generated {len(quiz)} questions using {provider}!")
    return {"original": quiz, "shuffled": shuffle_quiz(quiz)}

# ---------------------------
# Session State
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
# Main Interface
# ---------------------------
if not available_providers:
    st.error("❌ **No AI providers configured**")
    st.info("Please add at least one API key in Streamlit Settings → Secrets")
    st.stop()

# Input method selection
st.session_state.input_mode = st.radio(
    "Choose input method:", 
    ["Paste URL", "Paste Text"], 
    horizontal=True
)

# URL input
if st.session_state.input_mode == "Paste URL":
    url = st.text_input("Enter webpage URL:", value=st.session_state.get("url", ""))
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("📄 Extract Text", type="primary"):
            if not url:
                st.warning("Please enter a URL.")
            else:
                with st.spinner("Extracting text from webpage..."):
                    text, error = extract_text_from_url(url)
                
                if error:
                    st.error(error)
                else:
                    st.session_state.page_text = text
                    st.session_state.url = url
                    st.success("✅ Text extracted successfully!")
    
    with col2:
        if st.button("🗑️ Clear"):
            for key in ["page_text", "url", "quiz", "answers", "submitted"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    if st.session_state.page_text:
        with st.expander("📖 Preview extracted text"):
            st.text_area("Content:", st.session_state.page_text, height=200, disabled=True)

# Text input
else:
    st.session_state.page_text = st.text_area(
        "Paste content here:",
        value=st.session_state.get("page_text", ""),
        height=240,
        help="Copy and paste content from any source"
    )
    
    if st.button("🗑️ Clear"):
        for key in ["page_text", "quiz", "answers", "submitted"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

# Generate quiz
st.markdown("---")
if st.button("🎯 Generate Quiz", type="primary", disabled=not st.session_state.page_text):
    if not st.session_state.page_text:
        st.warning("Please provide content first.")
    else:
        result = generate_quiz(st.session_state.page_text, selected_provider, providers)
        if result:
            st.session_state.quiz = result
            st.session_state.answers = {}
            st.session_state.submitted = False
            st.rerun()

# Quiz display
if st.session_state.quiz and "shuffled" in st.session_state.quiz:
    st.markdown("---")
    st.write("### 📝 Quiz Time!")
    
    shuffled = st.session_state.quiz["shuffled"]
    
    for i, q in enumerate(shuffled):
        st.write(f"**Q{i+1}: {q['question']}**")
        selected = st.radio(
            f"Select answer for Q{i+1}:",
            q["options"],
            key=f"q{i}",
            index=None
        )
        st.session_state.answers[i] = selected
    
    # Control buttons
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("✅ Submit Answers", type="primary"):
            unanswered = [i+1 for i in range(len(shuffled)) if not st.session_state.answers.get(i)]
            if unanswered:
                st.warning(f"Please answer: Q{', Q'.join(map(str, unanswered))}")
            else:
                st.session_state.submitted = True
                st.rerun()
    
    with col2:
        if st.button("🔄 Retake Quiz"):
            # Reshuffle and clear answers
            st.session_state.quiz["shuffled"] = shuffle_quiz(st.session_state.quiz["original"])
            for i in range(20):
                if f"q{i}" in st.session_state:
                    del st.session_state[f"q{i}"]
            st.session_state.answers = {}
            st.session_state.submitted = False
            st.rerun()
    
    with col3:
        if st.button("🎲 New Quiz"):
            if st.session_state.page_text:
                # Clear old data
                for i in range(20):
                    if f"q{i}" in st.session_state:
                        del st.session_state[f"q{i}"]
                
                result = generate_quiz(st.session_state.page_text, selected_provider, providers)
                if result:
                    st.session_state.quiz = result
                    st.session_state.answers = {}
                    st.session_state.submitted = False
                    st.rerun()

# Results display
if st.session_state.submitted and st.session_state.quiz:
    st.markdown("---")
    st.write("### 🎯 Quiz Results")
    
    score = 0
    shuffled = st.session_state.quiz["shuffled"]
    
    for i, q in enumerate(shuffled):
        selected = st.session_state.answers.get(i)
        correct_letter = q.get("correct")
        correct_option = next((opt for opt in q["options"] if opt.startswith(f"{correct_letter}.")), None)
        
        st.write(f"**Q{i+1}: {q['question']}**")
        
        if selected == correct_option:
            st.success(f"✅ **Correct!** {selected}")
            score += 1
        else:
            st.error(f"❌ **Wrong.** You chose: {selected or 'No answer'}")
            if correct_option:
                st.info(f"✔️ **Correct answer:** {correct_option}")
        
        if q.get("explanation"):
            st.info(f"💡 **Explanation:** {q['explanation']}")
        st.write("---")
    
    # Final score
    percentage = (score / len(shuffled)) * 100 if shuffled else 0
    st.write(f"## 🏆 Final Score: {score}/{len(shuffled)} ({percentage:.1f}%)")
    
    if percentage >= 80:
        st.balloons()
        st.success("🎉 Excellent work!")
    elif percentage >= 60:
        st.success("👍 Good job!")
    else:
        st.info("📚 Keep studying and try again!")
    
    # Provider credit
    st.info(f"Quiz generated by: **{selected_provider}**")
