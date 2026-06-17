import sys
sys.stdout.reconfigure(encoding='utf-8')

"""
Agente de IA para análise de diagramas elétricos usando Gemini 2.5 Flash.
Utiliza o SDK google.genai (novo) para enviar imagens e obter análises estruturadas.
"""

import io
import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

# Modelo a ser utilizado
MODELO_GEMINI = "gemini-2.5-flash"

# Prompt de análise especializada em engenharia elétrica (Português)
PROMPT_ANALISE_PAGINA = """Você é um engenheiro eletricista sênior especializado em análise de diagramas elétricos industriais e prediais.

Analise a imagem desta página ({page_num} de {total_pages}) de um projeto elétrico.
{project_context}

Forneça uma análise técnica detalhada em formato JSON com a seguinte estrutura:

{{
    "pagina": {page_num},
    "tipo_diagrama": "Identifique o tipo: unifilar, multifilar, trifilar, funcional, diagrama de blocos, quadro de cargas, planta baixa elétrica, diagrama ladder, esquema de comando, etc.",
    "descricao_geral": "Descrição resumida do conteúdo da página.",
    "componentes_identificados": [
        {{
            "simbolo": "Símbolo ou referência no diagrama",
            "descricao": "Nome/descrição do componente",
            "tipo": "Tipo: disjuntor, contator, relé, transformador, motor, cabo, barramento, etc.",
            "especificacao": "Especificações técnicas visíveis (corrente, tensão, potência, seção do cabo, etc.)",
            "quantidade": "Quantidade identificada"
        }}
    ],
    "logica_funcionamento": "Explique a lógica de funcionamento do circuito, sequência de operação, intertravamentos, proteções, etc.",
    "legenda_carimbo": {{
        "titulo_projeto": "Título do projeto se visível",
        "numero_desenho": "Número do desenho/prancha",
        "revisao": "Revisão do documento",
        "responsavel_tecnico": "Nome do responsável técnico / engenheiro",
        "empresa": "Empresa responsável",
        "data": "Data do documento",
        "escala": "Escala utilizada",
        "outras_info": "Outras informações relevantes da legenda"
    }},
    "normas_seguranca": {{
        "nr10": "Observações relevantes à NR-10 (Segurança em Instalações e Serviços em Eletricidade)",
        "nbr5410": "Observações relevantes à NBR 5410 (Instalações Elétricas de Baixa Tensão)",
        "iec": "Observações relevantes a normas IEC aplicáveis",
        "outras_normas": "Outras normas identificadas ou aplicáveis"
    }},
    "observacoes_adicionais": "Qualquer observação adicional relevante, alertas, inconsistências ou pontos de atenção."
}}

IMPORTANTE:
- Retorne APENAS o JSON, sem markdown, sem blocos de código, sem texto adicional.
- Se algum campo não puder ser identificado, use "Não identificado" ou lista vazia.
- Seja preciso nas especificações técnicas.
- Identifique todos os componentes visíveis na imagem.
"""


def _obter_client() -> genai.Client:
    """
    Inicializa e retorna o cliente Gemini.

    Raises:
        EnvironmentError: Se a chave GEMINI_API_KEY não estiver configurada.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "A variável de ambiente GEMINI_API_KEY não está configurada. "
            "Defina-a no arquivo .env ou nas configurações do Azure Functions."
        )
    return genai.Client(api_key=api_key)


def _imagem_para_bytes(image: Image.Image) -> bytes:
    """Converte uma PIL.Image para bytes PNG."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _limpar_resposta_json(texto: str) -> dict:
    """
    Limpa e parseia a resposta do modelo, removendo possíveis
    marcadores de bloco de código markdown.
    """
    texto = texto.strip()

    # Remover blocos de código markdown se presentes
    if texto.startswith("```"):
        linhas = texto.split("\n")
        # Remover primeira linha (```json ou ```)
        linhas = linhas[1:]
        # Remover última linha (```)
        if linhas and linhas[-1].strip() == "```":
            linhas = linhas[:-1]
        texto = "\n".join(linhas).strip()

    try:
        return json.loads(texto)
    except json.JSONDecodeError as e:
        logger.warning("Resposta não é JSON válido, retornando como texto: %s", e)
        return {
            "resposta_raw": texto,
            "erro_parse": f"A resposta do modelo não é JSON válido: {e}",
        }


