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

load_dotenv()

if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# --- MULTI-KEY SETUP ---
if "GROQ_KEY_1" in st.secrets:
    api_keys = [st.secrets["GROQ_KEY_1"], st.secrets["GROQ_KEY_2"], st.secrets["GROQ_KEY_3"]]
else:
    api_keys = [os.getenv("GROQ_KEY_1"), os.getenv("GROQ_KEY_2"), os.getenv("GROQ_KEY_3")]
api_keys = [k for k in api_keys if k]
base_url = "https://api.groq.com/openai/v1"

FALLBACK_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama-3.1-8b-instant"]

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
                # Added 413 (Request too large) to the fallback list so it instantly switches models
                if any(err in error_str for err in ["429", "rate limit", "404", "not found", "tool choice", "called a tool", "413", "request too large"]):
                    continue 
                else:
                    raise e 
    raise Exception(f"All models failed. Last error: {last_error}")

# --- PAGE CONFIG ---
st.set_page_config(page_title="Kompass - Germany Study Advisor", page_icon="🧭", layout="wide")
st.title("🧭 Kompass - Germany Study Advisor")
st.markdown("Your personal AI counselor for studying in Germany.")

VERIFIED_FACTS = """
1. BLOCKED ACCOUNT: 11,208 EUR per year (934 EUR/month).
2. EU BLUE CARD (2024): Regular 58,400 EUR/yr. Shortage 45,552 EUR/yr.
3. PUBLIC UNIS: Generally no tuition, only 150-350 EUR semester fee.
"""

# --- BACKEND FUNCTIONS ---
def execute_search_germany_programs(keyword, degree_level=None, teaching_language=None, is_public=None):
    db = SessionLocal()
    query = db.query(models.Program).join(models.University)
    if keyword and keyword != "null":
        words = keyword.lower().split()
        search_conditions = []
        for word in words:
            search_conditions.extend([
                models.Program.title.ilike(f"%{word}%"),
                models.Program.field_of_study.ilike(f"%{word}%"),
                models.University.official_name.ilike(f"%{word}%"),
                models.University.city.ilike(f"%{word}%"),
                models.University.federal_state.ilike(f"%{word}%")
            ])
        query = query.filter(or_(*search_conditions))
    if degree_level and degree_level != "null": query = query.filter(models.Program.degree_type.ilike(f"%{degree_level}%"))
    if teaching_language and teaching_language != "null": query = query.filter(models.Program.language.ilike(f"%{teaching_language}%"))
    if is_public is not None and is_public != "null": query = query.filter(models.University.institution_type.ilike("%public%"))
    
    if keyword and ("how many" in keyword.lower() or "count" in keyword.lower()):
        count = query.count()
        db.close()
        return f"Found exactly {count} programs matching those criteria in the database."

    # Reduced limit from 10 to 5 to save tokens
    results = query.limit(5).all()
    formatted = [{"university": p.university.official_name if p.university else "Unknown", "program": p.title, "degree": p.degree_type, "tuition": p.tuition_fee_eur} for p in results]
    db.close()
    return formatted if formatted else "0 results found. Use search_internet."

def execute_match_scholarships(nationality="India", degree_level="Master"):
    db = SessionLocal()
    query = db.query(models.PolicyDocument).filter(
        models.PolicyDocument.topic == "Scholarships",
        models.PolicyDocument.chunk_text.ilike(f"%{nationality}%")
    )
    if degree_level:
        query = query.filter(models.PolicyDocument.chunk_text.ilike(f"%{degree_level}%"))
        
    results = query.limit(3).all() # Reduced to 3 to save tokens
    extracted_texts = [r.chunk_text for r in results] if results else []
    db.close()
    
    if not extracted_texts:
        return f"No scholarships found for {nationality} students at the {degree_level} level in the database."
    return extracted_texts

def execute_check_anabin(university_name):
    db = SessionLocal()
    words = university_name.lower().split()
    search_conditions = []
    for word in words:
        if len(word) > 3: 
            search_conditions.append(models.IndianUniversity.name.ilike(f"%{word}%"))
            
    results = db.query(models.IndianUniversity).filter(or_(*search_conditions)).limit(2).all()
    formatted = [{"university": r.name, "status": r.h_plus_status} for r in results]
    db.close()
    
    if not formatted:
        return "0 results found in the LOCAL Anabin database. You MUST use `search_internet` to check the official Anabin portal."
    
    status = formatted[0]['status'].lower()
    if status in ['not_checked', 'not found', 'error']:
        return f"Found in local registry, but the status is '{status}'. WARNING: Our local dataset has NOT verified this university yet. You MUST use `search_internet` to check the official Anabin portal."
        
    return formatted

