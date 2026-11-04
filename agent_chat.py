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

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_programs",
            "description": "Search the database for German university programs based on a field of study.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Subject e.g. Artificial Intelligence"}
                },
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
                "properties": {
                    "query": {"type": "string", "description": "e.g. blocked account, tuition fees"}
                },
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
    if not results: return "No programs found matching that keyword."
    return [{"program": p.title, "degree": p.degree_type, "tuition": p.tuition_fee_eur} for p in results]

def execute_search_policies(query):
    db = SessionLocal()
    print(f"   [Tool Executing]: Searching Vector DB for policies on '{query}'...")
    q_emb = client.embeddings.create(input=[query], model="auto").data[0].embedding
    results = db.query(models.PolicyDocument).order_by(
        models.PolicyDocument.embedding.cosine_distance(q_emb)
    ).limit(3).all()
    db.close()
    if not results: return "No policies found matching that query."
    return [r.chunk_text for r in results]

def start_chat():
    print("🤖 Germany Study Advisor Agent Initialized. Type 'quit' to exit.")
    
    # SYSTEM PROMPT: Tell the AI exactly how to behave
    messages = [
        {"role": "system", "content": "You are an expert Germany study abroad advisor. You have tools to search for programs and policies. When a user asks a complex question, use your tools to gather facts. THEN, write a comprehensive, detailed roadmap and explanation for the student. Do not just list data; explain it warmly."}
    ]

    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ['quit', 'exit']: break
            
        messages.append({"role": "user", "content": user_input})

        try:
            # Attempt standard tool calling
            response = client.chat.completions.create(
                model="auto",
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # HACK: Check if the model output raw XML text instead of JSON tool_calls
            if not tool_calls and "<tool_call>" in str(response_message.content):
                print("   [System]: Detected text-based tool call. Parsing manually...")
                # Parse the XML manually
                content = response_message.content
                func_match = re.search(r'<function=(\w+)>', content)
                param_match = re.search(r'<parameter=\w+>\s*(.*?)\s*</parameter>', content, re.DOTALL)
                
                if func_match:
                    func_name = func_match.group(1)
                    param_val = param_match.group(1).strip() if param_match else ""
                    
                    # Run the tool manually
                    if func_name == "search_programs":
                        tool_result = execute_search_programs(param_val)
                    else:
                        tool_result = execute_search_policies(param_val)
                        
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"Tool result: {json.dumps(tool_result)}. Now, based on this, give me a detailed roadmap and explanation."})
                    
                    # SECOND CALL: Generate the final answer
                    second_response = client.chat.completions.create(
                        model="auto",
                        messages=messages
                    )
                    print(f"\nAdvisor: {second_response.choices[0].message.content}")
                    messages.append({"role": "assistant", "content": second_response.choices[0].message.content})
                    continue

            # If standard tool calling worked, process it
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
                
                # Add a prompt to force the roadmap
                messages.append({"role": "user", "content": "Now, based on the tool results above, write a detailed roadmap and explanation for me."})
                
                second_response = client.chat.completions.create(
                    model="auto",
                    messages=messages
                )
                print(f"\nAdvisor: {second_response.choices[0].message.content}")
                messages.append({"role": "assistant", "content": second_response.choices[0].message.content})
                
            else:
                print(f"\nAdvisor: {response_message.content}")
                messages.append({"role": "assistant", "content": response_message.content})

        except Exception as e:
            print(f"❌ API Error: {e}")

if __name__ == "__main__":
    start_chat()