import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize the OpenAI client pointing to FreeLLMAPI
client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)

def test_ai():
    print("Sending test message to FreeLLMAPI...")
    try:
        response = client.chat.completions.create(
            model="auto", # FreeLLMAPI automatically routes to the best available free model
            messages=[
                {"role": "system", "content": "You are a helpful study abroad advisor."},
                {"role": "user", "content": "I have 78% in CBSE Commerce with Maths. Can I get into a German public university for a Bachelor's in Economics?"}
            ]
        )
        
        print("\n--- AI RESPONSE ---")
        print(response.choices[0].message.content)
        print("-------------------")
        print("\n✅ Connection Successful!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Check your LLM_API_KEY and LLM_BASE_URL in the .env file.")
        print("Also, make sure the FreeLLMAPI app is open and running on your computer.")

if __name__ == "__main__":
    test_ai()