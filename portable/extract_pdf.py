import pdfplumber  

input_folder = "Input"  
file_name = r"1A40E01000068B8000023979-1.pdf".replace("/", "\\") 
output_filename = r"Gold Drop - Liquid Loud Diamond Sauce-(g).txt" 

# Open PDF and extract all text in one call  
with pdfplumber.open(f"{input_folder}\\{file_name}") as pdoc:    
    # Extract from first page (update this if you need ALL pages later)
    raw_page_text = pdoc.pages[0].extract_text() or ""

    cleaned_text = " ".join(raw_page_text.split()).strip()  

# Write extracted text to file  
with open(output_filename, 'w', encoding='utf-8') as f_out:    
     if len(cleaned_text.strip()):       
         for line in [f"[Page 1]\n{cleaned_text}\n\n"]:      
             f_out.write(line) 

print("[✅] Extraction complete!")
