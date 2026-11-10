import streamlit as st
import os
import json
import platform
import re
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from sqlalchemy import or_
from database import SessionLocal
import models
from ddgs import DDGS
import pymupdf
import pytesseract
from PIL import Image
import io

# Load environment variables
load_dotenv()

# Cross-platform Tesseract Fix
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# --- MULTI-KEY & MULTI-MODEL ROTATION SETUP ---
if "GROQ_KEY_1" in st.secrets:
    api_keys = [st.secrets["GROQ_KEY_1"], st.secrets["GROQ_KEY_2"], st.secrets["GROQ_KEY_3"]]
else:
    api_keys = [os.getenv("GROQ_KEY_1"), os.getenv("GROQ_KEY_2"), os.getenv("GROQ_KEY_3")]

api_keys = [k for k in api_keys if k]
base_url = "https://api.groq.com/openai/v1"

FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "llama-3.1-8b-instant"
]

def get_ai_response(messages, tools=None, stream=False):
    last_error = None
    for key in api_keys:
        for model in FALLBACK_MODELS:
            try:
                client = OpenAI(api_key=key, base_url=base_url)
                kwargs = {"model": model, "messages": messages}
                if tools and not stream: kwargs["tools"] = tools
                if stream: kwargs["stream"] = True
                return client.chat.completions.create(**kwargs)
            except Exception as e:
                error_str = str(e).lower()
                last_error = e
                if any(err in error_str for err in ["429", "rate limit", "404", "not found", "does not exist"]):
                    continue 
                else:
                    raise e 
    raise Exception(f"All models failed. Last error: {last_error}")

# --- PAGE CONFIG ---
st.set_page_config(page_title="Kompass - Germany Study Advisor", page_icon="🧭", layout="wide")
st.title("🧭 Kompass - Germany Study Advisor")
st.markdown("Your personal AI counselor for studying in Germany.")

# --- VERIFIED FACTS (Hardcoded to prevent hallucination) ---
VERIFIED_FACTS = """
1. BLOCKED ACCOUNT: 11,208 EUR per year (934 EUR/month) as of 2024/2025 (Source: German Federal Foreign Office).
2. EU BLUE CARD (2024): Regular threshold is 58,400 EUR/year. Shortage occupation threshold is 45,552 EUR/year (Source: Make it in Germany).
3. PUBLIC VS PRIVATE: Public universities in Germany generally do NOT charge tuition fees for Bachelor's and consecutive Master's programs (except Baden-Württemberg for non-EU). They only charge a semester contribution (150-350 EUR). Private universities DO charge high tuition (10,000-20,000+ EUR).
4. TUM FEES: TU Munich does NOT charge tuition for standard Master's programs (except specific executive/part-time ones). It charges a semester fee.
5. 3-YEAR BACHELOR = 180 ECTS (60 ECTS per academic year).
"""

# --- BACKEND FUNCTIONS ---
def execute_search_germany_programs(keyword, degree_level=None, teaching_language=None, is_public=None):
    db = SessionLocal()
    query = db.query(models.Program).join(models.University)
    # Handle None/null values gracefully
    if keyword and keyword != "null":
        search_term = "Electrical" if "ece" in keyword.lower() else keyword
        query = query.filter(or_(models.Program.title.ilike(f"%{search_term}%"), models.Program.field_of_study.ilike(f"%{search_term}%"), models.Program.title.ilike(f"%{keyword}%")))
    if degree_level and degree_level != "null": query = query.filter(models.Program.degree_type.ilike(f"%{degree_level}%"))
    if teaching_language and teaching_language != "null": query = query.filter(models.Program.language.ilike(f"%{teaching_language}%"))
    if is_public is not None and is_public != "null": 
        query = query.filter(models.University.institution_type.ilike("%public%"))
    
    results = query.limit(5).all()
    formatted_results = [{"university": p.university.official_name if p.university else "Unknown", "program": p.title, "degree": p.degree_type, "tuition_eur": p.tuition_fee_eur} for p in results]
    db.close()
    
    if not formatted_results:
        return "CRITICAL: 0 results found in the database. You MUST tell the user you couldn't find the program in your database. Do NOT invent a program."
    return formatted_results

