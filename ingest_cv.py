import pymupdf
import pytesseract
from PIL import Image
import io
import json
import os
from openai import OpenAI
from dotenv import load_dotenv
from database import SessionLocal, engine
import models

load_dotenv()
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)

def extract_text_from_pdf(pdf_path):
    doc = pymupdf.open(pdf_path)
    text = ""
    for page in doc:
        page_text = page.get_text()
        if not page_text.strip():
            pix = page.get_pixmap()
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            page_text = pytesseract.image_to_string(img)
        text += page_text + "\n"
    doc.close()
    return text

def structure_cv_with_llm(raw_text):
    prompt = f"""
    Extract the CV information into this exact JSON schema. Do not invent facts.
    SCHEMA:
    {{
      "name": "string",
      "education": [{{"degree": "string", "institution": "string", "year": "string", "grade": "string"}}],
      "skills": ["string"],
      "experience": [{{"role": "string", "company": "string", "duration": "string", "description": "string"}}]
    }}
    CV TEXT: {raw_text[:5000]}
    """
    response = client.chat.completions.create(model="auto", messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content

if __name__ == "__main__":
    sample_pdf = "sample_cv.pdf" 
    
    if os.path.exists(sample_pdf):
        print("📄 Extracting text...")
        raw_text = extract_text_from_pdf(sample_pdf)
        
        print("🧠 Structuring with AI...")
        json_str = structure_cv_with_llm(raw_text)
        
        # Clean up potential markdown code blocks from the AI output
        json_str = json_str.replace("```json", "").replace("```", "").strip()
        
        try:
            profile_data = json.loads(json_str)
            name = profile_data.get("name", "Unknown Student")
            
            db = SessionLocal()
            new_profile = models.StudentProfile(name=name, profile_json=json_str)
            db.add(new_profile)
            db.commit()
            db.close()
            
            print(f"✅ Successfully saved profile for {name} to the database!")
            
        except Exception as e:
            print(f"❌ Error saving to DB: {e}")
            print("Raw AI Output:", json_str)
    else:
        print("❌ Please ensure sample_cv.pdf is in the folder.")