import os
import asyncio
from pypdf import PdfReader
from docx import Document
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY not found in environment variables.")
    exit(1)

genai.configure(api_key=api_key)

DOCU_DIR = r"d:\GEMINI-DEV\STAR-DOC-W\DOCU"
PLANTILLAS_DIR = r"d:\GEMINI-DEV\STAR-DOC-W\plantillas"
os.makedirs(PLANTILLAS_DIR, exist_ok=True)

model = genai.GenerativeModel('gemini-2.0-flash')

async def process_pdf(filename):
    pdf_path = os.path.join(DOCU_DIR, filename)
    print(f"Processing {filename}...")
    
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
            
        if not text.strip():
            print(f"⚠️ Warning: No text extracted from {filename}. It might be an image PDF.")
            return

        # Prompt for Gemini
        prompt = f"""
        ACT AS AN EXPERT LEGAL ENGINEER.
        You are converting a static legal document into a dynamic Jinja2 template.

        INSTRUCTIONS:
        1. Read the following legal text carefully.
        2. Identify ALL placeholders (underscores like ______, dots like ......, or bracketed text like [NOMBRE]).
        3. Replace them with appropriate Jinja2 variables in snake_case (e.g., {{ nombre_arrendatario }}, {{ fecha_inicio }}).
        4. Maintain the rest of the text EXACTLY as is. Do not summarize or change legal wording.
        5. Return ONLY the converted text. Do not add markdown code blocks or explanations.

        TEXT TO CONVERT:
        {text[:8000]}  # Limit context window just in case
        """

        response = model.generate_content(prompt)
        converted_text = response.text

        # Create DOCX
        doc = Document()
        # Simple approach: add paragraph by paragraph
        for line in converted_text.split('\n'):
            if line.strip():
                doc.add_paragraph(line)

        output_filename = filename.replace('.pdf', '.docx')
        output_path = os.path.join(PLANTILLAS_DIR, output_filename)
        doc.save(output_path)
        print(f"✅ Created {output_filename}")

    except Exception as e:
        print(f"❌ Error processing {filename}: {e}")

async def main():
    if not os.path.exists(DOCU_DIR):
        print(f"❌ Error: Directory {DOCU_DIR} does not exist.")
        return

    files = [f for f in os.listdir(DOCU_DIR) if f.lower().endswith('.pdf')]
    print(f"📂 Found {len(files)} PDF files in {DOCU_DIR}")
    
    if not files:
        print("⚠️ No PDFs found. Please check the directory path.")
        return

    for file in files:
        await process_pdf(file)
        # Rate limit protection (simple)
        await asyncio.sleep(4) 

if __name__ == "__main__":
    asyncio.run(main())
