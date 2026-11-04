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

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)

# ... [Keep all the Tools definition and Tool execution functions exactly the same] ...
tools = [
    {"type": "function", "function": {"name": "search_programs", "description": "Search local DB for programs.", "parameters": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}}},
    {"type": "function", "function": {"name": "search_policies", "description": "Search local DB for policies.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_internet", "description": "Search the live internet for recent news/deadlines.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}
]

def execute_search_programs(keyword):
    db = SessionLocal()
    print(f"   [Tool]: Searching SQL for programs related to '{keyword}'...")
    results = db.query(models.Program).filter(or_(models.Program.title.ilike(f"%{keyword}%"), models.Program.field_of_study.ilike(f"%{keyword}%"))).limit(5).all()
    db.close()
    if not results: return "No programs found."
    return [{"program": p.title, "degree": p.degree_type, "tuition": p.tuition_fee_eur} for p in results]

def execute_search_policies(query):
    db = SessionLocal()
    print(f"   [Tool]: Searching Vector DB for policies on '{query}'...")
    q_emb = client.embeddings.create(input=[query], model="auto").data[0].embedding
    results = db.query(models.PolicyDocument).order_by(models.PolicyDocument.embedding.cosine_distance(q_emb)).limit(3).all()
    db.close()
    if not results: return "No policies found."
    return [r.chunk_text for r in results]

def execute_web_search(query):
    print(f"   [Tool]: Searching the live internet for '{query}'...")
    try:
        results = DDGS().text(query, max_results=3)
        if not results: return "No internet results found."
        return [f"Title: {r.get('title')}\nSource: {r.get('href')}\nSnippet: {r.get('body')}" for r in results]
    except Exception as e:
        return f"Web search failed: {e}"

def manage_memory(messages):
    if len(messages) > 8:
        print("   [System]: Summarizing memory...")
        summary_prompt = [{"role": "system", "content": "Summarize the user's profile and goals."}, {"role": "user", "content": str(messages[1:])}]
        summary_response = client.chat.completions.create(model="auto", messages=summary_prompt)
        return [messages[0], {"role": "system", "content": f"Summary: {summary_response.choices[0].message.content}"}]
    return messages

# --- NEW STREAMING FUNCTION ---
def stream_and_save_response(messages):
    """Streams the text to the terminal word-by-word for instant feedback."""
    print("\nAlex: ", end="", flush=True)
    full_response = ""
    
    try:
        response = client.chat.completions.create(
            model="auto",
            messages=messages,
            stream=True # <--- THIS IS THE MAGIC
        )
        
        for chunk in response:
            if chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                print(text, end="", flush=True)
                full_response += text
        print("\n") # New line when done
        return full_response
    except Exception as e:
        print(f"\n❌ API Error during streaming: {e}")
        return ""

def start_chat():
    print("🤖 Germany Study Advisor (v4 - Streamed) Initialized. Type 'quit' to exit.")
    
    system_prompt = {
        "role": "system", 
        "content": (
            "You are Alex, a friendly, highly experienced study-abroad advisor based in Delhi. "
            "Talk like a human mentor. You have tools: search_programs, search_policies, and search_internet. "
            "Use search_internet for time-sensitive queries (2025/2026 deadlines). "
            "Always synthesize the data naturally and provide source links if from the web."
        )
    }

    messages = [system_prompt]

    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ['quit', 'exit']: break
            
        messages.append({"role": "user", "content": user_input})
        messages = manage_memory(messages)

        try:
            # First Call: Check if tools are needed (No streaming here, we need the tool JSON)
            response = client.chat.completions.create(
                model="auto",
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            if tool_calls:
                messages.append(response_message)
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    if function_name == "search_programs":
                        function_response = execute_search_programs(function_args.get("keyword"))
                    elif function_name == "search_policies":
                        function_response = execute_search_policies(function_args.get("query"))
                    else:
                        function_response = execute_web_search(function_args.get("query"))

                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": json.dumps(function_response)
                    })
                
                # Second Call: Stream the final answer
                final_text = stream_and_save_response(messages)
                messages.append({"role": "assistant", "content": final_text})
            
            # Handle messy XML tool calls (Text-based)
            elif "<tool_call>" in str(response_message.content):
                print("   [System]: Parsing text-based tool call...")
                content = response_message.content
                func_match = re.search(r'<function=(\w+)>', content)
                param_match = re.search(r'<parameter=\w+>\s*(.*?)\s*</parameter>', content, re.DOTALL)
                
                if func_match:
                    func_name = func_match.group(1)
                    param_val = param_match.group(1).strip() if param_match else ""
                    
                    if func_name == "search_programs": tool_result = execute_search_programs(param_val)
                    elif func_name == "search_policies": tool_result = execute_search_policies(param_val)
                    else: tool_result = execute_web_search(param_val)
                        
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"Tool result: {json.dumps(tool_result)}. Now answer me."})
                    
                    final_text = stream_and_save_response(messages)
                    messages.append({"role": "assistant", "content": final_text})
                    continue

            else:
                # No tools needed, just stream the direct chat
                messages.pop() # Remove user message temporarily to stream correctly
                final_text = stream_and_save_response(messages)
                messages.append({"role": "user", "content": user_input}) # Add it back
                messages.append({"role": "assistant", "content": final_text})

        except Exception as e:
            print(f"❌ API Error: {e}")

if __name__ == "__main__":
    start_chat()