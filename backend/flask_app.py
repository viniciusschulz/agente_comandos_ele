import sys
sys.stdout.reconfigure(encoding='utf-8')

from flask import Flask, request, jsonify
from flask_cors import CORS
from pathlib import Path
import os, time, uuid, threading, base64, io
from dotenv import load_dotenv

from cad_agent import analisar_documento_completo
from cad_processor import detectar_tipo_arquivo, processar_dwg, processar_pdf

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

app = Flask(__name__)
CORS(app)

UPLOAD_DIR = Path(__file__).resolve().parent / "temp_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
jobs = {}

@app.route('/api/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file: return jsonify({"erro": "Nenhum arquivo"}), 400
    
    filename = file.filename
    file_type = detectar_tipo_arquivo(filename)
    if not file_type: return jsonify({"erro": "Nao suportado"}), 400
    
    file_bytes = file.read()
    job_id = str(uuid.uuid4())
    safe_filename = f"{job_id}_{filename}"
    file_path = UPLOAD_DIR / safe_filename
    
    with open(file_path, "wb") as f:
        f.write(file_bytes)
        
    jobs[job_id] = {
        "job_id": job_id, "status": "uploaded", "filename": filename,
        "file_type": file_type, "file_path": str(file_path),
        "created_at": time.time(), "result": None, "error": None
    }
    return jsonify({"job_id": job_id, "status": "uploaded"}), 201

@app.route('/api/status/<job_id>', methods=['GET'])
def status(job_id):
    job = jobs.get(job_id)
    if not job: return jsonify({"erro": "Not found"}), 404
    
    resp = {
        "job_id": job_id, "status": job["status"], 
        "result": job.get("result"), "error": job.get("error")
    }
    
    if job["status"] == "completed" and job.get("result"):
        resp["resultado"] = job["result"] # maintain compatibility with frontend app.js
        
    return jsonify(resp)

def run_analysis(job_id, max_pages):
    job = jobs[job_id]
    job["status"] = "processing"
    job["started_at"] = time.time()
    try:
        with open(job["file_path"], "rb") as f:
            file_bytes = f.read()
            
        paginas = processar_pdf(file_bytes) if job["file_type"] == "pdf" else processar_dwg(file_bytes)
        
        # Se max_pages for 0, processar todas as páginas
        if max_pages <= 0:
            max_pages = len(paginas)
            
        resultado = analisar_documento_completo(paginas=paginas, max_pages=max_pages, project_context="")
        
        # Inject images
        for i, analise in enumerate(resultado.get("analises", [])):
            if i < len(paginas) and paginas[i].get("image"):
                buffer = io.BytesIO()
                paginas[i]["image"].save(buffer, format="PNG")
                analise["image_base64"] = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        job["status"] = "completed"
        job["result"] = resultado
        job["completed_at"] = time.time()
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)

@app.route('/api/analyze', methods=['POST'])
def analyze():
    body = request.get_json()
    job_id = body.get("job_id")
    max_pages = body.get("max_pages", 5)
    
    if job_id not in jobs: return jsonify({"erro": "Not found"}), 404
    
    if jobs[job_id]["status"] == "processing":
        return jsonify({"job_id": job_id, "status": "processing"}), 202
        
    # Run in background
    thread = threading.Thread(target=run_analysis, args=(job_id, int(max_pages)))
    thread.start()
    return jsonify({"job_id": job_id, "status": "processing"}), 202

if __name__ == '__main__':
    app.run(port=7071)
