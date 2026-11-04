import os
from openai import OpenAI
from dotenv import load_dotenv
from database import SessionLocal, engine
import models

load_dotenv()

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)

def get_embedding(text):
    response = client.embeddings.create(
        input=[text],
        model="auto"
    )
    return response.data[0].embedding

def ask_advisor(question):
    db = SessionLocal()
    try:
        print(f"\nUser: {question}")
        print("Searching database for relevant rules...")
        
        # 1. Convert the user's question into a vector
        question_embedding = get_embedding(question)
        
        # 2. Search the database for the 3 most similar rules using cosine distance
        # pgvector uses the <=> operator for cosine distance (lower is better)
        results = db.query(models.PolicyDocument).order_by(
            models.PolicyDocument.embedding.cosine_distance(question_embedding)
        ).limit(3).all()
        
        if not results:
            print("No relevant documents found.")
            return

        # 3. Combine the retrieved text into a context block
        context = "\n\n---\n\n".join([doc.chunk_text for doc in results])
        
        print("\n--- CONTEXT FOUND IN DATABASE ---")
        print(context[:500] + "... (truncated for display)\n") # Show a preview
        
        # 4. Ask the LLM to answer using ONLY the retrieved context
        prompt = f"""
        You are a helpful Germany study abroad advisor. 
        Use ONLY the following context to answer the user's question. 
        If the answer is not in the context, say "I don't have that specific information in my database right now."
        
        CONTEXT:
        {context}
        
        USER QUESTION: {question}
        """
        
        print("Generating answer with FreeLLMAPI...")
        response = client.chat.completions.create(
            model="auto",
            messages=[
                {"role": "system", "content": "You are a strict, factual advisor. Do not hallucinate."},
                {"role": "user", "content": prompt}
            ]
        )
        
        print("\n--- AI ADVISOR RESPONSE ---")
        print(response.choices[0].message.content)
        print("---------------------------")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # Test questions designed to hit your visa guardrails data
    ask_advisor("What are the rules for working in Germany after I graduate?")
    ask_advisor("What should I do if my visa application is rejected?")