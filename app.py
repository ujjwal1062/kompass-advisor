import streamlit as st
import os
import json
import platform
import re
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
    """Rotates through keys/models. If streaming, tools are ALWAYS stripped."""
    last_error = None
    for key in api_keys:
        for model in FALLBACK_MODELS:
            try:
                client = OpenAI(api_key=key, base_url=base_url)
                kwargs = {"model": model, "messages": messages}
                
                # CRITICAL: Only pass tools if we are NOT streaming.
                if tools and not stream: 
                    kwargs["tools"] = tools
                
                if stream: 
                    kwargs["stream"] = True
                
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

# --- BACKEND FUNCTIONS ---
def execute_search_germany_programs(keyword, degree_level=None, teaching_language=None, is_public=None):
    db = SessionLocal()
    query = db.query(models.Program).join(models.University)
    if keyword:
        search_term = "Electrical" if "ece" in keyword.lower() else keyword
        query = query.filter(or_(models.Program.title.ilike(f"%{search_term}%"), models.Program.field_of_study.ilike(f"%{search_term}%"), models.Program.title.ilike(f"%{keyword}%")))
    if degree_level: query = query.filter(models.Program.degree_type.ilike(f"%{degree_level}%"))
    if teaching_language: query = query.filter(models.Program.language.ilike(f"%{teaching_language}%"))
    if is_public is not None: query = query.filter(models.University.institution_type.ilike("%public%"))
    
    results = query.limit(5).all()
    formatted_results = [{"university": p.university.official_name if p.university else "Unknown", "program": p.title, "degree": p.degree_type, "tuition_eur": p.tuition_fee_eur} for p in results]
    db.close()
    return formatted_results if formatted_results else "0 results found."

def execute_search_policies(query):
    db = SessionLocal()
    try:
        results = db.query(models.PolicyDocument).filter(models.PolicyDocument.chunk_text.ilike(f"%{query}%")).limit(3).all()
        extracted_texts = [r.chunk_text for r in results] if results else []
    except Exception as e:
        extracted_texts = [f"Policy search error: {str(e)}"]
    db.close()
    return extracted_texts if extracted_texts else "No policies found matching that query."

def execute_web_search(query):
    try:
        results = DDGS().text(query + " Germany study abroad", max_results=3)
        return [f"Title: {r.get('title')}\nSource: {r.get('href')}\nSnippet: {r.get('body')}" for r in results] if results else "No internet results."
    except Exception as e: return f"Web search failed: {e}"

# --- TOOLS DEFINITION ---
tools = [
    {"type": "function", "function": {"name": "search_germany_programs", "description": "Search DB for German programs.", "parameters": {"type": "object", "properties": {"keyword": {"type": "string"}, "degree_level": {"type": "string"}, "teaching_language": {"type": "string"}, "is_public": {"type": "boolean"}}, "required": ["keyword"]}}},
    {"type": "function", "function": {"name": "search_policies", "description": "Search DB for visa/APS/finance rules.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_internet", "description": "Search live internet for recent news.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}
]

# --- STREAMING HELPER ---
def stream_generator(response):
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

# --- SIDEBAR: CV UPLOAD ---
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
                prompt = f"""Extract the CV information into JSON: {{"name": "string", "education": [{{"degree": "string", "institution": "string", "year": "string"}}], "skills": ["string"], "experience": [{{"role": "string", "company": "string", "description": "string"}}]}} \n CV TEXT: {raw_text[:5000]}"""
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

    system_prompt = f"""You are Kompass, an expert and friendly Germany study advisor. 
    You are speaking directly to a student. Talk like a human mentor, not a search engine.
    {profile_context}
    
    RULES:
    1. ADAPT TO THE USER: If they are in 11th grade, talk about Bachelors. If they have a BCA, talk about Masters.
    2. PERSONALIZE: Acknowledge their background if provided. 
    3. BE CONVERSATIONAL: Never output raw tables or JSON. Translate data into friendly advice.
    4. BE CONCISE: Match the length of the user's message.
    """

    api_messages = [{"role": "system", "content": system_prompt}]
    for msg in st.session_state.messages:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    with st.chat_message("assistant"):
        try:
            # STEP 1: Check if tools are needed
            response = get_ai_response(messages=api_messages, tools=tools, stream=False)
            response_message = response.choices[0].message
            
            if response_message.tool_calls:
                status_placeholder = st.empty()
                status_placeholder.caption("🔍 Analyzing database...")
                
                # THE FIX: We don't append raw tool calls. We collect the text results.
                tool_text_results = []
                
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    if function_name == "search_germany_programs":
                        res = execute_search_germany_programs(function_args.get("keyword"), function_args.get("degree_level"), function_args.get("teaching_language"), function_args.get("is_public"))
                    elif function_name == "search_policies":
                        res = execute_search_policies(function_args.get("query"))
                    else:
                        res = execute_web_search(function_args.get("query"))
                        
                    tool_text_results.append(f"Results for {function_name}: {json.dumps(res)}")
                
                status_placeholder.empty()
                
                # THE FIX: Create a CLEAN message history for the streaming call.
                # We take the original messages, add the user prompt, and inject the tool results as plain text.
                # This completely removes any "role: tool" or "tool_calls" history that confuses Groq.
                clean_messages = [{"role": "system", "content": system_prompt}]
                for m in st.session_state.messages[:-1]: # Exclude the latest prompt temporarily
                    clean_messages.append({"role": m["role"], "content": m["content"]})
                
                clean_messages.append({"role": "user", "content": f"{prompt}\n\n[SYSTEM DATA FROM SEARCH]:\n" + "\n".join(tool_text_results) + "\n\nNow, provide your final answer based on this data."})
                
                # STEP 2: Stream with clean history and NO tools
                stream = get_ai_response(messages=clean_messages, stream=True)
                final_text = st.write_stream(stream_generator(stream))
                
            else:
                # If no tools needed, just stream normally
                stream = get_ai_response(messages=api_messages, stream=True)
                final_text = st.write_stream(stream_generator(stream))
            
            final_text = re.sub(r'<[^>]+>', '', str(final_text)).strip()
            st.session_state.messages.append({"role": "assistant", "content": final_text})
            
        except Exception as e:
            st.error(f"Error: {e}")