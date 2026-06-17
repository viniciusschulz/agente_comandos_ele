import sys
sys.stdout.reconfigure(encoding='utf-8')

"""
Azure Function App — Backend do Agente de Análise de Diagramas Elétricos.

Endpoints:
    POST /api/upload   — Upload de arquivo PDF/DWG, retorna job_id.
    POST /api/analyze  — Executa análise com Gemini, retorna resultados.
    GET  /api/status   — Consulta status de um job.
"""

import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path

import azure.functions as func
from dotenv import load_dotenv

from cad_agent import analisar_documento_completo
from cad_processor import detectar_tipo_arquivo, processar_dwg, processar_pdf

# Carregar .env da raiz do projeto (um nível acima de backend/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ────────────────────────────────────────────
# Diretório temporário para uploads
# ────────────────────────────────────────────
UPLOAD_DIR = Path(__file__).resolve().parent / "temp_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ────────────────────────────────────────────
# Armazenamento em memória dos jobs
# (em produção, usar Azure Table Storage / Cosmos)
# ────────────────────────────────────────────
jobs: dict[str, dict] = {}

# ────────────────────────────────────────────
# Azure Function App com CORS
# ────────────────────────────────────────────
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def _cors_headers() -> dict[str, str]:
    """Retorna headers CORS para desenvolvimento local."""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "86400",
    }


def _json_response(body: dict, status_code: int = 200) -> func.HttpResponse:
    """Helper para criar respostas JSON com CORS."""
    return func.HttpResponse(
        body=json.dumps(body, ensure_ascii=False, indent=2),
        status_code=status_code,
        mimetype="application/json",
        headers=_cors_headers(),
    )


def _options_response() -> func.HttpResponse:
    """Resposta para preflight CORS (OPTIONS)."""
    return func.HttpResponse(
        status_code=204,
        headers=_cors_headers(),
    )


# ────────────────────────────────────────────
# POST /api/upload
# ────────────────────────────────────────────
@app.route(route="upload", methods=["POST", "OPTIONS"])
def upload(req: func.HttpRequest) -> func.HttpResponse:
    """
    Recebe upload de arquivo PDF ou DWG via multipart/form-data.
    Salva em diretório temporário e retorna um job_id.

    Form field esperado: 'file'
    """
    # Preflight CORS
    if req.method == "OPTIONS":
        return _options_response()

    logger.info("Recebida requisição de upload.")

    try:
        # Obter arquivo do form-data
        file = req.files.get("file")
        if not file:
            return _json_response(
                {"erro": "Nenhum arquivo enviado. Use o campo 'file' no form-data."},
                status_code=400,
            )

        filename = file.filename or "arquivo_sem_nome"
        file_type = detectar_tipo_arquivo(filename)

        if file_type is None:
            return _json_response(
                {
                    "erro": f"Tipo de arquivo não suportado: '{filename}'. "
                    "Envie um arquivo PDF ou DWG."
                },
                status_code=400,
            )

        # Ler conteúdo do arquivo
        file_bytes = file.read()
        file_size = len(file_bytes)

        if file_size == 0:
            return _json_response(
                {"erro": "O arquivo enviado está vazio."},
                status_code=400,
            )

        # Gerar job_id e salvar arquivo
        job_id = str(uuid.uuid4())
        safe_filename = f"{job_id}_{filename}"
        file_path = UPLOAD_DIR / safe_filename

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # Registrar job
        jobs[job_id] = {
            "job_id": job_id,
            "status": "uploaded",
            "filename": filename,
            "file_type": file_type,
            "file_size_bytes": file_size,
            "file_path": str(file_path),
            "created_at": time.time(),
            "result": None,
            "error": None,
        }

        logger.info(
            "Upload concluído — job_id: %s, arquivo: %s (%d bytes).",
            job_id,
            filename,
            file_size,
        )

        return _json_response(
            {
                "job_id": job_id,
                "status": "uploaded",
                "filename": filename,
                "file_type": file_type,
                "file_size_bytes": file_size,
                "mensagem": "Arquivo recebido com sucesso. Use POST /api/analyze para iniciar a análise.",
            },
            status_code=201,
        )

    except Exception as e:
        logger.error("Erro no upload: %s", e, exc_info=True)
        return _json_response(
            {"erro": f"Erro interno no upload: {e}"},
            status_code=500,
        )


