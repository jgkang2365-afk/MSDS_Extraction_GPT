# -*- coding: utf-8 -*-
import os
import sys
import fitz

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

pdf_path = os.path.join("TEST_File", "040_Giemsa SDS.pdf")
doc = fitz.open(pdf_path)
for i in range(min(5, len(doc))):
    text = doc[i].get_text("text")
    print(f"\n================ Page {i+1} ================")
    print(text)
doc.close()
