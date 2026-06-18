document.addEventListener('DOMContentLoaded', () => {
    // Configuração de API
    const API_BASE = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost' 
        ? 'http://localhost:7071/api' 
        : 'https://func-agente-comandos-ele.azurewebsites.net/api';

    // State Variables
    let currentJobId = null;
    let analysisResults = null;
    let currentPageIndex = 0;
    let pollInterval = null;
    let zoomLevel = 1;
    let isDraggingImage = false;
    let startPanX = 0, startPanY = 0;
    let currentPanX = 0, currentPanY = 0;

    // --- DOM Elements ---
    const stateUpload = document.getElementById('upload-state');
    const stateProcessing = document.getElementById('processing-state');
    const stateResults = document.getElementById('results-state');
    
    // Upload Elements
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const maxPagesSelect = document.getElementById('max-pages-select');
    
    // Processing Elements
    const procFileName = document.getElementById('processing-file-name');
    const analyzeCurrent = document.getElementById('analyze-current');
    const analyzeTotal = document.getElementById('analyze-total');
    const progressBarGlow = document.querySelector('.progress-bar-glow');
    const progressPercentage = document.getElementById('progress-percentage');
    
    // Results Elements
    const resFileName = document.getElementById('result-file-name');
    const resPageCount = document.getElementById('result-page-count');
    const btnNewAnalysis = document.getElementById('btn-new-analysis');
    const btnExport = document.getElementById('btn-export');
    
    // Viewer Elements
    const pageImage = document.getElementById('page-image');
    const imageCanvas = document.getElementById('image-canvas');
    const imageViewport = document.getElementById('image-viewport');
    const btnPrevPage = document.getElementById('btn-prev-page');
    const btnNextPage = document.getElementById('btn-next-page');
    const pageCurrent = document.getElementById('page-current');
    const pageTotal = document.getElementById('page-total');
    const pageThumbnails = document.getElementById('page-thumbnails');
    
    const btnZoomIn = document.getElementById('btn-zoom-in');
    const btnZoomOut = document.getElementById('btn-zoom-out');
    const btnZoomFit = document.getElementById('btn-zoom-fit');
    const zoomLevelText = document.getElementById('zoom-level');
    
    // Accordion & Content Elements
    const accordions = document.querySelectorAll('.accordion-item');
    const panelTabs = document.querySelectorAll('.panel-tab');
    const tabContents = document.querySelectorAll('.tab-content');

    // Load saved preferences
    const savedMaxPages = localStorage.getItem('cad_max_pages');
    if (savedMaxPages) maxPagesSelect.value = savedMaxPages;

    maxPagesSelect.addEventListener('change', () => {
        localStorage.setItem('cad_max_pages', maxPagesSelect.value);
    });

    // ==========================================
    // UPLOAD LOGIC
    // ==========================================
    dropZone.addEventListener('click', () => fileInput.click());
    
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-active');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-active');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-active');
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFileSelection(e.dataTransfer.files[0]);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
            handleFileSelection(e.target.files[0]);
            // Reseta o valor para permitir selecionar o mesmo arquivo novamente
            e.target.value = '';
        }
    });

    function handleFileSelection(file) {
        const validExtensions = ['.pdf', '.dwg', '.dxf'];
        const fileName = file.name.toLowerCase();
        const isValid = validExtensions.some(ext => fileName.endsWith(ext));
        
        if (!isValid) {
            showToast('Formato não suportado. Use PDF, DWG ou DXF.', 'error');
            return;
        }

        // DWG/DXF placeholder verification
        if (fileName.endsWith('.dwg') || fileName.endsWith('.dxf')) {
            showToast('Suporte a DWG/DXF em fase de testes. Tentando conversão...', 'warning');
        }

        uploadFile(file);
    }

    async function uploadFile(file) {
        changeState(stateProcessing);
        procFileName.textContent = file.name;
        resFileName.textContent = file.name;
        updateProgressStep(1, 'active');
        setProgressBar(5);

        const formData = new FormData();
        formData.append('file', file);
        formData.append('max_pages', maxPagesSelect.value);

        try {
            const response = await fetch(`${API_BASE}/upload`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) throw new Error(`Erro ${response.status}: Falha no upload`);

            const data = await response.json();
            currentJobId = data.job_id;
            
            // Trigger analysis
            const analyzeResponse = await fetch(`${API_BASE}/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_id: currentJobId,
                    max_pages: parseInt(maxPagesSelect.value)
                })
            });

            if (!analyzeResponse.ok) throw new Error('Erro ao iniciar análise');

            // Start polling
            pollInterval = setInterval(checkStatus, 2000);
            
        } catch (error) {
            console.error(error);
            showToast('Erro ao enviar arquivo para o servidor.', 'error');
            changeState(stateUpload);
        }
    }

    async function checkStatus() {
        if (!currentJobId) return;

        try {
            const response = await fetch(`${API_BASE}/status/${currentJobId}`);
            if (!response.ok) throw new Error('Erro ao consultar status');

            const data = await response.json();
            updateProcessingUI(data);

            if (data.status === 'completed') {
                clearInterval(pollInterval);
                analysisResults = data;
                renderResults(data);
                changeState(stateResults);
                showToast('Análise concluída com sucesso!', 'success');
            } else if (data.status === 'error') {
                clearInterval(pollInterval);
                showToast(`Erro na análise: ${data.message || 'Falha desconhecida'}`, 'error');
                changeState(stateUpload);
            }
        } catch (error) {
            console.error(error);
            // Don't kill polling on a single network error, just let it retry
        }
    }

    function updateProcessingUI(data) {
        if (data.status === 'processing') {
            updateProgressStep(1, 'completed');
            updateProgressStep(2, 'active');
            setProgressBar(50); // Indeterminate progress for simplified backend
        } else if (data.status === 'extracting') {
            updateProgressStep(1, 'completed');
            updateProgressStep(2, 'active');
            setProgressBar(25);
        } else if (data.status === 'analyzing') {
            updateProgressStep(2, 'completed');
            updateProgressStep(3, 'active');
            
            if (data.total_pages > 0) {
                analyzeTotal.textContent = data.total_pages;
                analyzeCurrent.textContent = data.current_page || 1;
                
                // Calculate percentage between 30% and 85%
                const progress = 30 + (((data.current_page || 0) / data.total_pages) * 55);
                setProgressBar(progress);
            }
        } else if (data.status === 'generating_report') {
            updateProgressStep(3, 'completed');
            updateProgressStep(4, 'active');
            setProgressBar(90);
        }
    }

    // ==========================================
    // RESULTS & RENDERING LOGIC
    // ==========================================
    function renderResults(data) {
        const analises = data.resultado?.analises;
        if (!analises || analises.length === 0) {
            showToast('Nenhum resultado retornado.', 'warning');
            return;
        }

        const pagesCount = analises.length;
        resPageCount.textContent = `${pagesCount} página${pagesCount > 1 ? 's' : ''}`;
        document.getElementById('status-pages').textContent = pagesCount;
        
        // Setup Viewer
        pageTotal.textContent = pagesCount;
        setupThumbnails(analises);
        loadPage(0);

        const combinedRaw = analises.map(r => `=== PÁGINA ${r.pagina} ===\n\n${JSON.stringify(r, null, 2)}\n`).join('\n\n');
        document.getElementById('raw-text').textContent = combinedRaw;

        populateAccordions(analises[0]);
    }

    function populateAccordions(jsonObj) {
        // Tipo de Diagrama
        if (jsonObj.tipo_diagrama) {
            document.getElementById('badge-tipo').textContent = jsonObj.tipo_diagrama;
            document.getElementById('content-tipo').innerHTML = `<p><strong>Identificado:</strong> ${jsonObj.tipo_diagrama}</p><p>${jsonObj.descricao_geral || ''}</p>`;
        }

        // Componentes
        if (jsonObj.componentes_identificados) {
            const comps = jsonObj.componentes_identificados;
            document.getElementById('component-count').textContent = comps.length;
            
            let tableHTML = `<table><thead><tr><th>Símbolo</th><th>Descrição</th><th>Tipo</th><th>Espec.</th></tr></thead><tbody>`;
            comps.forEach(c => {
                tableHTML += `<tr><td><strong>${c.simbolo || '-'}</strong></td><td>${c.descricao || '-'}</td><td>${c.tipo || '-'}</td><td>${c.especificacao || '-'}</td></tr>`;
            });
            tableHTML += `</tbody></table>`;
            document.getElementById('content-componentes').innerHTML = tableHTML;
        }

        // Sections
        if (jsonObj.logica_funcionamento) {
            document.getElementById('content-logica').innerHTML = `<p>${jsonObj.logica_funcionamento}</p>`;
        }
        if (jsonObj.legenda_carimbo) {
            let html = '<ul>';
            for (const [k, v] of Object.entries(jsonObj.legenda_carimbo)) {
                html += `<li><strong>${k}:</strong> ${v}</li>`;
            }
            html += '</ul>';
            document.getElementById('content-carimbo').innerHTML = html;
        }
        if (jsonObj.normas_seguranca) {
            let html = '<ul>';
            for (const [k, v] of Object.entries(jsonObj.normas_seguranca)) {
                html += `<li><strong>${k}:</strong> ${v}</li>`;
            }
            html += '</ul>';
            document.getElementById('content-seguranca').innerHTML = html;
        }
    }

    // ==========================================
    // VIEWER LOGIC
    // ==========================================
    function setupThumbnails(results) {
        pageThumbnails.innerHTML = '';
        results.forEach((res, index) => {
            const thumb = document.createElement('div');
            thumb.className = `thumb-wrap ${index === 0 ? 'active' : ''}`;
            thumb.innerHTML = `<img src="data:image/png;base64,${res.image_base64 || ''}" alt="Thumb ${res.pagina}">`;
            thumb.addEventListener('click', () => loadPage(index));
            pageThumbnails.appendChild(thumb);
        });
    }

    function loadPage(index) {
        const analises = analysisResults?.resultado?.analises;
        if (!analises || index < 0 || index >= analises.length) return;
        
        currentPageIndex = index;
        const pageData = analises[index];
        
        // Update Image
        if (pageData.image_base64) {
            pageImage.src = `data:image/png;base64,${pageData.image_base64}`;
        }
        
        // Reset Zoom & Pan
        zoomLevel = 1;
        currentPanX = 0; currentPanY = 0;
        updateTransform();
        
        // Update UI
        pageCurrent.textContent = pageData.pagina;
        btnPrevPage.disabled = index === 0;
        btnNextPage.disabled = index === analises.length - 1;
        
        // Update Thumbnails
        document.querySelectorAll('.thumb-wrap').forEach((el, i) => {
            el.classList.toggle('active', i === index);
        });
        
        // Scroll thumbnail into view
        const activeThumb = document.querySelector('.thumb-wrap.active');
        if (activeThumb) {
            activeThumb.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        }
    }

    btnPrevPage.addEventListener('click', () => loadPage(currentPageIndex - 1));
    btnNextPage.addEventListener('click', () => loadPage(currentPageIndex + 1));

    // Zoom & Pan
    btnZoomIn.addEventListener('click', () => setZoom(zoomLevel + 0.25));
    btnZoomOut.addEventListener('click', () => setZoom(zoomLevel - 0.25));
    btnZoomFit.addEventListener('click', () => { setZoom(1); currentPanX = 0; currentPanY = 0; updateTransform(); });

    imageViewport.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY < 0 ? 0.1 : -0.1;
        setZoom(zoomLevel + delta);
    });

    imageViewport.addEventListener('mousedown', (e) => {
        isDraggingImage = true;
        startPanX = e.clientX - currentPanX;
        startPanY = e.clientY - currentPanY;
        imageViewport.style.cursor = 'grabbing';
    });

    window.addEventListener('mousemove', (e) => {
        if (!isDraggingImage) return;
        currentPanX = e.clientX - startPanX;
        currentPanY = e.clientY - startPanY;
        updateTransform();
    });

    window.addEventListener('mouseup', () => {
        isDraggingImage = false;
        imageViewport.style.cursor = 'grab';
    });

    function setZoom(level) {
        zoomLevel = Math.max(0.1, Math.min(5, level));
        zoomLevelText.textContent = `${Math.round(zoomLevel * 100)}%`;
        updateTransform();
    }

    function updateTransform() {
        imageCanvas.style.transform = `translate(${currentPanX}px, ${currentPanY}px) scale(${zoomLevel})`;
    }

    // ==========================================
    // UI INTERACTION LOGIC
    // ==========================================
    function changeState(targetState) {
        [stateUpload, stateProcessing, stateResults].forEach(state => {
            state.classList.remove('state-active');
        });
        targetState.classList.add('state-active');
    }

    function updateProgressStep(stepNum, status) {
        document.querySelectorAll('.progress-step').forEach(step => {
            if (parseInt(step.dataset.step) === stepNum) {
                step.className = `progress-step ${status}`;
            } else if (parseInt(step.dataset.step) < stepNum && status === 'active') {
                step.className = `progress-step completed`;
            }
        });
    }

    function setProgressBar(percentage) {
        percentage = Math.max(0, Math.min(100, percentage));
        progressBarGlow.style.width = `${percentage}%`;
        progressPercentage.textContent = `${Math.round(percentage)}%`;
    }

    btnNewAnalysis.addEventListener('click', () => {
        currentJobId = null;
        analysisResults = null;
        fileInput.value = '';
        document.querySelectorAll('.progress-step').forEach(step => step.className = 'progress-step');
        setProgressBar(0);
        changeState(stateUpload);
    });

    btnExport.addEventListener('click', () => {
        if (!analysisResults || !analysisResults.pages) {
            showToast('Nenhum resultado para exportar.', 'error');
            return;
        }
        
        let reportText = `Relatório de Análise CAD Elétrico\n`;
        reportText += `Arquivo: ${resFileName.textContent}\n`;
        reportText += `Data: ${new Date().toLocaleString()}\n\n`;
        
        analysisResults.pages.forEach((page, index) => {
            reportText += `=========================================================\n`;
            reportText += `                     PÁGINA ${index + 1}\n`;
            reportText += `=========================================================\n\n`;
            
            reportText += `--- RESUMO ---\n`;
            reportText += `${page.analysis.summary || 'Sem resumo disponível.'}\n\n`;
            
            if (page.analysis.components && page.analysis.components.length > 0) {
                reportText += `--- COMPONENTES IDENTIFICADOS ---\n`;
                page.analysis.components.forEach(comp => {
                    reportText += `- ${comp.name || 'Desconhecido'} (${comp.type || 'N/A'})\n`;
                });
                reportText += `\n`;
            }
            
            if (page.analysis.errors && page.analysis.errors.length > 0) {
                reportText += `--- ERROS E ALERTAS ---\n`;
                page.analysis.errors.forEach(err => {
                    reportText += `[${err.severity ? err.severity.toUpperCase() : 'ALERTA'}] ${err.description || 'Erro não especificado'}\n`;
                });
                reportText += `\n`;
            }
            
            reportText += `\n`;
        });
        
        const blob = new Blob([reportText], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `relatorio_${resFileName.textContent}.txt`;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        showToast('Relatório exportado com sucesso!', 'success');
    });

    // Accordions
    accordions.forEach(item => {
        const header = item.querySelector('.accordion-header');
        header.addEventListener('click', () => {
            item.classList.toggle('open');
        });
    });

    // Open first accordion by default
    if (accordions.length > 0) accordions[0].classList.add('open');

    // Tabs
    panelTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            panelTabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('tab-active'));
            
            tab.classList.add('active');
            document.getElementById(`tab-${tab.dataset.tab}`).classList.add('tab-active');
        });
    });

    // Split Panel Resizing
    const resizeHandle = document.getElementById('resize-handle');
    const panelLeft = document.getElementById('panel-left');
    const panelRight = document.getElementById('panel-right');
    let isResizing = false;

    resizeHandle.addEventListener('mousedown', () => isResizing = true);
    window.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        const containerWidth = document.querySelector('.split-container').offsetWidth;
        const newLeftWidth = (e.clientX / containerWidth) * 100;
        if (newLeftWidth > 20 && newLeftWidth < 80) {
            panelLeft.style.width = `${newLeftWidth}%`;
            panelRight.style.width = `${100 - newLeftWidth}%`;
            resizeHandle.style.left = `${newLeftWidth}%`;
        }
    });
    window.addEventListener('mouseup', () => isResizing = false);

    // Toast Notifications
    function showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        let icon = 'info-circle';
        if (type === 'success') icon = 'check-circle';
        if (type === 'error') icon = 'exclamation-circle';
        if (type === 'warning') icon = 'exclamation-triangle';

        toast.innerHTML = `<i class="fas fa-${icon}"></i><span>${message}</span>`;
        container.appendChild(toast);
        
        // Trigger reflow for animation
        toast.offsetHeight;
        toast.classList.add('show');
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }
});