# ────────────────────────────────────────────
# POST /api/analyze
# ────────────────────────────────────────────
def run_analysis_background(job_id: str, max_pages: int, project_context: str):
    import io
    import base64
    job = jobs[job_id]
    try:
        file_path = job.get("file_path")
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        file_type = job.get("file_type", "pdf")
        
        if file_type == "pdf":
            logger.info("Processando PDF: %s", job["filename"])
            paginas = processar_pdf(file_bytes)
        else:
            logger.info("Processando DWG: %s", job["filename"])
            paginas = processar_dwg(file_bytes)

        if max_pages <= 0:
            max_pages = len(paginas)

        logger.info("Iniciando análise com Gemini — %d página(s), limite: %d.", len(paginas), max_pages)

        resultado = analisar_documento_completo(
            paginas=paginas,
            max_pages=max_pages,
            project_context=project_context,
        )

        # Inject base64 images into the result so the frontend can display them
        for i, analise in enumerate(resultado.get("analises", [])):
            if i < len(paginas) and paginas[i].get("image"):
                buffer = io.BytesIO()
                paginas[i]["image"].save(buffer, format="PNG")
                analise["image_base64"] = base64.b64encode(buffer.getvalue()).decode("utf-8")

        job["status"] = "completed"
        job["completed_at"] = time.time()
        job["result"] = resultado
        duracao = job["completed_at"] - job["started_at"]
        logger.info("Análise concluída em %.1f segundos — job_id: %s", duracao, job_id)
        
    except Exception as e:
        logger.error("Erro na análise em background: %s", e, exc_info=True)
        job["status"] = "error"
        job["error"] = str(e)


@app.route(route="analyze", methods=["POST", "OPTIONS"])
def analyze(req: func.HttpRequest) -> func.HttpResponse:
    """
    Inicia a pipeline de análise para um job_id existente em background.
    """
    if req.method == "OPTIONS":
        return _options_response()

    logger.info("Recebida requisição de análise.")

    try:
        try:
            body = req.get_json()
        except ValueError:
            return _json_response({"erro": "Body da requisição deve ser JSON válido."}, status_code=400)

        job_id = body.get("job_id")
        max_pages = body.get("max_pages", 5)
        project_context = body.get("project_context", "")

        if not job_id:
            return _json_response({"erro": "O campo 'job_id' é obrigatório."}, status_code=400)

        if not isinstance(max_pages, int):
            max_pages = 5
        
        job = jobs.get(job_id)
        if not job:
            return _json_response({"erro": f"Job não encontrado: {job_id}"}, status_code=404)

        if job["status"] == "processing":
            return _json_response({
                "job_id": job_id,
                "status": "processing",
                "mensagem": "A análise já está em andamento. Consulte GET /api/status/{job_id}.",
            }, status_code=202)

        file_path = job.get("file_path")
        if not file_path or not os.path.exists(file_path):
            job["status"] = "error"
            job["error"] = "Arquivo não encontrado no servidor."
            return _json_response({"erro": "Arquivo não encontrado. Faça o upload novamente."}, status_code=404)

        job["status"] = "processing"
        job["started_at"] = time.time()

        import threading
        thread = threading.Thread(
            target=run_analysis_background,
            args=(job_id, max_pages, project_context)
        )
        thread.start()

        return _json_response({
            "job_id": job_id,
            "status": "processing",
            "mensagem": "Análise iniciada em background.",
        }, status_code=202)

    except Exception as e:
        logger.error("Erro ao iniciar análise: %s", e, exc_info=True)
        return _json_response({"erro": f"Erro interno: {e}"}, status_code=500)


# ────────────────────────────────────────────
# GET /api/status/{job_id}
# ────────────────────────────────────────────
@app.route(route="status/{job_id}", methods=["GET", "OPTIONS"])
def status(req: func.HttpRequest) -> func.HttpResponse:
    """
    Retorna o status atual de um job de análise.

    Path parameter: job_id
    """
    # Preflight CORS
    if req.method == "OPTIONS":
        return _options_response()

    job_id = req.route_params.get("job_id")

    if not job_id:
        return _json_response(
            {"erro": "O parâmetro 'job_id' é obrigatório na URL."},
            status_code=400,
        )

    job = jobs.get(job_id)
    if not job:
        return _json_response(
            {"erro": f"Job não encontrado: {job_id}"},
            status_code=404,
        )

    # Montar resposta de status (sem incluir o resultado completo)
    response_body = {
        "job_id": job_id,
        "status": job["status"],
        "filename": job.get("filename"),
        "file_type": job.get("file_type"),
        "file_size_bytes": job.get("file_size_bytes"),
        "created_at": job.get("created_at"),
    }

    if job.get("started_at"):
        response_body["started_at"] = job["started_at"]

    if job.get("completed_at"):
        response_body["completed_at"] = job["completed_at"]
        response_body["duracao_segundos"] = round(
            job["completed_at"] - job["started_at"], 2
        )

    if job["status"] == "error":
        response_body["erro"] = job.get("error")

    if job["status"] == "completed" and job.get("result"):
        response_body["resultado"] = job["result"]

    return _json_response(response_body)
