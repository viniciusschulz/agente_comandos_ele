import sys
sys.stdout.reconfigure(encoding='utf-8')

"""
Módulo de processamento de arquivos CAD/PDF para extração de páginas como imagens.
Suporta PDF (via PyMuPDF) e DWG (placeholder para suporte futuro).
"""

import io
import logging
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)


def processar_pdf(pdf_bytes: bytes, dpi: int = 200) -> list[dict]:
    """
    Extrai páginas de um PDF como imagens PIL em alta resolução.

    Args:
        pdf_bytes: Conteúdo do arquivo PDF em bytes.
        dpi: Resolução de renderização em DPI (padrão: 200).

    Returns:
        Lista de dicts com:
            - page_num (int): Número da página (1-indexed).
            - image (PIL.Image): Imagem renderizada da página.
            - text_content (str): Texto extraído da página.

    Raises:
        ValueError: Se o PDF estiver vazio ou corrompido.
    """
    if not pdf_bytes:
        raise ValueError("O conteúdo do PDF está vazio.")

    paginas = []

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.error("Erro ao abrir o PDF: %s", e)
        raise ValueError(f"Não foi possível abrir o PDF: {e}") from e

    total_paginas = len(doc)
    logger.info("PDF aberto com sucesso — %d página(s) encontrada(s).", total_paginas)

    if total_paginas == 0:
        doc.close()
        raise ValueError("O PDF não contém nenhuma página.")

    # Fator de escala: 72 DPI é o padrão do PDF
    zoom = dpi / 72.0
    matriz = fitz.Matrix(zoom, zoom)

    for idx in range(total_paginas):
        page = doc[idx]
        page_num = idx + 1

        try:
            # Renderizar página como pixmap (imagem raster)
            pixmap = page.get_pixmap(matrix=matriz, alpha=False)

            # Converter pixmap para PIL.Image
            img_data = pixmap.tobytes("png")
            image = Image.open(io.BytesIO(img_data))

            # Extrair texto da página
            text_content = page.get_text("text").strip()

            paginas.append({
                "page_num": page_num,
                "image": image,
                "text_content": text_content,
            })

            logger.info(
                "Página %d/%d processada — dimensões: %dx%d, texto: %d caracteres.",
                page_num,
                total_paginas,
                image.width,
                image.height,
                len(text_content),
            )

        except Exception as e:
            logger.error("Erro ao processar página %d: %s", page_num, e)
            paginas.append({
                "page_num": page_num,
                "image": None,
                "text_content": "",
                "error": str(e),
            })

    doc.close()
    logger.info("Processamento do PDF concluído — %d página(s) extraída(s).", len(paginas))
    return paginas


def processar_dwg(dwg_bytes: bytes) -> list[dict]:
    """
    Placeholder para processamento de arquivos DWG.

    O suporte nativo a DWG requer o ODA File Converter (Open Design Alliance)
    para converter DWG → PDF antes do processamento.

    Args:
        dwg_bytes: Conteúdo do arquivo DWG em bytes.

    Returns:
        Lista com um único dict informando a necessidade do conversor ODA.
    """
    logger.warning("Tentativa de processar arquivo DWG — funcionalidade ainda não implementada.")

    return [{
        "page_num": 0,
        "image": None,
        "text_content": "",
        "error": (
            "O processamento de arquivos DWG ainda não está disponível. "
            "É necessário instalar o ODA File Converter "
            "(https://www.opendesign.com/guestfiles/oda_file_converter) "
            "para converter DWG → PDF antes da análise. "
            "Por enquanto, exporte o arquivo como PDF no AutoCAD e envie o PDF."
        ),
    }]


def detectar_tipo_arquivo(filename: str) -> Optional[str]:
    """
    Detecta o tipo de arquivo com base na extensão.

    Args:
        filename: Nome do arquivo.

    Returns:
        'pdf', 'dwg' ou None se não suportado.
    """
    if not filename:
        return None

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        return "pdf"
    elif ext == "dwg":
        return "dwg"
    else:
        return None