def analisar_pagina(
    image: Image.Image,
    page_num: int,
    total_pages: int,
    project_context: str = "",
) -> dict:
    """
    Envia uma imagem de página ao Gemini para análise técnica de diagrama elétrico.

    Args:
        image: Imagem da página como PIL.Image.
        page_num: Número da página (1-indexed).
        total_pages: Total de páginas no documento.
        project_context: Contexto adicional do projeto (opcional).

    Returns:
        Dict com a análise estruturada da página.
    """
    logger.info("Analisando página %d/%d com Gemini (%s)...", page_num, total_pages, MODELO_GEMINI)

    try:
        client = _obter_client()

        # Preparar o prompt com as variáveis
        contexto = f"\nContexto do projeto: {project_context}" if project_context else ""
        prompt_formatado = PROMPT_ANALISE_PAGINA.format(
            page_num=page_num,
            total_pages=total_pages,
            project_context=contexto,
        )

        # Converter imagem para bytes e criar Part
        img_bytes = _imagem_para_bytes(image)
        image_part = types.Part.from_bytes(data=img_bytes, mime_type="image/png")

        # Enviar para o Gemini
        response = client.models.generate_content(
            model=MODELO_GEMINI,
            contents=[image_part, prompt_formatado],
        )

        # Processar resposta
        resultado = _limpar_resposta_json(response.text)
        resultado["status"] = "sucesso"
        resultado["modelo_utilizado"] = MODELO_GEMINI

        logger.info("Página %d analisada com sucesso.", page_num)
        return resultado

    except EnvironmentError:
        raise
    except Exception as e:
        logger.error("Erro ao analisar página %d: %s", page_num, e)
        return {
            "pagina": page_num,
            "status": "erro",
            "erro": str(e),
            "modelo_utilizado": MODELO_GEMINI,
        }


def analisar_documento_completo(
    paginas: list[dict],
    max_pages: int = 5,
    project_context: str = "",
) -> dict:
    """
    Processa todas as páginas de um documento e retorna um relatório consolidado.

    Args:
        paginas: Lista de dicts retornada por processar_pdf() ou processar_dwg().
        max_pages: Número máximo de páginas a analisar (padrão: 5).
        project_context: Contexto adicional do projeto (opcional).

    Returns:
        Dict com o relatório consolidado de todas as páginas analisadas.
    """
    total_paginas = len(paginas)
    paginas_para_analisar = paginas[:max_pages]
    total_a_analisar = len(paginas_para_analisar)

    logger.info(
        "Iniciando análise completa: %d de %d páginas (limite: %d).",
        total_a_analisar,
        total_paginas,
        max_pages,
    )

    resultados_paginas = []
    paginas_com_erro = 0
    paginas_com_sucesso = 0

    for pagina_info in paginas_para_analisar:
        page_num = pagina_info.get("page_num", 0)
        image = pagina_info.get("image")

        # Verificar se a página tem erro de extração
        if pagina_info.get("error"):
            resultados_paginas.append({
                "pagina": page_num,
                "status": "erro_extracao",
                "erro": pagina_info["error"],
            })
            paginas_com_erro += 1
            continue

        # Verificar se a imagem está disponível
        if image is None:
            resultados_paginas.append({
                "pagina": page_num,
                "status": "erro",
                "erro": "Imagem da página não disponível.",
            })
            paginas_com_erro += 1
            continue

        # Analisar a página com o Gemini
        resultado = analisar_pagina(
            image=image,
            page_num=page_num,
            total_pages=total_paginas,
            project_context=project_context,
        )
        resultados_paginas.append(resultado)

        if resultado.get("status") == "sucesso":
            paginas_com_sucesso += 1
        else:
            paginas_com_erro += 1

    # Montar relatório consolidado
    relatorio = {
        "resumo": {
            "total_paginas_documento": total_paginas,
            "paginas_analisadas": total_a_analisar,
            "paginas_com_sucesso": paginas_com_sucesso,
            "paginas_com_erro": paginas_com_erro,
            "limite_paginas": max_pages,
            "modelo_utilizado": MODELO_GEMINI,
        },
        "analises": resultados_paginas,
    }

    logger.info(
        "Análise completa finalizada — %d sucesso, %d erros de %d páginas.",
        paginas_com_sucesso,
        paginas_com_erro,
        total_a_analisar,
    )

    return relatorio
