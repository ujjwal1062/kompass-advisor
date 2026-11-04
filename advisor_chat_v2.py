import os
import json
import re
from openai import OpenAI
from dotenv import load_dotenv
from sqlalchemy import or_
from database import SessionLocal
import models

load_dotenv()

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)

# ==========================================
# 1. DEFINE THE TOOLS (Same as before)
# ==========================================
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_programs",
            "description": "Search the database for German university programs based on a field of study.",
            "parameters": {
                "type": "object",
                "properties": {"keyword": {"type": "string"}},
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_policies",
            "description": "Search the knowledge base for visa, APS, finance, language requirements, and study rules.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    }
]

def execute_search_programs(keyword):
    db = SessionLocal()
    print(f"   [Tool Executing]: Searching SQL for programs related to '{keyword}'...")
    results = db.query(models.Program).filter(
        or_(
            models.Program.title.ilike(f"%{keyword}%"),
            models.Program.field_of_study.ilike(f"%{keyword}%")
        )
    ).limit(5).all()
    db.close()
    if not results: return "No programs found."
    return [{"program": p.title, "degree": p.degree_type, "tuition": p.tuition_fee_eur} for p in results]

def execute_search_policies(query):
    db = SessionLocal()
    print(f"   [Tool Executing]: Searching Vector DB for policies on '{query}'...")
    q_emb = client.embeddings.create(input=[query], model="auto").data[0].embedding
    results = db.query(models.PolicyDocument).order_by(
        models.PolicyDocument.embedding.cosine_distance(q_emb)
    ).limit(3).all()
    db.close()
    if not results: return "No policies found."
    return [r.chunk_text for r in results]

# ==========================================
# 2. MEMORY MANAGEMENT (Discourse Integration)
# ==========================================
def manage_memory(messages):
    """If chat gets too long, summarize it so the AI doesn't forget the user's profile."""
    if len(messages) > 8: # If more than 8 messages (4 user, 4 AI)
        print("   [System]: Context getting long. Summarizing memory...")
        
        summary_prompt = [
            {"role": "system", "content": "Summarize the user's profile, goals, and key facts discussed so far. Keep it brief but retain specific details like degrees, grades, and preferences."},
            {"role": "user", "content": str(messages[1:])} # Skip system prompt, summarize the rest
        ]
        
        summary_response = client.chat.completions.create(
            model="auto",
            messages=summary_prompt
        )
        
        summary_text = summary_response.choices[0].message.content
        
        # Reset messages to just the original system prompt + the new summary
        return [
            messages[0], 
            {"role": "system", "content": f"Here is a summary of the conversation so far: {summary_text}"}
        ]
    return messages

# ==========================================
# 3. THE HUMAN PERSONA
# ==========================================
def start_chat():
    print("🤖 Germany Study Advisor (v2) Initialized. Type 'quit' to exit.")
    
    # THIS PROMPT IS THE KEY TO MAKING IT SOUND HUMAN
    system_prompt = {
        "role": "system", 
        "content": (
            "You are Alex, a friendly, highly experienced study-abroad advisor based in Delhi. "
            "You have been helping Indian students move to Germany for 10 years. You are talking directly to a student. "
            "DO NOT sound like a robot. Never use phrases like 'Certainly', 'Great question', or 'Here is a structured roadmap'. "
            "Instead, talk to the student like a mentor. Use conversational transitions (e.g., 'Okay, so here is the deal...', 'To be honest with you...', 'Let's map this out.'). "
            "When you use your tools, weave the facts into your natural conversation. "
            "If the user asks a complex question, answer it warmly but thoroughly. "
            "Ask them follow-up questions to keep the conversation going."
        )
    }

    messages = [system_prompt]

    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ['quit', 'exit']: break
            
        messages.append({"role": "user", "content": user_input})
        
        # Manage memory before sending to LLM
        messages = manage_memory(messages)

        try:
            # First call: Does it need tools?
            response = client.chat.completions.create(
                model="auto",
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # Handle standard tool calling
            if tool_calls:
                messages.append(response_message)
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    if function_name == "search_programs":
                        function_response = execute_search_programs(function_args.get("keyword"))
                    else:
                        function_response = execute_search_policies(function_args.get("query"))

                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": json.dumps(function_response)
                    })
                
                # Second call: Generate the human response using the tool data
                second_response = client.chat.completions.create(
                    model="auto",
                    messages=messages
                )
                print(f"\nAlex: {second_response.choices[0].message.content}")
                messages.append({"role": "assistant", "content": second_response.choices[0].message.content})
            
            # Handle messy XML tool calls (from open-source models)
            elif "<tool_call>" in str(response_message.content):
                print("   [System]: Parsing text-based tool call...")
                content = response_message.content
                func_match = re.search(r'<function=(\w+)>', content)
                param_match = re.search(r'<parameter=\w+>\s*(.*?)\s*</parameter>', content, re.DOTALL)
                
                if func_match:
                    func_name = func_match.group(1)
                    param_val = param_match.group(1).strip() if param_match else ""
                    tool_result = execute_search_programs(param_val) if func_name == "search_programs" else execute_search_policies(param_val)
                        
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"Tool result: {json.dumps(tool_result)}. Now, talk to me like a human mentor."})
                    
                    second_response = client.chat.completions.create(model="auto", messages=messages)
                    print(f"\nAlex: {second_response.choices[0].message.content}")
                    messages.append({"role": "assistant", "content": second_response.choices[0].message.content})
                    continue

            # If no tools needed, just chat
            else:
                print(f"\nAlex: {response_message.content}")
                messages.append({"role": "assistant", "content": response_message.content})

        except Exception as e:
            print(f"❌ API Error: {e}")

if __name__ == "__main__":
    start_chat()