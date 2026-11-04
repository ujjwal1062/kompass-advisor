import json
import os
from openai import OpenAI
from dotenv import load_dotenv
from database import SessionLocal
import models
from sqlalchemy import or_

load_dotenv()

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)

# --- SIMPLIFIED CHATBOT LOGIC (For evaluation only) ---
def run_chatbot_query(question):
    # This is a simplified version of your chat.py logic.
    # It searches the DB and generates an answer.
    db = SessionLocal()
    
    # 1. Vector Search for policies
    q_emb = client.embeddings.create(input=[question], model="auto").data[0].embedding
    results = db.query(models.PolicyDocument).order_by(
        models.PolicyDocument.embedding.cosine_distance(q_emb)
    ).limit(3).all()
    
    context = "\n\n".join([r.chunk_text for r in results]) if results else "No context found."
    db.close()
    
    # 2. Generate Answer
    prompt = f"""
    Use ONLY the following context to answer the user's question.
    If the answer is not in the context, say "I don't have that specific information."
    
    CONTEXT:
    {context}
    
    QUESTION: {question}
    """
    
    response = client.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content, context

# --- EVALUATION JUDGE ---
def evaluate_response(question, answer, expected_keywords):
    judge_prompt = f"""
    You are an impartial judge evaluating an AI advisor.
    
    Question asked: {question}
    Expected keywords/concepts: {expected_keywords}
    AI's Answer: {answer}
    
    Does the AI's answer contain the expected keywords or concepts? 
    Answer strictly with "PASS" or "FAIL". Then explain why in one sentence.
    """
    
    response = client.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": judge_prompt}]
    )
    return response.choices[0].message.content

# --- MAIN EVALUATION LOOP ---
def run_evaluation():
    with open('golden_dataset.json', 'r') as f:
        test_cases = json.load(f)
        
    print(f"🧪 Running {len(test_cases)} test cases...\n")
    passed = 0
    
    for i, test in enumerate(test_cases):
        print(f"--- Test {i+1}: {test['question']} ---")
        
        # 1. Get the AI's answer
        answer, context = run_chatbot_query(test['question'])
        
        # 2. Grade the answer
        grade = evaluate_response(test['question'], answer, test['expected_keywords'])
        
        print(f"Answer: {answer[:200]}...")
        print(f"Grade: {grade}\n")
        
        if "PASS" in grade:
            passed += 1
            
    print(f"📊 Final Score: {passed}/{len(test_cases)} tests passed.")

if __name__ == "__main__":
    run_evaluation()