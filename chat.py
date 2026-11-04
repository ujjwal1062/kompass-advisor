import os
import json
import re
from openai import OpenAI
from dotenv import load_dotenv
from sqlalchemy import or_
from database import SessionLocal
import models
from ddgs import DDGS

load_dotenv()

client = OpenAI(api_key=os.getenv("LLM_API_KEY"), base_url=os.getenv("LLM_BASE_URL"))

tools = [
    {"type": "function", "function": {"name": "search_germany_programs", "description": "Search DB for German programs.", "parameters": {"type": "object", "properties": {"keyword": {"type": "string"}, "degree_level": {"type": "string"}, "teaching_language": {"type": "string"}, "is_public": {"type": "boolean"}}, "required": ["keyword"]}}},
    {"type": "function", "function": {"name": "search_policies", "description": "Search DB for visa/APS/finance rules.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_internet", "description": "Search live internet for recent news/deadlines.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}
]

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
    
    formatted_results = []
    for p in results:
        formatted_results.append({
            "university": p.university.official_name if p.university else "Unknown",
            "program": p.title,
            "degree": p.degree_type,
            "tuition_eur": p.tuition_fee_eur
        })
        
    db.close()
    return formatted_results if formatted_results else "0 results found. Use search_internet."

def execute_search_policies(query):
    db = SessionLocal()
    q_emb = client.embeddings.create(input=[query], model="auto").data[0].embedding
    results = db.query(models.PolicyDocument).order_by(models.PolicyDocument.embedding.cosine_distance(q_emb)).limit(3).all()
    extracted_texts = [r.chunk_text for r in results] if results else []
    db.close()
    return extracted_texts if extracted_texts else "No policies found."

def execute_web_search(query):
    try:
        results = DDGS().text(query + " Germany study abroad", max_results=3)
        return [f"Title: {r.get('title')}\nSource: {r.get('href')}\nSnippet: {r.get('body')}" for r in results] if results else "No internet results."
    except Exception as e: return f"Web search failed: {e}"

def execute_get_student_profile():
    print("   [Tool Executing]: Fetching student profile from DB...")
    db = SessionLocal()
    profile = db.query(models.StudentProfile).order_by(models.StudentProfile.id.desc()).first()
    if profile:
        profile_data = f"Student Name: {profile.name}\nProfile Data: {profile.profile_json}"
        db.close()
        print(f"   [Tool Success]: Found profile for {profile.name}")
        return profile_data
    db.close()
    return "No student profile found in the database."

def manage_memory(messages):
    if len(messages) > 10:
        print("   [System]: Summarizing memory...")
        summary_prompt = [{"role": "system", "content": "Summarize the user's profile and goals."}, {"role": "user", "content": str(messages[1:])}]
        summary_response = client.chat.completions.create(model="auto", messages=summary_prompt)
        return [messages[0], {"role": "system", "content": f"Summary: {summary_response.choices[0].message.content}"}]
    return messages

def stream_and_save_response(messages):
    print("\nAlex: ", end="", flush=True)
    full_response = ""
    try:
        response = client.chat.completions.create(model="auto", messages=messages, stream=True)
        for chunk in response:
            if hasattr(chunk, 'choices') and chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    print(delta.content, end="", flush=True)
                    full_response += delta.content
        print("\n") 
        return full_response
    except Exception as e:
        print(f"\n❌ API Error: {e}")
        return "Error."

def start_chat():
    print("🤖 Germany Study Advisor (v9 - Multi-Tool Parser). Type 'quit' to exit.")
    
    system_prompt = {
        "role": "system", 
        "content": (
            "You are Alex, an expert advisor for studying in GERMANY. "
            "CRITICAL RULES:\n"
            "1. If a user asks for program recommendations, you MUST use `search_germany_programs`. DO NOT use `search_internet` to find programs. The local database is the source of truth.\n"
            "2. Only use `search_internet` for recent deadlines (like 2026/2027), news, or scholarship updates.\n"
            "3. Personalize your advice based on the user's profile."
        )
    }

    messages = [system_prompt]

    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ['quit', 'exit']: break
        
        # Force Profile Fetch
        profile_context = ""
        if any(word in user_input.lower() for word in ["cv", "profile", "resume", "my skills", "my background", "my degree"]):
            profile_data = execute_get_student_profile()
            profile_context = f"\n[SYSTEM NOTE: Here is the user's actual profile data: {profile_data}. Use this to answer.]"

        messages.append({"role": "user", "content": user_input + profile_context})
        messages = manage_memory(messages)

        try:
            response = client.chat.completions.create(model="auto", messages=messages, tools=tools, tool_choice="auto")
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # 1. Standard JSON Tool Calls
            if tool_calls:
                messages.append(response_message)
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    if function_name == "search_germany_programs":
                        function_response = execute_search_germany_programs(function_args.get("keyword"), function_args.get("degree_level"), function_args.get("teaching_language"), function_args.get("is_public"))
                    elif function_name == "search_policies":
                        function_response = execute_search_policies(function_args.get("query"))
                    elif function_name == "search_internet":
                        function_response = execute_web_search(function_args.get("query"))

                    messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": function_name, "content": json.dumps(function_response)})
                
                final_text = stream_and_save_response(messages)
                messages.append({"role": "assistant", "content": final_text})
            
            # 2. HACK: Catch MULTIPLE hallucinated XML tool calls
            elif "<tool_call>" in str(response_message.content):
                print("   [System]: Detected multiple XML tool calls. Parsing...")
                content = str(response_message.content)
                
                # Find all tool call blocks
                blocks = re.findall(r'<tool_call>(.*?)</tool_call>', content, re.DOTALL)
                all_results = []
                
                for block in blocks:
                    func_match = re.search(r'<function=(\w+)>', block)
                    param_match = re.search(r'<parameter=\w+>\s*(.*?)\s*</parameter>', block, re.DOTALL)
                    
                    if func_match:
                        func_name = func_match.group(1)
                        param_val = param_match.group(1).strip() if param_match else ""
                        
                        print(f"   [System]: Executing XML {func_name} for '{param_val}'...")
                        
                        if func_name == "search_germany_programs": 
                            result = execute_search_germany_programs(keyword=param_val)
                        elif func_name == "search_policies": 
                            result = execute_search_policies(param_val)
                        else: 
                            result = execute_web_search(param_val)
                            
                        all_results.append(f"Result for {func_name}({param_val}): {json.dumps(result)}")
                
                # Send all results back to the AI
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"Here are the results from your search queries:\n" + "\n".join(all_results) + "\n\nNow answer the user's original question based on these results."})
                
                final_text = stream_and_save_response(messages)
                messages.append({"role": "assistant", "content": final_text})
                
            else:
                messages.pop()
                final_text = stream_and_save_response(messages)
                messages.append({"role": "user", "content": user_input})
                messages.append({"role": "assistant", "content": final_text})

        except Exception as e:
            print(f"❌ API Error: {e}")

if __name__ == "__main__":
    start_chat()