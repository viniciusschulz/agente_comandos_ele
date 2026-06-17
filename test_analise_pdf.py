"""
Prova de Conceito: Análise de Diagrama Elétrico via PDF + Gemini Vision
========================================================================
Extrai páginas do PDF como imagens de alta resolução usando PyMuPDF (fitz),
e envia ao Gemini para interpretação do diagrama elétrico.
"""
import os
import sys
import json
import io
import base64

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Adicionar o diretório do projeto para importar .env
sys.path.insert(0, r"C:\agente-diretrizes")
from dotenv import load_dotenv
load_dotenv(r"C:\agente-diretrizes\.env")

import fitz  # PyMuPDF
from PIL import Image
import google.generativeai as genai

# Configurar Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("ERRO: GEMINI_API_KEY não encontrada no .env")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

PDF_PATH = r"C:\RAG-circuitos elétricos\projeto-aquecedor-placa.pdf"
OUTPUT_DIR = r"C:\RAG-circuitos elétricos\output_paginas"

def extrair_paginas_como_imagem(pdf_path, output_dir, dpi=200, max_pages=5):
    """Extrai as primeiras N páginas do PDF como imagens PNG de alta resolução."""
    os.makedirs(output_dir, exist_ok=True)
    
    doc = fitz.open(pdf_path)
    total_paginas = len(doc)
    paginas_a_processar = min(total_paginas, max_pages)
    
    print(f"PDF: {os.path.basename(pdf_path)}")
    print(f"Total de páginas: {total_paginas}")
    print(f"Processando primeiras {paginas_a_processar} páginas em {dpi} DPI...\n")
    
    imagens_salvas = []
    zoom = dpi / 72  # fitz usa 72 DPI como base
    matrix = fitz.Matrix(zoom, zoom)
    
    for i in range(paginas_a_processar):
        page = doc[i]
        pix = page.get_pixmap(matrix=matrix)
        
        img_path = os.path.join(output_dir, f"pagina_{i+1:03d}.png")
        pix.save(img_path)
        
        # Tamanho da imagem
        w, h = pix.width, pix.height
        size_mb = os.path.getsize(img_path) / (1024 * 1024)
        
        print(f"  Página {i+1}/{paginas_a_processar}: {w}x{h}px ({size_mb:.2f} MB) -> {img_path}")
        imagens_salvas.append(img_path)
    
    doc.close()
    return imagens_salvas, total_paginas


def analisar_com_gemini(imagem_path, numero_pagina):
    """Envia uma imagem de diagrama elétrico ao Gemini e obtém interpretação."""
    
    # Carregar imagem
    img = Image.open(imagem_path)
    
    prompt = f"""Você é um engenheiro eletricista experiente especializado em leitura e interpretação de diagramas elétricos industriais (esquemas de força, comando e controle).

Analise esta imagem que é a **Página {numero_pagina}** de um projeto de diagrama elétrico industrial (projeto de aquecedor de placas).

Por favor, forneça uma análise estruturada contendo:

## 1. Tipo de Diagrama
Identifique o tipo desta folha (ex: Diagrama Unifilar, Diagrama Trifilar de Força, Diagrama de Comando, Lista de Cabos, Legenda, Capa do Projeto, etc.)

## 2. Componentes Identificados
Liste todos os componentes elétricos visíveis com seus respectivos rótulos/tags (ex: -Q1 Disjuntor, -K1 Contator, -F1 Relé Térmico, etc.). Apresente em formato de tabela:
| Tag | Tipo de Componente | Descrição/Função |

## 3. Lógica de Funcionamento
Explique a lógica do circuito representado, descrevendo passo a passo o que acontece quando o sistema é energizado ou operado.

## 4. Informações da Legenda/Carimbo
Se visível, extraia: nome do projeto, número do desenho, revisão, cliente, data, escala, e quaisquer notas.

## 5. Observações de Segurança
Mencione se existem dispositivos de proteção visíveis (disjuntores, fusíveis, relés térmicos, DPS, etc.) e se nota alguma irregularidade ou item faltante do ponto de vista normativo (NR-10, NBR 5410, IEC).

Responda em **português brasileiro**. Seja detalhado e técnico.
"""
    
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    print(f"\n  Enviando página {numero_pagina} ao Gemini para análise...")
    response = model.generate_content([prompt, img])
    
    return response.text


def main():
    print("=" * 70)
    print("AGENTE DE INTERPRETAÇÃO DE DIAGRAMAS ELÉTRICOS - Prova de Conceito")
    print("=" * 70)
    print()
    
    # 1. Extrair páginas como imagens
    imagens, total = extrair_paginas_como_imagem(PDF_PATH, OUTPUT_DIR, dpi=200, max_pages=3)
    
    if not imagens:
        print("Nenhuma imagem extraída. Verifique o PDF.")
        return
    
    # 2. Analisar a primeira página com Gemini
    print("\n" + "=" * 70)
    print("ANÁLISE COM IA (Gemini 2.0 Flash)")
    print("=" * 70)
    
    resultados = []
    
    for i, img_path in enumerate(imagens):
        pagina_num = i + 1
        print(f"\n{'─' * 50}")
        print(f"Analisando Página {pagina_num}...")
        print(f"{'─' * 50}")
        
        try:
            analise = analisar_com_gemini(img_path, pagina_num)
            print(f"\n{analise}")
            
            resultados.append({
                "pagina": pagina_num,
                "imagem": img_path,
                "analise": analise
            })
        except Exception as e:
            print(f"  ERRO ao analisar página {pagina_num}: {e}")
            resultados.append({
                "pagina": pagina_num,
                "imagem": img_path,
                "analise": f"ERRO: {str(e)}"
            })
    
    # 3. Salvar resultados em JSON
    resultado_path = os.path.join(OUTPUT_DIR, "resultado_analise.json")
    with open(resultado_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'=' * 70}")
    print(f"Análise completa! {len(resultados)} páginas processadas.")
    print(f"Resultados salvos em: {resultado_path}")
    print(f"Total de páginas no PDF: {total}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