def execute_search_knowledge_base(query):
    db = SessionLocal()
    try:
        results = db.query(models.PolicyDocument).filter(models.PolicyDocument.chunk_text.ilike(f"%{query}%")).limit(2).all() # Reduced to 2
        extracted_texts = [r.chunk_text for r in results] if results else []
    except Exception as e:
        extracted_texts = [f"Error: {str(e)}"]
    db.close()
    return extracted_texts if extracted_texts else "0 results found. Use search_internet."

def execute_web_search(query):
    try:
        results = DDGS().text(query + " Anabin Germany recognition", max_results=3) # Reduced to 3
        return [f"Title: {r.get('title')}\nSource: {r.get('href')}\nSnippet: {r.get('body')}" for r in results] if results else "No internet results found."
    except Exception as e: return f"Web search failed: {e}"

def calculate_german_grade(cgpa, max_grade=10.0, min_pass=4.0):
    try:
        result = 1 + 3 * (float(max_grade) - float(cgpa)) / (float(max_grade) - float(min_pass))
        return f"The German grade equivalent is {round(result, 2)}."
    except Exception as e: return f"Math error: {e}"

# --- TOOLS DEFINITION ---
tools = [
    {"type": "function", "function": {"name": "search_germany_programs", "description": "Search DB for unis/programs.", "parameters": {"type": "object", "properties": {"keyword": {"type": ["string", "null"]}, "degree_level": {"type": ["string", "null"]}, "teaching_language": {"type": ["string", "null"]}, "is_public": {"type": ["boolean", "null"]}}, "required": ["keyword"]}}},
    {"type": "function", "function": {"name": "match_scholarships", "description": "Find scholarships filtered by nationality and degree level.", "parameters": {"type": "object", "properties": {"nationality": {"type": ["string", "null"]}, "degree_level": {"type": ["string", "null"]}}, "required": []}}},
    {"type": "function", "function": {"name": "check_anabin_status", "description": "Check the H+ recognition status of an Indian university.", "parameters": {"type": "object", "properties": {"university_name": {"type": "string"}}, "required": ["university_name"]}}},
    {"type": "function", "function": {"name": "search_knowledge_base", "description": "Search local DB for visas, APS, finance, AND industry/careers.", "parameters": {"type": "object", "properties": {"query": {"type": ["string", "null"]}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_internet", "description": "Use ONLY if the local DB returns 0 results or if Anabin status is 'not_checked'.", "parameters": {"type": "object", "properties": {"query": {"type": ["string", "null"]}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "calculate_german_grade", "description": "Convert CGPA to German grade.", "parameters": {"type": "object", "properties": {"cgpa": {"type": "number"}}, "required": ["cgpa"]}}}
]

def stream_generator(response):
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

# --- SIDEBAR: CV UPLOAD ---
with st.sidebar:
    st.header("📄 Upload Your CV")
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    if "user_profile" not in st.session_state: st.session_state.user_profile = None
    if uploaded_file is not None:
        if st.button("Process CV"):
            with st.spinner("Structuring CV..."):
                doc = pymupdf.open(stream=uploaded_file.read(), filetype="pdf")
                raw_text = "".join([page.get_text() for page in doc])
                doc.close()
                prompt = f"""Extract CV info to JSON. SCHEMA: {{"name": "string", "education": [{{"degree": "string", "institution": "string", "year": "string"}}], "skills": ["string"], "experience": [{{"role": "string", "company": "string", "duration": "string", "description": "string"}}]}} \n CV TEXT: {raw_text[:3000]}""" # Truncated CV text to save tokens
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

# --- MAIN CHAT ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm Kompass. Upload your CV, or ask me about programs, scholarships, Anabin status, or visas."}]

for message in st.session_state.messages:
    with st.chat_message(message["role"]): st.markdown(message["content"])

if prompt := st.chat_input("Ask Kompass anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    profile_data = st.session_state.get("user_profile")
    profile_context = f"\n\n[STUDENT PROFILE: \n{profile_data}]" if profile_data else ""
    
    system_prompt = f"""You are Kompass, an expert Germany study advisor. 
    Today is: {datetime.now().strftime("%d %B %Y")}.
    {profile_context}
    *** VERIFIED FACTS ***
    {VERIFIED_FACTS}
    
    *** RULES ***
    1. ANABIN: Use `check_anabin_status`. 
       - CRITICAL RULE: If the tool returns "0 results found" OR it returns a status of "not_checked", you must IMMEDIATELY use `search_internet` to check the live Anabin portal. Do not tell the user it is unrecognized until you have checked the internet.
    2. SCHOLARSHIPS: Use `match_scholarships` if asked about scholarships.
    3. INDUSTRY/CAREERS: Use `search_knowledge_base` for jobs/companies.
    4. LOCAL DATA FIRST. Only use `search_internet` if the local DB fails.
    5. NO HTML/LATEX. Use pure Markdown.
    6. Be a mentor, talk like a human.
    """

    api_messages = [{"role": "system", "content": system_prompt}]
    
    # --- CONTEXT TRIMMING FIX ---
    # Only keep the last 6 messages from the chat history to prevent TPM limit
    recent_messages = st.session_state.messages[-6:] if len(st.session_state.messages) > 6 else st.session_state.messages
    for msg in recent_messages: 
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    with st.chat_message("assistant"):
        try:
            response = get_ai_response(messages=api_messages, tools=tools, stream=False)
            response_message = response.choices[0].message
            
            if response_message.tool_calls:
                status_placeholder = st.empty()
                status_placeholder.caption("🔍 Searching local database...")
                tool_text_results = []
                
                for tool_call in response_message.tool_calls:
                    fn = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    try:
                        if fn == "search_germany_programs": res = execute_search_germany_programs(args.get("keyword"), args.get("degree_level"), args.get("teaching_language"), args.get("is_public"))
                        elif fn == "match_scholarships": res = execute_match_scholarships(args.get("nationality", "India"), args.get("degree_level", "Master"))
                        elif fn == "check_anabin_status": res = execute_check_anabin(args.get("university_name"))
                        elif fn == "search_knowledge_base": res = execute_search_knowledge_base(args.get("query"))
                        elif fn == "search_internet": res = execute_web_search(args.get("query"))
                        elif fn == "calculate_german_grade": res = calculate_german_grade(args.get("cgpa"))
                    except Exception as e: res = f"Error: {str(e)}"
                    tool_text_results.append(f"Results for {fn}: {json.dumps(res)}")
                
                status_placeholder.empty()
                clean_messages = [{"role": "system", "content": system_prompt}]
                for m in recent_messages[:-1]: clean_messages.append({"role": m["role"], "content": m["content"]})
                clean_messages.append({"role": "user", "content": f"{prompt}\n\n[SYSTEM DATA FROM SEARCH]:\n" + "\n".join(tool_text_results) + "\n\nNow, answer."})
                
                try:
                    stream = get_ai_response(messages=clean_messages, stream=True)
                    final_text = st.write_stream(stream_generator(stream))
                except Exception as stream_err:
                    if "tool choice" in str(stream_err).lower() or "called a tool" in str(stream_err).lower():
                        fallback_res = get_ai_response(messages=clean_messages, stream=False)
                        final_text = fallback_res.choices[0].message.content
                        st.markdown(final_text)
                    else:
                        raise stream_err
            else:
                try:
                    stream = get_ai_response(messages=api_messages, stream=True)
                    final_text = st.write_stream(stream_generator(stream))
                except Exception as stream_err:
                    if "tool choice" in str(stream_err).lower() or "called a tool" in str(stream_err).lower():
                        fallback_res = get_ai_response(messages=api_messages, stream=False)
                        final_text = fallback_res.choices[0].message.content
                        st.markdown(final_text)
                    else:
                        raise stream_err
            
            final_text = str(final_text).replace("<br>", "\n").replace("<br/>", "\n").replace("<p>", "").replace("</p>", "\n")
            final_text = re.sub(r'\$\$(.*?)\$\$', r'\1', final_text)
            final_text = re.sub(r'<[^>]+>', '', final_text).strip()
            
            st.session_state.messages.append({"role": "assistant", "content": final_text})
        except Exception as e:
            st.error(f"Error: {e}")