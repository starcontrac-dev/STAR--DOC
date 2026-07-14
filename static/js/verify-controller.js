/**
 * STAR-DOC - Controlador del Portal Público de Verificación de Contratos y Títulos
 * Cumple con los estándares de evidencia digital de la Ley 527 de 1999 de Colombia.
 */
document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileSelectBtn = document.getElementById('file-select-btn');
    const verifyBtn = document.getElementById('verify-btn');
    const fileInfo = document.getElementById('file-info');
    const selectedFileName = document.getElementById('selected-file-name');
    const resetBtn = document.getElementById('reset-btn');
    
    const loadingState = document.getElementById('loading-state');
    const resultsState = document.getElementById('results-state');
    
    // Contenedores de resultados
    const integrityBanner = document.getElementById('integrity-banner');
    const integrityTitle = document.getElementById('integrity-title');
    const integrityDesc = document.getElementById('integrity-desc');
    const integrityIcon = document.getElementById('integrity-icon');
    
    const docNameDisplay = document.getElementById('doc-name-display');
    const docHashDisplay = document.getElementById('doc-hash-display');
    const docDateDisplay = document.getElementById('doc-date-display');
    const ipfsContainer = document.getElementById('ipfs-container');
    const ipfsCidDisplay = document.getElementById('ipfs-cid-display');
    const ipfsLink = document.getElementById('ipfs-link');
    
    const signersList = document.getElementById('signers-list');
    
    let currentFile = null;

    // --- Eventos de Drag and Drop ---
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('border-primary', 'bg-primary/10');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('border-primary', 'bg-primary/10');
        }, false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleFileSelection(files[0]);
        }
    });

    fileSelectBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelection(e.target.files[0]);
        }
    });

    // --- Procesar Selección de Archivo ---
    function handleFileSelection(file) {
        const nameLower = file.name.toLowerCase();
        if (!nameLower.endsWith('.pdf') && !nameLower.endsWith('.md')) {
            showToast('Por favor, seleccione únicamente archivos en formato PDF o actas en formato .md.', 'error');
            return;
        }
        currentFile = file;
        selectedFileName.textContent = file.name;
        
        // Ajustar iconos y textos del tipo de archivo en la UI
        const fileIconContainer = fileInfo.querySelector('.text-4xl');
        const fileDescContainer = fileInfo.querySelector('.text-xs.text-base-content\\/50');
        if (nameLower.endsWith('.md')) {
            if (fileIconContainer) {
                fileIconContainer.innerHTML = '<i class="bi bi-file-earmark-text-fill text-accent"></i>';
            }
            if (fileDescContainer) {
                fileDescContainer.textContent = 'Formato Acta MD listo para verificación';
            }
        } else {
            if (fileIconContainer) {
                fileIconContainer.innerHTML = '<i class="bi bi-file-earmark-pdf-fill"></i>';
            }
            if (fileDescContainer) {
                fileDescContainer.textContent = 'Formato PDF listo para verificación';
            }
        }

        // Efecto visual de archivo cargado
        dropZone.classList.add('hidden');
        fileInfo.classList.remove('hidden');
        verifyBtn.disabled = false;
        
        // Auto-verificar para mayor fluidez
        verifyDocument();
    }

    // --- Reiniciar Formulario ---
    resetBtn.addEventListener('click', resetForm);

    function resetForm() {
        currentFile = null;
        fileInput.value = '';
        dropZone.classList.remove('hidden');
        fileInfo.classList.add('hidden');
        verifyBtn.disabled = true;
        resultsState.classList.add('hidden');
        loadingState.classList.add('hidden');
    }

    // --- Petición de Verificación al Backend ---
    verifyBtn.addEventListener('click', verifyDocument);

    async function verifyDocument() {
        if (!currentFile) return;

        // Mostrar cargador
        loadingState.classList.remove('hidden');
        resultsState.classList.add('hidden');
        verifyBtn.disabled = true;

        const formData = new FormData();
        formData.append('file', currentFile);

        try {
            const response = await fetch('/api/verify-integrity', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Error al procesar la verificación.');
            }

            const data = await response.json();
            renderResults(data);
        } catch (error) {
            console.error(error);
            showToast(error.message, 'error');
            loadingState.classList.add('hidden');
            verifyBtn.disabled = false;
        } finally {
            loadingState.classList.add('hidden');
        }
    }

    // --- Renderizar Resultados en UI ---
    function renderResults(res) {
        resultsState.classList.remove('hidden');
        
        // Limpiar estilos anteriores del banner
        integrityBanner.className = 'alert shadow-lg flex flex-col md:flex-row items-center md:items-start text-center md:text-left gap-4 p-6 border transition-all duration-500 ';
        integrityIcon.className = 'bi text-4xl ';

        const isSuccess = res.success && res.status === 'INTEGRO';
        const isModified = res.success && res.status === 'MODIFICADO';
        const isPending = res.status === 'PENDIENTE_FIRMA';
        const isClean = res.status === 'VERSION_LIMPIA';
        
        if (isSuccess) {
            // INTEGRAL Y ORIGINAL
            integrityBanner.classList.add('bg-success/15', 'text-success', 'border-success/30');
            integrityIcon.classList.add('bi-patch-check-fill', 'text-success');
            integrityTitle.textContent = 'DOCUMENTO VERIFICADO E ÍNTEGRO';
            integrityDesc.textContent = 'Este contrato coincide exactamente con el hash criptográfico y firmas estampadas digitalmente en Star-Doc. Cumple con el Artículo 7 de la Ley 527 de 1999 de Colombia.';
        } else if (isModified) {
            // DETECTADA ADULTERACIÓN
            integrityBanner.classList.add('bg-error/15', 'text-error', 'border-error/30');
            integrityIcon.classList.add('bi-exclamation-triangle-fill', 'text-error');
            integrityTitle.textContent = 'DOCUMENTO ALTERADO O ADULTERADO';
            integrityDesc.textContent = '¡Cuidado! Este archivo PDF ha sufrido modificaciones o alteraciones después de haberse estampado la firma digital. Criptográficamente ha perdido validez legal.';
        } else if (isPending) {
            // PENDIENTE DE FIRMAS
            integrityBanner.classList.add('bg-warning/15', 'text-warning', 'border-warning/30');
            integrityIcon.classList.add('bi-clock-history', 'text-warning');
            integrityTitle.textContent = 'PROCESO DE FIRMA EN CURSO';
            integrityDesc.textContent = 'El documento está registrado en la plataforma, pero su flujo de firma electrónica aún no se ha completado por todos los firmantes.';
        } else if (isClean) {
            // BORRADOR LIMPIO
            integrityBanner.classList.add('bg-info/15', 'text-info', 'border-info/30');
            integrityIcon.classList.add('bi-file-earmark-medical', 'text-info');
            integrityTitle.textContent = 'VERSION ORIGINAL (BORRADOR LIMPIO)';
            integrityDesc.textContent = 'El archivo subido es el documento borrador original limpio (sin firmar). Ya existe una versión final firmada en el sistema, pero el documento subido no contiene las firmas.';
        } else {
            // NO REGISTRADO
            integrityBanner.className = 'alert shadow-lg flex flex-col md:flex-row items-center md:items-start text-center md:text-left gap-4 p-6 border transition-all duration-500 bg-neutral/30 text-base-content/80 border-white/10';
            integrityIcon.classList.add('bi-question-diamond-fill', 'text-base-content/60');
            integrityTitle.textContent = 'DOCUMENTO NO REGISTRADO';
            integrityDesc.textContent = 'No se encontró ningún registro de firma electrónica, sello de tiempo ni anclaje IPFS para este documento en la base de datos de Star-Doc.';
        }

        // Renderizar metadatos del documento
        docNameDisplay.textContent = currentFile.name;
        docHashDisplay.textContent = res.hash_calculado || 'No calculado';

        if (res.registro_firma) {
            const reg = res.registro_firma;
            
            // Fecha
            if (reg.timestamp_utc) {
                let dateStr = reg.timestamp_utc;
                if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-')) {
                    dateStr = dateStr.replace(' ', 'T') + 'Z';
                }
                const date = new Date(dateStr);
                docDateDisplay.textContent = date.toLocaleString('es-CO', { timeZone: 'America/Bogota' }) + ' (Hora de Colombia)';
            } else {
                docDateDisplay.textContent = 'No registrada';
            }

            // IPFS Info
            const ipfsCid = reg.seguridad_integridad?.ipfs_cid;
            if (ipfsCid && ipfsCid !== 'local' && ipfsCid !== 'local_db' && ipfsCid !== 'local_audit') {
                ipfsContainer.classList.remove('hidden');
                ipfsCidDisplay.textContent = ipfsCid;
                ipfsLink.href = `https://ipfs.io/ipfs/${ipfsCid}`;
            } else {
                ipfsContainer.classList.add('hidden');
            }

            // Renderizar firmantes
            signersList.innerHTML = '';
            
            if (reg.firmantes && reg.firmantes.length > 0) {
                reg.firmantes.forEach(signer => {
                    const dateSign = signer.signed_at ? new Date(signer.signed_at).toLocaleString('es-CO', { timeZone: 'America/Bogota' }) : 'No firmado';
                    
                    const card = document.createElement('div');
                    card.className = 'glass-card p-5 rounded-xl border border-white/5 flex flex-col justify-between gap-4 transition-all duration-300';
                    
                    // Contenido superior
                    let statusBadge = '';
                    if (signer.signed) {
                        statusBadge = `<span class="badge badge-success gap-1 text-white py-2 px-3 text-xs"><i class="bi bi-check-circle-fill"></i> Firmado</span>`;
                    } else {
                        statusBadge = `<span class="badge badge-neutral gap-1 py-2 px-3 text-xs"><i class="bi bi-clock-history"></i> Pendiente</span>`;
                    }

                    let videoBadge = '';
                    if (signer.video_evidencia_cid) {
                        videoBadge = `
                            <a href="https://ipfs.io/ipfs/${signer.video_evidencia_cid}" target="_blank" class="btn btn-xs btn-outline btn-accent gap-1 mt-2 text-xs">
                                <i class="bi bi-camera-video-fill"></i> Evidencia en Video (IPFS)
                            </a>`;
                    }

                    card.innerHTML = `
                        <div class="flex items-start justify-between gap-2">
                            <div class="min-w-0 flex-1">
                                <h4 class="font-bold text-white text-base md:text-lg truncate" title="${signer.nombre}">${signer.nombre}</h4>
                                <p class="text-xs text-base-content/60 font-mono break-all">${signer.email}</p>
                            </div>
                            <div class="flex-shrink-0">${statusBadge}</div>
                        </div>
                        <div class="text-xs text-base-content/75 flex flex-col gap-1.5 border-t border-white/5 pt-3">
                            <div class="flex justify-between gap-2">
                                <span class="text-base-content/50">Fecha de firma:</span>
                                <span class="font-semibold text-white text-right">${dateSign}</span>
                            </div>
                            <div class="flex justify-between gap-2">
                                <span class="text-base-content/50">IP de Origen:</span>
                                <span class="font-mono text-white text-right">${signer.ip || 'No registrada'}</span>
                            </div>
                            <div class="flex justify-between gap-2 truncate">
                                <span class="text-base-content/50 mr-2">Dispositivo:</span>
                                <span class="text-white text-right truncate max-w-[110px] sm:max-w-[150px]" title="${signer.user_agent || ''}">${signer.user_agent ? signer.user_agent.split(' ')[0] : 'Navegador Web'}</span>
                            </div>
                            <div class="flex justify-between gap-2">
                                <span class="text-base-content/50">Habeas Data:</span>
                                <span class="font-semibold ${signer.consentimiento_habeas_data ? 'text-success' : 'text-neutral'}">
                                    ${signer.consentimiento_habeas_data ? 'Aceptado ✅' : 'No'}
                                </span>
                            </div>
                        </div>
                        ${videoBadge}
                    `;
                    signersList.appendChild(card);
                });
            } else {
                signersList.innerHTML = `<div class="col-span-full text-center text-base-content/50 py-6">No se encontraron firmantes asociados a esta solicitud.</div>`;
            }

        } else {
            // Si es modificado u original sin registro en DB
            docDateDisplay.textContent = 'No disponible';
            ipfsContainer.classList.add('hidden');
            signersList.innerHTML = `<div class="col-span-full text-center text-base-content/50 py-6">No hay información de firmantes disponible.</div>`;
        }

        // Hacer scroll suave hacia los resultados
        resultsState.scrollIntoView({ behavior: 'smooth' });
    }

    // --- Helper Toast de Notificaciones ---
    function showToast(message, type = 'info') {
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast toast-top toast-end z-[9999]';
            document.body.appendChild(toastContainer);
        }
        
        const toast = document.createElement('div');
        let bgClass = 'bg-info';
        if (type === 'error') bgClass = 'bg-error';
        if (type === 'success') bgClass = 'bg-success';
        if (type === 'warning') bgClass = 'bg-warning';
        
        toast.className = `alert ${bgClass} text-white shadow-lg text-sm flex items-center gap-2 p-3.5 rounded-lg border-none`;
        toast.innerHTML = `
            <span>${message}</span>
            <button onclick="this.parentElement.remove()" class="btn btn-ghost btn-xs btn-circle text-white">✕</button>
        `;
        toastContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }
});
