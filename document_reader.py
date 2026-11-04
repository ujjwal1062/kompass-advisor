import pymupdf  # CHANGED: Use the new library name instead of 'fitz'
import pytesseract
from PIL import Image
import io
import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)

# --- WINDOWS TESSERACT FIX ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def extract_text_from_pdf(pdf_path):
    """Extracts text. If the PDF is scanned (no text), it uses OCR."""
    print(f"📄 Reading: {pdf_path}")
    # CHANGED: Use pymupdf.open instead of fitz.open
    doc = pymupdf.open(pdf_path) 
    text = ""
    
    for page_num, page in enumerate(doc):
        page_text = page.get_text()
        
        # If the page has no text, it's likely a scanned image. Use OCR.
        if not page_text.strip():
            print(f"   [OCR]: Page {page_num+1} is an image. Running OCR...")
            pix = page.get_pixmap()
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            try:
                page_text = pytesseract.image_to_string(img)
            except Exception as e:
                print(f"   ⚠️ OCR Failed: {e}. Is Tesseract installed?")
            
        text += page_text + "\n"
        
    doc.close()
    return text

def structure_cv_with_llm(raw_text):
    """Uses the LLM to convert messy CV text into clean JSON."""
    print("🧠 Structuring data with AI...")
    
    prompt = f"""
    You are an expert data extractor. Read the following CV/Resume text.
    Extract the information into this exact JSON schema. Do not invent facts.
    If a field is missing, use null.
    
    SCHEMA:
    {{
      "name": "string",
      "education": [
        {{"degree": "string", "institution": "string", "year": "string", "grade": "string"}}
      ],
      "skills": ["string"],
      "experience": [
        {{"role": "string", "company": "string", "duration": "string", "description": "string"}}
      ]
    }}
    
    CV TEXT:
    {raw_text[:5000]} 
    """
    
    response = client.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

if __name__ == "__main__":
    # The script will look for this file in your current folder
    sample_pdf = r"sample_cv.pdf" 
    
    if os.path.exists(sample_pdf):
        raw_text = extract_text_from_pdf(sample_pdf)
        print("\n--- RAW TEXT PREVIEW ---")
        print(raw_text[:500])
        
        structured_json = structure_cv_with_llm(raw_text)
        print("\n--- STRUCTURED JSON PROFILE ---")
        print(structured_json)
    else:
        print(f"❌ Error: Cannot find '{sample_pdf}'. Please put a PDF file in this folder and rename it to sample_cv.pdf.")