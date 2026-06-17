import json, sys
sys.stdout.reconfigure(encoding='utf-8')
data = json.load(open(r'C:\RAG-circuitos elétricos\output_paginas\resultado_analise.json', encoding='utf-8'))
for d in data:
    print(f"=== PAGINA {d['pagina']} ===")
    print(d['analise'])
    print("\n" + "="*60 + "\n")