def execute_search_policies(query):
    db = SessionLocal()
    try:
        results = db.query(models.PolicyDocument).filter(models.PolicyDocument.chunk_text.ilike(f"%{query}%")).limit(3).all()
        extracted_texts = [r.chunk_text for r in results] if results else []
    except Exception as e:
        extracted_texts = [f"Policy search error: {str(e)}"]
    db.close()
    if not extracted_texts:
        return "No policies found matching that query in the database. Do NOT guess the rule."
    return extracted_texts

def execute_web_search(query):
    try:
        results = DDGS().text(query + " Germany study abroad", max_results=3)
        return [f"Title: {r.get('title')}\nSource: {r.get('href')}\nSnippet: {r.get('body')}" for r in results] if results else "No internet results found."
    except Exception as e: return f"Web search failed: {e}"

def calculate_german_grade(cgpa, max_grade=10.0, min_pass=4.0):
    """Calculates Modified Bavarian Formula deterministically."""
    try:
        cgpa = float(cgpa)
        max_grade = float(max_grade)
        min_pass = float(min_pass)
        # 1 + 3 * (Nmax - Nd) / (Nmax - Nmin)
        result = 1 + 3 * (max_grade - cgpa) / (max_grade - min_pass)
        return f"The German grade equivalent is {round(result, 2)}."
    except Exception as e:
        return f"Math error: {e}"

