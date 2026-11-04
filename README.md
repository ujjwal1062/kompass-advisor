# 🧭 Kompass - AI Germany Study Advisor

Kompass is a personalized, conversational AI advisor designed to help Indian students navigate the complex journey of studying in Germany. It goes beyond simple search by understanding your unique profile and providing grounded, actionable advice.

## ✨ Key Features

*   **🧠 Personalized Advice:** Upload your CV (PDF) and the AI will extract your skills, education, and experience to tailor its recommendations to *you*.
*   **🏫 Intelligent Program Search:** Uses a powerful SQL database to find the perfect Bachelor's or Master's programs based on degree level, field of study, language, and institution type (public/private).
*   **📚 RAG-Powered Policy Knowledge:** Answers complex questions about visas, APS certificates, blocked accounts, and Studienkolleg by retrieving information from a vector database of official rules.
*   **🌐 Live Web Search:** When time-sensitive information is needed (like 2026 deadlines or recent news), the agent automatically searches the live internet to provide the most current answer.
*   **💬 Conversational Memory:** Remembers the context of your conversation, so you don't have to repeat yourself.
*   **🚀 Live & Free:** Deployed on Streamlit Community Cloud, accessible to anyone, anywhere.

## 🛠️ Technology Stack

*   **Frontend:** Streamlit
*   **Backend & AI Orchestration:** Python, FastAPI (for potential future API expansion)
*   **Database:** PostgreSQL (Neon) with `pgvector` extension for hybrid (SQL + Vector) search.
*   **LLM Router:** FreeLLMAPI (Local Development) / OpenRouter (Production)
*   **Key Libraries:** `openai`, `sqlalchemy`, `pymupdf`, `pytesseract`, `ddgs` (for web search).

## 🚀 How to Run Locally

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/YOUR_USERNAME/kompass-advisor.git
    cd kompass-advisor
Set up a virtual environment:

bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
Install dependencies:

bash
pip install -r requirements.txt
Create a .env file in the project root and add your secrets:

env
DATABASE_URL="postgresql://neondb_owner:YOUR_ACTUAL_PASSWORD@ep-cool-name-123456.c-8.eu-central-1.aws.neon.tech/neondb?sslmode=require"
LLM_API_KEY="your_freellmapi_or_provider_key"
LLM_BASE_URL="http://127.0.0.1:31415/v1"
Initialize the database (first time only):

bash
python -c "from database import engine; import models; models.Base.metadata.create_all(bind=engine)"
Run the app:

bash
streamlit run app.py