import os
from pypdf import PdfReader

DOCU_DIR = r"d:\GEMINI-DEV\STAR-DOC-W\DOCU"
TEMP_DIR = r"d:\GEMINI-DEV\STAR-DOC-W\temp_text"
os.makedirs(TEMP_DIR, exist_ok=True)

for filename in os.listdir(DOCU_DIR):
    if filename.lower().endswith('.pdf'):
        try:
            reader = PdfReader(os.path.join(DOCU_DIR, filename))
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            
            txt_filename = filename.replace('.pdf', '.txt')
            with open(os.path.join(TEMP_DIR, txt_filename), 'w', encoding='utf-8') as f:
                f.write(text)
            print(f"Extracted: {txt_filename}")
        except Exception as e:
            print(f"Error extracting {filename}: {e}")