# --- TOOLS DEFINITION (FIXED SCHEMA) ---
tools = [
    {
        "type": "function", 
        "function": {
            "name": "search_germany_programs", 
            "description": "Search DB for German programs.", 
            "parameters": {
                "type": "object", 
                "properties": {
                    "keyword": {"type": ["string", "null"]}, 
                    "degree_level": {"type": ["string", "null"]}, 
                    "teaching_language": {"type": ["string", "null"]}, 
                    "is_public": {"type": ["boolean", "null"]}
                }, 
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "search_policies", 
            "description": "Search DB for visa/APS/finance rules.", 
            "parameters": {
                "type": "object", 
                "properties": {"query": {"type": ["string", "null"]}}, 
                "required": ["query"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "search_internet", 
            "description": "Search live internet for recent news.", 
            "parameters": {
                "type": "object", 
                "properties": {"query": {"type": ["string", "null"]}}, 
                "required": ["query"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "calculate_german_grade", 
            "description": "Use this tool to convert an Indian CGPA to a German grade. NEVER calculate this yourself.", 
            "parameters": {
                "type": "object", 
                "properties": {
                    "cgpa": {"type": "number", "description": "The student's CGPA"},
                    "max_grade": {"type": "number", "description": "Max possible CGPA, default 10"},
                    "min_pass": {"type": "number", "description": "Passing CGPA, default 4"}
                }, 
                "required": ["cgpa"]
            }
        }
    }
]

# --- STREAMING HELPER ---
def stream_generator(response):
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

# --- SIDEBAR: CV UPLOAD (FIXED PROMPT) ---
with st.sidebar:
    st.header("📄 Upload Your CV")
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    if "user_profile" not in st.session_state:
        st.session_state.user_profile = None
    if uploaded_file is not None:
        if st.button("Process CV"):
            with st.spinner("Structuring CV..."):
                doc = pymupdf.open(stream=uploaded_file.read(), filetype="pdf")
                raw_text = "".join([page.get_text() for page in doc])
                doc.close()
                # STRICT CV PROMPT
                prompt = f"""Extract the CV information into JSON. DO NOT summarize. Extract EVERY detail.
                SCHEMA: {{"name": "string", "education": [{{"degree": "string", "institution": "string", "year": "string"}}], "skills": ["string"], "experience": [{{"role": "string", "company": "string", "duration": "string", "description": "string"}}]}} 
                CV TEXT: {raw_text[:5000]}"""
                response = get_ai_response(messages=[{"role": "user", "content": prompt}])
                json_str = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
                try:
                    profile_data = json.loads(json_str)
                    name = profile_data.get("name", "Unknown")
                    db = SessionLocal()
                    db.add(models.StudentProfile(name=name, profile_json=json_str))
                    db.commit()
                    db.close()
                    st.session_state.user_profile = json_str
                    st.success(f"✅ Profile loaded for {name}!")
                except Exception as e:
                    st.error(f"Error: {e}")

# --- MAIN CHAT INTERFACE ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm Kompass. Upload your CV on the left, or tell me about your background, and let's find your perfect path to Germany."}]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask Kompass anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    profile_data = st.session_state.get("user_profile")
    profile_context = f"\n\n[STUDENT PROFILE ON FILE: \n{profile_data}]" if profile_data else "\n\n[No CV uploaded yet. DO NOT assume you know the user's name or background.]"
    
    today_date = datetime.now().strftime("%d %B %Y")

    system_prompt = f"""You are Kompass, an expert and friendly Germany study advisor. 
    Today's date is: {today_date}. Use this for all math related to deadlines.
    
    {profile_context}
    
    *** HARDCODED VERIFIED FACTS (Use these over any other memory) ***
    {VERIFIED_FACTS}
    
    *** STRICT RULES ***
    1. NEVER INVENT: If the search tool returns "0 results" or "not found", you MUST tell the user: "I couldn't find that in my database." DO NOT hallucinate universities, scholarships, or deadlines.
    2. NEVER DO MATH: If asked to convert a grade, you MUST use the `calculate_german_grade` tool. Do not calculate it yourself.
    3. NO HTML/LATEX: You are outputting Markdown. NEVER use `<br>`, `<p>`, or LaTeX like `$$`. Use standard Markdown tables and lists.
    4. BE CONVERSATIONAL: Address the user's points one by one. If asked a list of questions, number them correctly (1, 2, 3...) matching the user's prompt.
    5. SOURCES: If you use the internet or verified facts, provide the source link if available. Do not call something "official" unless it is from a retrieved source.
    """

    api_messages = [{"role": "system", "content": system_prompt}]
    for msg in st.session_state.messages:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    with st.chat_message("assistant"):
        try:
            # STEP 1: Tool call
            response = get_ai_response(messages=api_messages, tools=tools, stream=False)
            response_message = response.choices[0].message
            
            if response_message.tool_calls:
                status_placeholder = st.empty()
                status_placeholder.caption("🔍 Analyzing database...")
                
                tool_text_results = []
                
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    try:
                        if function_name == "search_germany_programs":
                            res = execute_search_germany_programs(function_args.get("keyword"), function_args.get("degree_level"), function_args.get("teaching_language"), function_args.get("is_public"))
                        elif function_name == "search_policies":
                            res = execute_search_policies(function_args.get("query"))
                        elif function_name == "search_internet":
                            res = execute_web_search(function_args.get("query"))
                        elif function_name == "calculate_german_grade":
                            res = calculate_german_grade(function_args.get("cgpa"), function_args.get("max_grade", 10), function_args.get("min_pass", 4))
                    except Exception as e:
                        res = f"Tool execution failed: {str(e)}"
                        
                    tool_text_results.append(f"Results for {function_name}: {json.dumps(res)}")
                
                status_placeholder.empty()
                
                # THE FIX: Flatten tool history to plain text to prevent Groq streaming crash
                clean_messages = [{"role": "system", "content": system_prompt}]
                for m in st.session_state.messages[:-1]: 
                    clean_messages.append({"role": m["role"], "content": m["content"]})
                
                clean_messages.append({"role": "user", "content": f"{prompt}\n\n[SYSTEM DATA FROM SEARCH]:\n" + "\n".join(tool_text_results) + "\n\nNow, provide your final answer based on this data. Follow all STRICT RULES."})
                
                stream = get_ai_response(messages=clean_messages, stream=True)
                final_text = st.write_stream(stream_generator(stream))
                
            else:
                stream = get_ai_response(messages=api_messages, stream=True)
                final_text = st.write_stream(stream_generator(stream))
            
            # Cleanup any accidental HTML/LaTeX
            final_text = str(final_text).replace("<br>", "\n").replace("<br/>", "\n").replace("<p>", "").replace("</p>", "\n")
            final_text = re.sub(r'\$\$(.*?)\$\$', r'\1', final_text)
            final_text = re.sub(r'<[^>]+>', '', final_text).strip()
            
            st.session_state.messages.append({"role": "assistant", "content": final_text})
            
        except Exception as e:
            st.error(f"Error: {e}")