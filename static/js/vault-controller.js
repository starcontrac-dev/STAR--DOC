// vault-controller.js - Controlador para la Bóveda Documental y Expedientes IPFS en STAR-DOC
// Desarrollado con mejores prácticas y soporte de comunicación con Alpine.js

/**
 * Función auxiliar de notificaciones.
 * Detecta automáticamente el tipo de mensaje según el contenido y
 * enruta al sistema showToast si está disponible; de lo contrario
 * usa el diálogo nativo como respaldo de emergencia.
 * @param {string} message - Texto de la notificación
 * @param {string} [forceType] - Tipo forzado: 'success' | 'error' | 'warning' | 'info'
 */
function _vaultNotify(message, forceType = null) {
    let type = forceType;
    if (!type) {
        const lc = message.toLowerCase();
        if (lc.includes('error') || lc.includes('fallo') || lc.includes('❌') || lc.includes('no se pudo')) {
            type = 'error';
        } else if (lc.includes('✓') || lc.includes('éxito') || lc.includes('exitosamente') || lc.includes('copiado') || lc.includes('creado') || lc.includes('ejecutado') || lc.includes('publicado') || lc.includes('registrado') || lc.includes('sincronizado') || lc.includes('resuelto') || lc.includes('generada')) {
            type = 'success';
        } else if (lc.includes('advertencia') || lc.includes('por favor') || lc.includes('ingrese')) {
            type = 'warning';
        } else {
            type = 'info';
        }
    }
    if (window.showToast) {
        window.showToast(message, type);
    } else {
        alert(message); // fallback de emergencia
    }
}

let rvDocuments = [];
let rvAudits = [];
let activeVaultTab = 'docs'; // 'docs' o 'audits'

function _showMobilePreview() {
    const left = document.getElementById('rv-left-panel');
    const right = document.getElementById('rv-right-panel');
    if (left && window.innerWidth < 768) {
        left.classList.add('hidden');
    }
    if (right && window.innerWidth < 768) {
        right.classList.remove('hidden');
    }
}

function _showMobileList() {
    const left = document.getElementById('rv-left-panel');
    const right = document.getElementById('rv-right-panel');
    if (left && window.innerWidth < 768) {
        left.classList.remove('hidden');
    }
    if (right && window.innerWidth < 768) {
        right.classList.add('hidden');
    }
}

window.switchVaultTab = function (tab) {
    activeVaultTab = tab;
    const btnDocs = document.getElementById('tab-vault-docs');
    const btnAudits = document.getElementById('tab-vault-audits');
    
    const containerDocs = document.getElementById('rv-docs-container');
    const containerAudits = document.getElementById('rv-audits-container');

    // Resetear estilos de pestañas (Modo Oscuro)
    if (btnDocs) btnDocs.className = "flex-1 py-3 text-center text-xs font-bold border-b-2 border-transparent text-gray-400 hover:text-cyan-400 transition-all focus:outline-none";
    if (btnAudits) btnAudits.className = "flex-1 py-3 text-center text-xs font-bold border-b-2 border-transparent text-gray-400 hover:text-cyan-400 transition-all focus:outline-none";
    
    if (containerDocs) containerDocs.classList.add('hidden');
    if (containerAudits) containerAudits.classList.add('hidden');

    if (tab === 'docs') {
        if (btnDocs) btnDocs.className = "flex-1 py-3 text-center text-xs font-bold border-b-2 border-cyan-400 text-cyan-400 transition-all focus:outline-none";
        if (containerDocs) containerDocs.classList.remove('hidden');
        fetchVaultDocuments();
        clearRvPreview();
    } else if (tab === 'audits') {
        if (btnAudits) btnAudits.className = "flex-1 py-3 text-center text-xs font-bold border-b-2 border-cyan-400 text-cyan-400 transition-all focus:outline-none";
        if (containerAudits) containerAudits.classList.remove('hidden');
        fetchVaultAudits();
        clearRvPreview();
    }
}

window.openRagVaultModal = function () {
    const modal = document.getElementById('rag_vault_modal');
    const content = document.getElementById('rv-modal-card');
    if (modal) {
        modal.classList.remove('hidden');
        
        // Asegurar que en móvil inicie mostrando la lista de documentos
        const left = document.getElementById('rv-left-panel');
        const right = document.getElementById('rv-right-panel');
        if (left) left.classList.remove('hidden');
        if (right) right.classList.add('hidden');
        
        // Lanzar animación
        setTimeout(() => {
            modal.style.opacity = '1';
            content.classList.remove('scale-95');
            content.classList.add('scale-100');
        }, 10);
        switchVaultTab('docs');
    }
}

window.closeRagVaultModal = function () {
    const modal = document.getElementById('rag_vault_modal');
    const content = document.getElementById('rv-modal-card');
    if (modal) {
        modal.style.opacity = '0';
        content.classList.remove('scale-100');
        content.classList.add('scale-95');
        setTimeout(() => {
            modal.classList.add('hidden');
        }, 300);
    }
}

async function fetchVaultDocuments() {
    const token = localStorage.getItem("access_token");
    if (!token) return;

    try {
        const res = await fetch('/api/documents/my-documents', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            rvDocuments = await res.json();
            renderRvList();
            updateSelectedDocsCount();
        }
    } catch (e) {
        console.error("Error fetching vault docs:", e);
    }
}

function getBadgeClass(classification) {
    if (classification === 'public') return 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
    if (classification === 'confidential') return 'bg-amber-500/10 text-amber-400 border border-amber-500/20';
    if (classification === 'chain_of_custody') return 'bg-purple-500/10 text-purple-400 border border-purple-500/20';
    return 'bg-white/5 text-gray-400 border border-white/10';
}

function getClassificationName(classification) {
    if (classification === 'public') return 'Público';
    if (classification === 'confidential') return 'Confidencial';
    if (classification === 'chain_of_custody') return 'Custodia';
    return classification;
}

window.copyCIDToClipboard = function (event, cid) {
    event.stopPropagation();
    navigator.clipboard.writeText(cid).then(() => {
        if (window.showToast) {
            window.showToast('CID copiado al portapapeles', 'success');
        } else {
            _vaultNotify('CID copiado: ' + cid);
        }
    }).catch(err => {
        console.error('Error al copiar CID:', err);
    });
}

window.verCertificadoLegal = function (event, cid) {
    event.stopPropagation();
    const modal = document.getElementById('certificate_modal');
    const content = document.getElementById('cert-modal-card');
    const iframe = document.getElementById('cert-iframe');
    
    if (modal && iframe) {
        iframe.src = `/ipfs/certificate/${cid}`;
        modal.classList.remove('hidden');
        setTimeout(() => {
            modal.style.opacity = '1';
            content.classList.remove('scale-95');
            content.classList.add('scale-100');
        }, 10);
    }
}

window.closeCertificateModal = function () {
    const modal = document.getElementById('certificate_modal');
    const content = document.getElementById('cert-modal-card');
    const iframe = document.getElementById('cert-iframe');
    if (modal) {
        modal.style.opacity = '0';
        content.classList.remove('scale-100');
        content.classList.add('scale-95');
        setTimeout(() => {
            modal.classList.add('hidden');
            if (iframe) iframe.src = '';
        }, 300);
    }
}

window.printCertificate = function () {
    const iframe = document.getElementById('cert-iframe');
    if (iframe && iframe.contentWindow) {
        iframe.contentWindow.focus();
        iframe.contentWindow.print();
    }
}

window.verificarIntegridad = async function (event, cid, sha256, buttonElement) {
    event.stopPropagation();
    
    const originalHTML = buttonElement.innerHTML;
    buttonElement.disabled = true;
    buttonElement.innerHTML = `
        <svg class="animate-spin h-3.5 w-3.5 text-indigo-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
    `;

    const token = localStorage.getItem("access_token");
    try {
        const res = await fetch(`/ipfs/verify/${cid}?sha256=${sha256}`, {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        
        buttonElement.disabled = false;
        buttonElement.innerHTML = originalHTML;

        if (res.ok) {
            const data = await res.json();
            if (data.valid) {
                _vaultNotify(`✓ Integridad Confirmada:\nEl hash criptográfico original coincide plenamente.\n\nHash SHA-256:\n${sha256}\n\nVerificado via: ${data.verification_mode}`);
            } else {
                _vaultNotify(`❌ Falló la verificación de integridad:\nEl hash del documento en IPFS no coincide con el registrado.\n\nEsperado: ${sha256}\nObtenido: ${data.actual_sha256}`);
            }
        } else {
            const err = await res.json();
            _vaultNotify("Error en verificación: " + (err.detail || "Desconocido"));
        }
    } catch (e) {
        console.error(e);
        buttonElement.disabled = false;
        buttonElement.innerHTML = originalHTML;
        _vaultNotify("Error al verificar integridad en red.");
    }
}

window.updateSelectedDocsCount = function () {
    const checkboxes = document.querySelectorAll('.rv-doc-cb:checked');
    const packContainer = document.getElementById('rv-pack-container');
    if (checkboxes.length >= 2) {
        packContainer.classList.remove('hidden');
    } else {
        packContainer.classList.add('hidden');
    }
}

window.createIPFSPack = async function () {
    const checkboxes = document.querySelectorAll('.rv-doc-cb:checked');
    const packNameInput = document.getElementById('rv-pack-name');
    const name = packNameInput.value.trim();

    if (!name) {
        _vaultNotify("Por favor ingrese un nombre para el expediente.");
        return;
    }

    const document_ids = Array.from(checkboxes).map(cb => parseInt(cb.value));
    const token = localStorage.getItem("access_token");

    try {
        const listDiv = document.getElementById('rv-doc-list');
        listDiv.innerHTML = '<div class="flex flex-col items-center justify-center p-8 space-y-3"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div><p class="text-xs text-indigo-600 font-medium">Empaquetando expediente en Merkle DAG...</p></div>';

        const res = await fetch('/ipfs/pack-audit', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name, document_ids })
        });

        if (res.ok) {
            const data = await res.json();
            _vaultNotify(`¡Expediente "${data.name}" creado con éxito en IPFS!\nCID: ${data.ipfs_cid}`);
            packNameInput.value = '';
            switchVaultTab('audits');
        } else {
            const err = await res.json();
            _vaultNotify("Error al crear expediente: " + (err.detail || "Desconocido"));
            fetchVaultDocuments();
        }
    } catch (e) {
        console.error(e);
        _vaultNotify("Error al procesar la solicitud.");
        fetchVaultDocuments();
    }
}

async function fetchVaultAudits() {
    const token = localStorage.getItem("access_token");
    if (!token) return;

    try {
        const res = await fetch('/ipfs/audits', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            const data = await res.json();
            rvAudits = data.audits || [];
            renderRvAuditsList();
        }
    } catch (e) {
        console.error("Error fetching audits:", e);
    }
}

function renderRvAuditsList() {
    const listDiv = document.getElementById('rv-audits-list');
    document.getElementById('rv-audits-count').textContent = `${rvAudits.length} expedientes`;

    if (rvAudits.length === 0) {
        listDiv.innerHTML = '<p class="text-gray-400 text-xs text-center mt-6">No hay expedientes.</p>';
        return;
    }

    listDiv.innerHTML = rvAudits.map(audit => `
        <div class="group relative p-2.5 sm:p-3 rounded-xl bg-white/5 border border-white/10 hover:border-cyan-500/30 shadow-sm hover:shadow-md transition-all cursor-pointer overflow-hidden mb-2"
             onclick="viewAuditLogs('${audit.ipfs_cid}', '${audit.name}')">
            <div class="flex items-start gap-3 relative z-10">
                <div class="w-8 h-8 rounded-lg bg-purple-500/10 flex items-center justify-center shrink-0 border border-purple-500/20 text-purple-400 group-hover:bg-purple-600 group-hover:text-white transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                    </svg>
                </div>
                <div class="flex-1 min-w-0 flex flex-col justify-center h-8">
                    <h5 class="text-[11px] sm:text-xs font-semibold text-gray-200 truncate group-hover:text-cyan-400 transition-colors" title="${audit.name}">${audit.name}</h5>
                    <p class="text-[9px] sm:text-[10px] text-gray-400 font-medium">${audit.document_ids.length} docs • ${new Date(audit.created_at).toLocaleDateString()}</p>
                </div>
            </div>
            <div class="absolute right-2 top-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity bg-black/90 p-1 rounded-lg border border-white/10 shadow-sm z-20">
                <a href="/ipfs/download-pack/${audit.ipfs_cid}" onclick="event.stopPropagation()" class="p-1 rounded text-cyan-400 hover:bg-white/10" title="Descargar ZIP" download>
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                </a>
            </div>
            <div class="absolute left-0 top-0 bottom-0 w-1 bg-purple-500 opacity-0 group-hover:opacity-100 transition-opacity"></div>
        </div>
    `).join('');
}

let currentAuditDetails = null;
let currentAuditLogs = null;
let activeAuditSubTab = 'docs'; // 'docs' o 'logs'

window.viewAuditLogs = async function (cid, name) {
    _showMobilePreview();
    const token = localStorage.getItem("access_token");
    const contentDiv = document.getElementById('rv-preview-content');
    contentDiv.innerHTML = '<div class="flex justify-center mt-20"><div class="animate-pulse flex flex-col items-center"><div class="rounded-full bg-purple-500/20 h-10 w-10 mb-4"></div><div class="h-2 bg-white/10 rounded w-32"></div></div></div>';

    try {
        const [detailsRes, logsRes] = await Promise.all([
            fetch(`/ipfs/audit/${cid}`, { headers: { 'Authorization': 'Bearer ' + token } }),
            fetch(`/ipfs/audit/${cid}/logs`, { headers: { 'Authorization': 'Bearer ' + token } })
        ]);

        if (detailsRes.ok && logsRes.ok) {
            currentAuditDetails = await detailsRes.json();
            currentAuditLogs = await logsRes.json();
            
            document.getElementById('rv-preview-header').classList.remove('hidden');
            document.getElementById('rv-preview-title').textContent = `Expediente: ${name}`;
            document.getElementById('rv-preview-meta').textContent = `CID: ${cid}`;

            const wrapper = document.getElementById('rv-preview-icon-wrapper');
            if (wrapper) {
                wrapper.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                    </svg>
                `;
            }

            const actionsDiv = document.getElementById('rv-preview-actions');
            if (actionsDiv) {
                actionsDiv.innerHTML = `
                    <a href="/ipfs/download-pack/${cid}" download class="bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all shadow-sm active:scale-95 border border-indigo-500 font-sans" title="Descargar expediente en ZIP">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        Descargar Expediente (ZIP)
                    </a>
                `;
            }

            activeAuditSubTab = 'docs';
            renderAuditSubTab();
        } else {
            contentDiv.innerHTML = '<p class="text-red-500 text-sm p-4 bg-red-50 rounded-lg border border-red-100 font-sans">Error al consultar el expediente y su bitácora de custodia.</p>';
        }
    } catch (e) {
        console.error(e);
        contentDiv.innerHTML = '<p class="text-red-500 text-sm p-4 bg-red-50 rounded-lg border border-red-100 font-sans">Error al conectar con el servidor.</p>';
    }
}

window.switchAuditSubTab = function (subTab) {
    activeAuditSubTab = subTab;
    renderAuditSubTab();
}

function renderAuditSubTab() {
    const contentDiv = document.getElementById('rv-preview-content');
    if (!currentAuditDetails || !currentAuditLogs) return;

    const tabHeader = `
        <div class="flex border-b border-white/10 bg-transparent mb-4 shrink-0 font-sans">
            <button onclick="switchAuditSubTab('docs')" class="flex-1 py-2 text-center text-xs font-bold border-b-2 ${activeAuditSubTab === 'docs' ? 'border-purple-500 text-purple-400' : 'border-transparent text-gray-400 hover:text-purple-400'} transition-all focus:outline-none">
                📁 Estructura del Expediente (${currentAuditDetails.documents ? currentAuditDetails.documents.length : 0} docs)
            </button>
            <button onclick="switchAuditSubTab('logs')" class="flex-1 py-2 text-center text-xs font-bold border-b-2 ${activeAuditSubTab === 'logs' ? 'border-purple-500 text-purple-400' : 'border-transparent text-gray-400 hover:text-purple-400'} transition-all focus:outline-none">
                🕵️ Cadena de Custodia (Bitácora de Logs)
            </button>
        </div>
    `;

    if (activeAuditSubTab === 'docs') {
        let docRows = "";
        if (currentAuditDetails.documents && currentAuditDetails.documents.length > 0) {
            docRows = currentAuditDetails.documents.map(doc => `
                <tr class="border-b border-white/5 hover:bg-white/5 transition-colors font-sans" id="audit-doc-row-${doc.id}">
                    <td class="px-3 py-3 text-[11px] text-white font-semibold truncate max-w-[150px]" title="${doc.filename}">${doc.filename}</td>
                    <td class="px-3 py-3 text-[10px] text-cyan-400 font-mono truncate max-w-[100px]">
                        <span title="${doc.cid}">${doc.cid}</span>
                        <button onclick="copyCIDToClipboard(event, '${doc.cid}')" class="text-gray-400 hover:text-cyan-400 transition-colors p-0.5 ml-1 focus:outline-none" title="Copiar CID">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-2.5 w-2.5 inline" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2" />
                            </svg>
                        </button>
                    </td>
                    <td class="px-3 py-3 text-[10px] text-gray-400 font-mono truncate max-w-[100px]" title="${doc.sha256}">${doc.sha256}</td>
                    <td class="px-3 py-3 text-[10px]">
                        <span class="px-1.5 py-0.5 rounded-full text-[9px] font-bold ${getBadgeClass(doc.classification)}">
                            ${getClassificationName(doc.classification).toUpperCase()}
                        </span>
                    </td>
                    <td class="px-3 py-3 text-right">
                        <div class="flex items-center justify-end gap-2">
                            <span id="integrity-badge-${doc.id}" class="px-2 py-0.5 rounded-md text-[9px] font-bold bg-white/5 text-gray-400 border border-white/10">
                                Sin Auditar
                            </span>
                            <button onclick="auditarDocumentoIndividual(event, ${doc.id}, '${doc.cid}', '${doc.sha256}', this)" class="p-1 text-purple-400 hover:bg-white/10 rounded focus:outline-none" title="Auditar integridad criptográfica">
                                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                            </button>
                        </div>
                    </td>
                </tr>
            `).join('');
        } else {
            docRows = `
                <tr>
                    <td colspan="5" class="px-4 py-8 text-center text-gray-400 text-xs">
                        Este expediente está vacío o no tiene documentos vinculados.
                    </td>
                </tr>
            `;
        }

        contentDiv.innerHTML = `
            ${tabHeader}
            <div class="p-2 sm:p-4 bg-black/45 backdrop-blur-md rounded-xl border border-white/10 shadow-sm font-sans text-left">
                <div class="flex justify-between items-center mb-4">
                    <h4 class="text-xs font-bold text-white uppercase tracking-wider">Estructura del Merkle DAG del Caso</h4>
                    <button onclick="auditarTodoElExpediente(this)" class="bg-purple-600 hover:bg-purple-700 text-white font-bold px-3 py-1.5 rounded-lg text-[10px] sm:text-xs flex items-center gap-1.5 transition-all shadow-sm active:scale-95">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Auditar Todo el Expediente
                    </button>
                </div>
                <div class="w-full overflow-x-auto">
                    <table class="min-w-full bg-transparent border border-white/10 rounded-lg overflow-hidden">
                        <thead class="bg-white/5 border-b border-white/10 text-[9px] font-bold text-gray-400 uppercase tracking-wider text-left font-sans">
                            <tr>
                                <th class="px-3 py-2">Documento / Evidencia</th>
                                <th class="px-3 py-2">IPFS CID</th>
                                <th class="px-3 py-2">SHA-256 Original</th>
                                <th class="px-3 py-2">Clasificación</th>
                                <th class="px-3 py-2 text-right">Integridad</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${docRows}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    } else {
        let logRows = "";
        if (currentAuditLogs.logs && currentAuditLogs.logs.length > 0) {
            logRows = currentAuditLogs.logs.map(log => `
                <tr class="border-b border-white/5 hover:bg-white/5 transition-colors font-sans text-xs">
                    <td class="px-3 py-2.5 text-gray-400 whitespace-nowrap">${new Date(log.accessed_at).toLocaleString()}</td>
                    <td class="px-3 py-2.5 text-white font-semibold truncate max-w-[120px]" title="${log.username}">${log.username}</td>
                    <td class="px-3 py-2.5 text-gray-300 font-medium font-sans">
                        <span class="px-1.5 py-0.5 rounded-full text-[9px] font-bold ${log.action.includes('verify') ? 'bg-green-500/10 text-green-400 border border-green-500/20' : log.action.includes('download') ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' : 'bg-white/5 text-gray-400 border border-white/10'}">
                            ${log.action.toUpperCase()}
                        </span>
                    </td>
                    <td class="px-3 py-2.5 text-gray-450 font-mono">${log.ip_address || 'N/A'}</td>
                    <td class="px-3 py-2.5 text-gray-500 truncate max-w-[200px]" title="${log.user_agent}">${log.user_agent || 'N/A'}</td>
                </tr>
            `).join('');
        } else {
            logRows = `
                <tr>
                    <td colspan="5" class="px-4 py-8 text-center text-gray-450 text-xs font-sans">
                        No hay registros de acceso ni auditoría para este expediente en la bitácora.
                    </td>
                </tr>
            `;
        }

        contentDiv.innerHTML = `
            ${tabHeader}
            <div class="p-2 sm:p-4 bg-black/45 backdrop-blur-md rounded-xl border border-white/10 shadow-sm font-sans text-left">
                <div class="w-full overflow-x-auto">
                    <table class="min-w-full bg-transparent border border-white/10 rounded-lg overflow-hidden shadow-sm">
                        <thead class="bg-white/5 border-b border-white/10 text-[9px] font-bold text-gray-400 uppercase tracking-wider text-left">
                            <tr>
                                <th class="px-3 py-2">Fecha / Hora</th>
                                <th class="px-3 py-2">Usuario</th>
                                <th class="px-3 py-2">Acción</th>
                                <th class="px-3 py-2">Dirección IP</th>
                                <th class="px-3 py-2">Agente de Usuario</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${logRows}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }
}

window.auditarDocumentoIndividual = async function (event, docId, cid, sha256, buttonElement) {
    if (event) event.stopPropagation();

    const badge = document.getElementById(`integrity-badge-${docId}`);
    if (badge) {
        badge.className = "px-2 py-0.5 rounded-md text-[9px] font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 animate-pulse";
        badge.textContent = "Verificando...";
    }

    const token = localStorage.getItem("access_token");
    try {
        const res = await fetch(`/ipfs/verify/${cid}?sha256=${sha256}`, {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        
        if (res.ok) {
            const data = await res.json();
            if (data.valid) {
                badge.className = "px-2 py-0.5 rounded-md text-[9px] font-bold bg-green-500/10 text-green-400 border border-green-500/20";
                badge.textContent = "Intacto ✓";
            } else {
                badge.className = "px-2 py-0.5 rounded-md text-[9px] font-bold bg-red-500/10 text-red-400 border border-red-500/20";
                badge.textContent = "Alterado ✗";
            }
        } else {
            badge.className = "px-2 py-0.5 rounded-md text-[9px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20";
            badge.textContent = "Error";
        }
    } catch (e) {
        console.error(e);
        badge.className = "px-2 py-0.5 rounded-md text-[9px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20";
        badge.textContent = "Error";
    }
}

window.auditarTodoElExpediente = async function (buttonElement) {
    if (!currentAuditDetails || !currentAuditDetails.documents) return;
    
    const originalHTML = buttonElement.innerHTML;
    buttonElement.disabled = true;
    buttonElement.innerHTML = `
        <svg class="animate-spin h-3.5 w-3.5 text-white mr-1.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        Verificando...
    `;

    for (const doc of currentAuditDetails.documents) {
        await auditarDocumentoIndividual(null, doc.id, doc.cid, doc.sha256, null);
    }

    buttonElement.disabled = false;
    buttonElement.innerHTML = originalHTML;
    if (window.showToast) window.showToast('Auditoría criptográfica completada.', 'success');
}

function getWorkflowBadge(status) {
    if (!status) return '';
    status = status.toLowerCase();
    if (status === 'draft') {
        return `<span class="inline-flex items-center px-1.5 py-0.2 rounded text-[8px] font-bold bg-white/5 text-gray-400 border border-white/10" title="Borrador preliminar. Requiere aprobación.">📄 Borrador</span>`;
    }
    if (status === 'pending_approval') {
        return `<span class="inline-flex items-center px-1.5 py-0.2 rounded text-[8px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20" title="Pendiente de aprobación por revisor Senior.">⏳ En Revisión</span>`;
    }
    if (status === 'approved') {
        return `<span class="inline-flex items-center px-1.5 py-0.2 rounded text-[8px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" title="Aprobado. Listo para firmas.">✅ Aprobado</span>`;
    }
    if (status === 'pending_signatures') {
        return `<span class="inline-flex items-center px-1.5 py-0.2 rounded text-[8px] font-bold bg-purple-500/10 text-purple-400 border border-purple-500/20" title="Proceso de firmas iniciado.">✍️ En Firmas</span>`;
    }
    if (status === 'signed') {
        return `<span class="inline-flex items-center px-1.5 py-0.2 rounded text-[8px] font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20" title="Firmado digitalmente y anclado a IPFS de forma inmutable.">🔒 Firmado</span>`;
    }
    if (status === 'rejected') {
        return `<span class="inline-flex items-center px-1.5 py-0.2 rounded text-[8px] font-bold bg-red-500/10 text-red-400 border border-red-500/20" title="Rechazado. Por favor revise los comentarios del revisor.">❌ Rechazado</span>`;
    }
    return '';
}

function renderRvList() {
    const listDiv = document.getElementById('rv-doc-list');
    document.getElementById('rv-doc-count').textContent = `${rvDocuments.length} documentos`;

    if (rvDocuments.length === 0) {
        listDiv.innerHTML = '<p class="text-gray-400 text-xs text-center mt-6">Bóveda vacía.</p>';
        clearRvPreview();
        return;
    }

    listDiv.innerHTML = rvDocuments.map(doc => {
        const hasIpfs = doc.ipfs !== null;
        const ipfsCid = hasIpfs ? doc.ipfs.cid : '';
        const ipfsClass = hasIpfs ? doc.ipfs.classification : '';
        const ipfsHash = hasIpfs ? doc.ipfs.sha256_original : '';
        const pinnedKubo = hasIpfs ? doc.ipfs.pinned_kubo : false;
        const pinnedPinata = hasIpfs ? doc.ipfs.pinned_pinata : false;
        
        return `
        <div class="group relative p-2.5 sm:p-3 rounded-xl bg-white/5 border border-white/10 hover:border-cyan-500/30 shadow-sm hover:shadow-md transition-all cursor-pointer overflow-hidden mb-2"
             onclick="viewDocument(${doc.id})">
             <div class="flex items-start gap-2.5 relative z-10">
                <div class="pt-0.5" onclick="event.stopPropagation()">
                    <input type="checkbox" class="rv-doc-cb rounded border-white/20 bg-white/5 text-cyan-500 focus:ring-cyan-500 h-3.5 w-3.5" value="${doc.id}" onchange="updateSelectedDocsCount()">
                </div>
                <div class="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center shrink-0 border border-indigo-500/20 text-indigo-400 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                </div>
                <div class="flex-1 min-w-0 flex flex-col justify-center">
                    <h5 class="text-[11px] sm:text-xs font-semibold text-gray-200 truncate group-hover:text-cyan-400 transition-colors" title="${doc.filename}">${doc.filename}</h5>
                    <div class="flex items-center gap-2 mt-0.5 font-sans">
                        <p class="text-[9px] text-gray-400 font-medium">${new Date(doc.upload_date).toLocaleDateString()}</p>
                        ${getWorkflowBadge(doc.status)}
                    </div>
                    
                    ${hasIpfs ? `
                    <div class="flex items-center gap-1 mt-1 flex-wrap font-sans">
                        <span class="inline-flex items-center gap-0.5 px-1 py-0.2 rounded text-[8px] font-bold ${getBadgeClass(ipfsClass)}">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-2 w-2" viewBox="0 0 20 20" fill="currentColor">
                                <path fill-rule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clip-rule="evenodd" />
                            </svg>
                            ${getClassificationName(ipfsClass)}
                        </span>
                        <span class="inline-flex items-center gap-0.5 px-1 py-0.2 rounded text-[8px] font-semibold ${pinnedKubo ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20' : 'bg-white/5 text-gray-400 border border-white/10'}" title="${pinnedKubo ? 'Disponible en nodo local Kubo' : 'Archivado de nodo local'}">
                            💻 ${pinnedKubo ? 'Local' : 'Archivado'}
                        </span>
                        <span class="inline-flex items-center gap-0.5 px-1 py-0.2 rounded text-[8px] font-semibold ${pinnedPinata ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20' : 'bg-white/5 text-gray-400 border border-white/10'}" title="${pinnedPinata ? 'Sincronizado con Pinata Cloud' : 'Solo Local (Pendiente Sync)'}">
                            ☁️ ${pinnedPinata ? 'Sync' : 'Solo Local'}
                        </span>
                        <span class="text-[8px] text-gray-400 font-mono truncate max-w-[50px]" title="${ipfsCid}">${ipfsCid}</span>
                        <button onclick="copyCIDToClipboard(event, '${ipfsCid}')" class="text-gray-400 hover:text-cyan-400 transition-colors p-0.5 focus:outline-none" title="Copiar CID">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                            </svg>
                        </button>
                    </div>
                    ` : ''}
                </div>
            </div>

            <!-- Acciones flotantes en Hover -->
            <div class="absolute right-2 top-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity bg-black/90 p-1 rounded-lg border border-white/10 shadow-sm z-20">
                ${hasIpfs ? `
                <button onclick="verCertificadoLegal(event, '${ipfsCid}')" class="p-1 rounded text-cyan-400 hover:bg-white/10 focus:outline-none" title="Ver Certificado Legal">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                </button>
                <button onclick="verificarIntegridad(event, '${ipfsCid}', '${ipfsHash}', this)" class="p-1 rounded text-emerald-400 hover:bg-white/10 focus:outline-none" title="Verificar Integridad">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                </button>
                ${!pinnedPinata ? `
                <button onclick="syncDocumentPinata(event, '${ipfsCid}', this)" class="p-1 rounded text-sky-400 hover:bg-white/10 focus:outline-none" title="Sincronizar con Pinata Cloud">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" />
                    </svg>
                </button>
                ` : ''}
                ${pinnedKubo ? `
                <button onclick="unpinDocumentKubo(event, '${ipfsCid}', this)" class="p-1 rounded text-amber-400 hover:bg-white/10 focus:outline-none" title="Archivar de nodo local">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                    </svg>
                </button>
                ` : ''}
                ` : ''}
                <button onclick="deleteDocument(event, ${doc.id})" class="p-1 rounded text-red-400 hover:bg-white/10 focus:outline-none" title="Eliminar documento de la Bóveda">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
            </div>

            <div class="absolute left-0 top-0 bottom-0 w-1 bg-indigo-500 opacity-0 group-hover:opacity-100 transition-opacity"></div>
        </div>
        `;
    }).join('');
}

window.viewDocument = async function (id) {
    _showMobilePreview();
    const token = localStorage.getItem("access_token");
    const contentDiv = document.getElementById('rv-preview-content');
    contentDiv.innerHTML = '<div class="flex justify-center mt-20"><div class="animate-pulse flex flex-col items-center"><div class="rounded-full bg-indigo-500/20 h-10 w-10 mb-4"></div><div class="h-2 bg-white/10 rounded w-32"></div></div></div>';

    try {
        const res = await fetch(`/api/documents/${id}`, {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            const data = await res.json();

            document.getElementById('rv-preview-header').classList.remove('hidden');
            document.getElementById('rv-preview-title').textContent = data.filename;
            document.getElementById('rv-preview-meta').textContent = `Subido el: ${new Date(data.upload_date).toLocaleString()}`;

            const wrapper = document.getElementById('rv-preview-icon-wrapper');
            if (wrapper) {
                wrapper.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                    </svg>
                `;
            }

            const docObj = rvDocuments.find(d => d.id === id);
            const ext = data.filename.split('.').pop().toLowerCase();
            const esColabSoportado = ext === 'md' || ext === 'docx';
            
            const actionsDiv = document.getElementById('rv-preview-actions');
            if (actionsDiv) {
                let buttonsHtml = '';
                if (docObj && docObj.ipfs) {
                    const isEnc = docObj.ipfs.is_encrypted;
                    const cid = docObj.ipfs.cid;
                    const filename = docObj.filename;
                    
                    if (isEnc) {
                        buttonsHtml += `
                            <button onclick="desencriptarYVerDocumento(event, ${id}, '${cid}', '${filename}')" class="bg-amber-600 hover:bg-amber-700 text-white px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all shadow-sm active:scale-95 border border-amber-500 font-sans mr-2" title="Desencriptar archivo confidencial con su clave privada">
                                🔓 Desencriptar y Ver Original
                            </button>
                        `;
                    }
                }
                
                // Agregar botón de co-edición colaborativa si no está activa
                if (esColabSoportado && !data.is_collaborative) {
                    buttonsHtml += `
                        <button onclick="startNubeCollaboration(${data.id}, '${ext}')" class="bg-cyan-600 hover:bg-cyan-700 text-black px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all shadow-sm active:scale-95 font-sans" title="Iniciar sesión de edición colaborativa en CryptPad.fr">
                            ⚡ Co-Edición (CryptPad)
                        </button>
                    `;
                }
                
                actionsDiv.innerHTML = buttonsHtml;
            }

            // Lógica del Workflow de Aprobación Documental (Opción B)
            let workflowBannerHtml = '';
            const payload = getDecodedToken();
            const username = payload ? payload.sub : '';
            const role = payload ? payload.role : '';
            const isSenior = (username === 'starcontract') || (role === 'senior') || (role === 'admin') || (role === 'compliance');
            
            const docStatus = (data.status || 'draft').toLowerCase();
            
            if (docStatus === 'draft') {
                workflowBannerHtml = `
                    <div class="mb-4 p-3 rounded-xl bg-white/5 border border-white/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3 font-sans">
                        <div class="flex items-center gap-2 text-left">
                            <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-white/10 text-gray-300 shrink-0">📄 Borrador</span>
                            <span class="text-[11px] text-gray-400">Este contrato aún no ha sido enviado para aprobación de firmas.</span>
                        </div>
                        <button onclick="solicitarAprobacion(${data.id})" class="bg-cyan-500 hover:bg-cyan-600 active:scale-95 text-black font-bold rounded-lg transition-all shrink-0 font-sans" style="padding: 6px 12px !important; font-size: 11px !important; line-height: 1 !important; height: 30px !important; width: auto !important; min-height: 0 !important; min-width: 0 !important; display: inline-flex !important; align-items: center !important; gap: 4px !important;">
                            ✉️ Solicitar Aprobación
                        </button>
                    </div>
                `;
            } else if (docStatus === 'pending_approval') {
                if (isSenior) {
                    workflowBannerHtml = `
                        <div class="mb-4 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 flex flex-col gap-3 font-sans">
                            <div class="flex items-center justify-between">
                                <div class="flex items-center gap-2 text-left">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 animate-pulse shrink-0">⏳ Pendiente de Revisión</span>
                                    <span class="text-[11px] text-gray-300">Revisión requerida por Oficial de Cumplimiento.</span>
                                </div>
                            </div>
                            <div id="review-comment-box" class="hidden">
                                <textarea id="review-comments" placeholder="Escriba los comentarios o motivos de rechazo..." class="w-full h-16 p-2 rounded-lg bg-black/40 border border-white/10 text-[11px] text-white focus:outline-none focus:border-cyan-500 font-sans"></textarea>
                            </div>
                            <div class="flex items-center gap-2 justify-end">
                                <button id="btn-reject-trigger" onclick="mostrarCajaComentarios()" class="bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 font-bold rounded-lg transition-all font-sans" style="padding: 6px 12px !important; font-size: 11px !important; line-height: 1 !important; height: 30px !important; width: auto !important; min-height: 0 !important; min-width: 0 !important; display: inline-flex !important; align-items: center !important; gap: 4px !important;">
                                    ❌ Rechazar
                                </button>
                                <button id="btn-reject-confirm" onclick="enviarDecisionReview(${data.id}, 'reject')" class="hidden bg-red-600 hover:bg-red-700 text-white font-bold rounded-lg transition-all font-sans" style="padding: 6px 12px !important; font-size: 11px !important; line-height: 1 !important; height: 30px !important; width: auto !important; min-height: 0 !important; min-width: 0 !important; display: inline-flex !important; align-items: center !important; gap: 4px !important;">
                                    Confirmar Rechazo
                                </button>
                                <button onclick="enviarDecisionReview(${data.id}, 'approve')" class="bg-emerald-500 hover:bg-emerald-600 text-black font-bold rounded-lg transition-all font-sans" style="padding: 6px 12px !important; font-size: 11px !important; line-height: 1 !important; height: 30px !important; width: auto !important; min-height: 0 !important; min-width: 0 !important; display: inline-flex !important; align-items: center !important; gap: 4px !important;">
                                    ✅ Aprobar Contrato
                                </button>
                            </div>
                        </div>
                    `;
                } else {
                    workflowBannerHtml = `
                        <div class="mb-4 p-3 rounded-xl bg-amber-500/5 border border-amber-500/10 flex items-center justify-between gap-3 font-sans">
                            <div class="flex items-center gap-2 text-left">
                                <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/15 text-amber-400 shrink-0">⏳ En Revisión</span>
                                <span class="text-[11px] text-gray-400">El contrato está siendo auditado por un revisor Senior. El inicio de firmas se encuentra bloqueado de forma preventiva.</span>
                            </div>
                        </div>
                    `;
                }
            } else if (docStatus === 'approved') {
                workflowBannerHtml = `
                    <div class="mb-4 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex flex-col gap-1.5 font-sans">
                        <div class="flex items-center gap-2 text-left">
                            <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 shrink-0">✅ Aprobado para Firmas</span>
                            <span class="text-[11px] text-gray-300">Este contrato ha sido validado. Ya puedes iniciar la solicitud de firmas.</span>
                        </div>
                        ${data.comments ? `<p class="text-[10px] text-gray-400 italic">Comentarios: "${data.comments}"</p>` : ''}
                    </div>
                `;
            } else if (docStatus === 'rejected') {
                workflowBannerHtml = `
                    <div class="mb-4 p-4 rounded-xl bg-red-500/10 border border-red-500/20 flex flex-col gap-2 font-sans">
                        <div class="flex items-center gap-2 text-left">
                            <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-400 shrink-0">❌ Rechazado</span>
                            <span class="text-[11px] text-gray-300">Este contrato no fue aprobado. Corrija los motivos descritos y vuelva a solicitar revisión.</span>
                        </div>
                        <div class="p-2.5 rounded-lg bg-black/40 border border-white/5 text-[11px]">
                            <p class="text-gray-400 font-bold">Comentarios del Revisor:</p>
                            <p class="text-red-300 mt-1 italic">"${data.comments || 'No se ingresaron comentarios.'}"</p>
                        </div>
                        <div class="flex justify-end">
                            <button onclick="solicitarAprobacion(${data.id})" class="bg-cyan-500 hover:bg-cyan-600 active:scale-95 text-black font-bold rounded-lg transition-all shrink-0 font-sans" style="padding: 6px 12px !important; font-size: 11px !important; line-height: 1 !important; height: 30px !important; width: auto !important; min-height: 0 !important; min-width: 0 !important; display: inline-flex !important; align-items: center !important; gap: 4px !important;">
                                🔄 Reenviar para Aprobación
                            </button>
                        </div>
                    </div>
                `;
            } else if (docStatus === 'pending_signatures') {
                workflowBannerHtml = `
                    <div class="mb-4 p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-between gap-3 font-sans">
                        <div class="flex items-center gap-2 text-left">
                            <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-400 shrink-0">✍️ En Firmas</span>
                            <span class="text-[11px] text-gray-300">El proceso de firmas electrónicas está activo. Puede firmar ingresando al correo recibido.</span>
                        </div>
                    </div>
                `;
            } else if (docStatus === 'signed') {
                workflowBannerHtml = `
                    <div class="mb-4 p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-between gap-3 font-sans">
                        <div class="flex items-center gap-2 text-left">
                            <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-500/20 text-cyan-400 shrink-0">🔒 Firmado</span>
                            <span class="text-[11px] text-gray-300">Este contrato está firmado y anclado a la cadena de bloques / IPFS de forma inmutable.</span>
                        </div>
                    </div>
                `;
            }

            // Inyectar banner verde/cyan si la co-edición está activa
            let colabBannerHtml = '';
            if (data.is_collaborative) {
                colabBannerHtml = `
                    <div class="mb-4 p-4 rounded-xl bg-gradient-to-r from-emerald-500/20 to-teal-500/10 border border-emerald-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-lg shadow-emerald-950/10 animate-pulse font-sans">
                        <div class="flex items-start gap-2.5 text-left">
                            <div class="mt-0.5 p-1 bg-emerald-500/20 text-emerald-400 rounded-lg shrink-0">
                                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                                </svg>
                            </div>
                            <div>
                                <h5 class="text-xs font-bold text-emerald-400">Co-Edición en la Nube Activa</h5>
                                <p class="text-[10px] text-gray-300 mt-0.5 leading-normal">
                                    El equipo está co-editando este contrato en tiempo real en CryptPad.fr.
                                </p>
                            </div>
                        </div>
                        <div class="flex items-center gap-2 shrink-0 self-center">
                            <a href="${data.cryptpad_share_url}" target="_blank" class="bg-emerald-500 hover:bg-emerald-600 text-black font-bold rounded-lg flex items-center justify-center gap-1 transition-all hover:scale-[1.03] active:scale-95 shadow-sm no-underline font-sans" style="padding: 6px 12px !important; font-size: 11px !important; line-height: 1 !important; height: 30px !important; width: auto !important; min-height: 0 !important; min-width: 0 !important; display: inline-flex !important; align-items: center !important;">
                                🚀 Unirse
                            </a>
                            <button onclick="openFinalizeNubeModal(${data.id})" class="bg-purple-600 hover:bg-purple-700 text-white font-bold rounded-lg flex items-center justify-center gap-1 transition-all hover:scale-[1.03] active:scale-95 shadow-sm border border-purple-500/30 font-sans" style="padding: 6px 12px !important; font-size: 11px !important; line-height: 1 !important; height: 30px !important; width: auto !important; min-height: 0 !important; min-width: 0 !important; display: inline-flex !important; align-items: center !important;">
                                💾 Finalizar
                            </button>
                        </div>
                    </div>
                `;
            }

            contentDiv.innerHTML = colabBannerHtml + workflowBannerHtml + data.content_text;
        } else {
            contentDiv.innerHTML = '<p class="text-red-500 text-sm font-sans">Error al descargar el documento de la base de datos.</p>';
        }
    } catch (e) {
        console.error(e);
        contentDiv.innerHTML = '<p class="text-red-500 text-sm font-sans">Fallo al conectar con el servidor.</p>';
    }
}

window.descargarDocumentoDesencriptado = async function(cid, filename) {
    const token = localStorage.getItem("access_token");
    if (window.showToast) {
        window.showToast("Iniciando descarga desencriptada...", "info");
    }
    try {
        const res = await fetch(`/ipfs/download/${cid}?decrypt=true`, {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
            if (window.showToast) {
                window.showToast("Descarga completada con éxito", "success");
            }
        } else {
            const err = await res.json();
            _vaultNotify("Error al descargar: " + (err.detail || "Desconocido"));
        }
    } catch (e) {
        console.error(e);
        _vaultNotify("Fallo al conectar con el servidor para la descarga.");
    }
}

window.descargarBlobLocal = function(blobUrl, name) {
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
}

window.desencriptarYVerDocumento = async function(event, docId, cid, filename) {
    if (event) event.stopPropagation();
    
    const token = localStorage.getItem("access_token");
    const contentDiv = document.getElementById('rv-preview-content');
    const originalContent = contentDiv.innerHTML;
    
    const isZkEncrypted = filename.endsWith('.zkenc');
    
    if (isZkEncrypted) {
        const password = prompt("🔐 Este archivo está cifrado con Zero-Knowledge en cliente.\n\nSTAR-DOC no tiene la clave ni puede acceder a su contenido. Ingrese la contraseña de seguridad para descifrarlo localmente:");
        if (!password) {
            _vaultNotify("Operación cancelada.");
            return;
        }

        contentDiv.innerHTML = `
            <div class="flex flex-col items-center justify-center p-12 space-y-4">
                <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-500"></div>
                <p class="text-xs text-amber-550 font-semibold font-sans">Descargando bloques cifrados y descifrando localmente con AES-GCM...</p>
            </div>
        `;

        try {
            // Descargar el archivo encriptado raw (decrypt=false)
            const response = await fetch(`/ipfs/download/${cid}?decrypt=false`, {
                headers: { 'Authorization': 'Bearer ' + token }
            });

            if (!response.ok) {
                throw new Error("No se pudo descargar el archivo encriptado desde IPFS.");
            }

            const encryptedBlob = await response.blob();
            const decryptedBlob = await zkDecryptFile(encryptedBlob, password);

            // Nombre sin .zkenc
            const origFilename = filename.substring(0, filename.length - 6);
            const ext = origFilename.split('.').pop().toLowerCase();
            const textExtensions = ['txt', 'md', 'json', 'xml', 'html', 'css', 'js', 'py', 'sh', 'sql', 'csv'];
            const isText = textExtensions.includes(ext);

            const localUrl = window.URL.createObjectURL(decryptedBlob);

            if (isText) {
                const textContent = await decryptedBlob.text();
                contentDiv.innerHTML = `
                    <div class="mb-4 p-4 rounded-xl bg-amber-500/10 border border-amber-500/25 text-amber-300 font-sans text-left">
                        <h4 class="text-xs font-bold flex items-center gap-1.5">
                            ✓ Descifrado Zero-Knowledge Exitoso (Local)
                        </h4>
                        <p class="text-[10px] mt-1 text-amber-400">
                            El archivo ha sido descifrado en la memoria de su navegador de forma segura. La plataforma nunca conoció la clave de descifrado.
                        </p>
                    </div>
                    <div class="mb-4 text-left">
                        <button onclick="descargarBlobLocal('${localUrl}', '${origFilename}')" class="bg-amber-600 hover:bg-amber-700 text-white font-bold py-1.5 px-3 rounded-lg text-[10px] flex items-center gap-1 transition-all border border-amber-500 font-sans">
                            📥 Descargar Copia Descifrada
                        </button>
                    </div>
                    <div class="p-4 border border-white/10 rounded-xl bg-white/5 overflow-auto font-mono text-xs text-left">
                        ${textContent}
                    </div>
                `;
            } else {
                contentDiv.innerHTML = `
                    <div class="mb-4 p-4 rounded-xl bg-amber-500/10 border border-amber-500/25 text-amber-300 font-sans text-left">
                        <h4 class="text-xs font-bold flex items-center gap-1.5">
                            ✓ Descifrado Zero-Knowledge Exitoso (Local)
                        </h4>
                        <p class="text-[10px] mt-1 text-amber-400">
                            El archivo ha sido descifrado en la memoria de su navegador de forma segura. La plataforma nunca conoció la clave de descifrado.
                        </p>
                    </div>
                    
                    <div class="p-6 border border-amber-500/30 rounded-xl bg-amber-500/5 text-center font-sans space-y-4 shadow-lg max-w-md mx-auto my-8">
                        <div class="w-16 h-16 bg-amber-500/10 rounded-full flex items-center justify-center mx-auto text-amber-400 border border-amber-500/20">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                        </div>
                        <div class="space-y-1">
                            <h4 class="text-xs font-bold text-amber-400 uppercase tracking-wider">Archivo Binario Descifrado</h4>
                            <p class="text-[11px] text-gray-300">
                                El archivo <span class="font-semibold text-white">${origFilename}</span> ha sido descifrado exitosamente localmente.
                            </p>
                        </div>
                        <div class="pt-2">
                            <button onclick="descargarBlobLocal('${localUrl}', '${origFilename}')" class="w-full bg-amber-600 hover:bg-amber-700 text-white font-bold py-2.5 px-4 rounded-xl text-xs flex items-center justify-center gap-2 transition-all active:scale-95 shadow-md border border-amber-500 font-sans">
                                Descargar Archivo Descifrado
                            </button>
                        </div>
                    </div>
                `;
            }
            _vaultNotify("✓ Archivo descifrado exitosamente de forma local.");
        } catch (decErr) {
            console.error("Error al descifrar localmente:", decErr);
            _vaultNotify("❌ Error al descifrar el archivo. Verifique la contraseña.");
            contentDiv.innerHTML = originalContent;
        }
        return;
    }

    contentDiv.innerHTML = `
        <div class="flex flex-col items-center justify-center p-12 space-y-4">
            <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400"></div>
            <p class="text-xs text-indigo-450 font-semibold font-sans">Desencriptando bloques y verificando firmas IPFS...</p>
        </div>
    `;

    try {
        const response = await fetch(`/ipfs/decrypt/${cid}`, {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });

        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                // Determinar si es texto plano o binario según extensión
                const ext = filename.split('.').pop().toLowerCase();
                const textExtensions = ['txt', 'md', 'json', 'xml', 'html', 'css', 'js', 'py', 'sh', 'sql', 'csv'];
                const isText = textExtensions.includes(ext);

                if (isText) {
                    contentDiv.innerHTML = `
                        <div class="mb-4 p-4 rounded-xl bg-green-500/10 border border-green-500/25 text-green-300 font-sans text-left">
                            <h4 class="text-xs font-bold flex items-center gap-1.5">
                                ✓ Documento Desencriptado Exitosamente
                            </h4>
                            <p class="text-[10px] mt-1 text-green-400">
                                El archivo ha sido recuperado en memoria temporal y su firma criptográfica coincide con el registro original.
                            </p>
                        </div>
                        <div class="mb-4 text-left">
                            <button onclick="descargarDocumentoDesencriptado('${cid}', '${filename}')" class="bg-indigo-650 hover:bg-indigo-750 text-white font-bold py-1.5 px-3 rounded-lg text-[10px] flex items-center gap-1 transition-all border border-indigo-500 font-sans">
                                📥 Descargar Copia Desencriptada
                            </button>
                        </div>
                        <div class="p-4 border border-white/10 rounded-xl bg-white/5 overflow-auto font-mono text-xs text-left">
                            ${data.decrypted_content}
                        </div>
                    `;
                } else {
                    // Es un archivo binario (PDF, DOCX, etc.)
                    contentDiv.innerHTML = `
                        <div class="mb-4 p-4 rounded-xl bg-green-500/10 border border-green-500/25 text-green-300 font-sans text-left">
                            <h4 class="text-xs font-bold flex items-center gap-1.5">
                                ✓ Documento Desencriptado Exitosamente
                            </h4>
                            <p class="text-[10px] mt-1 text-green-400">
                                El archivo ha sido recuperado en memoria temporal y su firma criptográfica coincide con el registro original.
                            </p>
                        </div>
                        
                        <div class="p-6 border border-emerald-500/30 rounded-xl bg-emerald-500/5 text-center font-sans space-y-4 shadow-lg max-w-md mx-auto my-8">
                            <div class="w-16 h-16 bg-emerald-500/10 rounded-full flex items-center justify-center mx-auto text-emerald-400 border border-emerald-500/20">
                                <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                </svg>
                            </div>
                            <div class="space-y-1">
                                <h4 class="text-xs font-bold text-emerald-405 uppercase tracking-wider">Archivo Binario Desencriptado</h4>
                                <p class="text-[11px] text-gray-300">
                                    El archivo <span class="font-semibold text-white">${filename}</span> no es texto plano y no se puede previsualizar directamente, pero ha sido desencriptado en memoria local con éxito.
                                </p>
                            </div>
                            <div class="pt-2">
                                <button onclick="descargarDocumentoDesencriptado('${cid}', '${filename}')" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2.5 px-4 rounded-xl text-xs flex items-center justify-center gap-2 transition-all active:scale-95 shadow-md border border-emerald-500 font-sans">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                    </svg>
                                    Descargar Archivo Original Desencriptado
                                </button>
                            </div>
                        </div>
                    `;
                }
            } else {
                _vaultNotify("No se pudo desencriptar el documento.");
                contentDiv.innerHTML = originalContent;
            }
        } else {
            const err = await response.json();
            _vaultNotify("Error al desencriptar: " + (err.detail || "Error del servidor"));
            contentDiv.innerHTML = originalContent;
        }
    } catch (e) {
        console.error(e);
        _vaultNotify("Fallo de red al solicitar desencriptación.");
        contentDiv.innerHTML = originalContent;
    }
}

function clearRvPreview() {
    document.getElementById('rv-preview-header').classList.add('hidden');
    const contentDiv = document.getElementById('rv-preview-content');
    contentDiv.innerHTML = `
        <div class="h-full flex flex-col items-center justify-center text-gray-400 space-y-4">
            <div class="p-6 bg-white/5 rounded-full">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 sm:h-16 sm:w-16 opacity-40 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
            </div>
            <p class="text-xs sm:text-sm font-medium text-center px-4 max-w-sm font-sans text-gray-400">
                Selecciona un documento del panel izquierdo para ver su contenido, o un expediente para inspeccionar su bitácora criptográfica e historial de cadena de custodia.
            </p>
        </div>
    `;
    _showMobileList();
}

window.deleteDocument = async function (e, id) {
    e.stopPropagation();
    if (!confirm("¿Estás seguro de eliminar este documento de tu Bóveda RAG? Se perderá el contexto para la IA.")) return;

    const token = localStorage.getItem("access_token");
    try {
        const res = await fetch(`/api/documents/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            if (window.showToast) window.showToast('Documento eliminado', 'success');
            clearRvPreview();
            fetchVaultDocuments();
        }
    } catch (error) {
        console.error(error);
    }
}

// Funciones Criptográficas Zero-Knowledge AES-GCM en Cliente (PBKDF2 + AES-GCM 256 bits)
async function _zkDeriveKey(password, salt) {
    const encoder = new TextEncoder();
    const baseKey = await window.crypto.subtle.importKey(
        "raw",
        encoder.encode(password),
        "PBKDF2",
        false,
        ["deriveKey"]
    );
    return window.crypto.subtle.deriveKey(
        {
            name: "PBKDF2",
            salt: salt,
            iterations: 100000,
            hash: "SHA-256"
        },
        baseKey,
        { name: "AES-GCM", length: 256 },
        false,
        ["encrypt", "decrypt"]
    );
}

async function zkEncryptFile(file, password) {
    const arrayBuffer = await file.arrayBuffer();
    const salt = window.crypto.getRandomValues(new Uint8Array(16));
    const iv = window.crypto.getRandomValues(new Uint8Array(12));
    const key = await _zkDeriveKey(password, salt);
    
    const encryptedContent = await window.crypto.subtle.encrypt(
        { name: "AES-GCM", iv: iv },
        key,
        arrayBuffer
    );
    
    // Concatenar Salt (16B) + IV (12B) + Contenido Cifrado
    const encryptedBytes = new Uint8Array(salt.byteLength + iv.byteLength + encryptedContent.byteLength);
    encryptedBytes.set(salt, 0);
    encryptedBytes.set(iv, salt.byteLength);
    encryptedBytes.set(new Uint8Array(encryptedContent), salt.byteLength + iv.byteLength);
    
    return new Blob([encryptedBytes], { type: "application/octet-stream" });
}

async function zkDecryptFile(encryptedBlob, password) {
    const arrayBuffer = await encryptedBlob.arrayBuffer();
    const salt = new Uint8Array(arrayBuffer, 0, 16);
    const iv = new Uint8Array(arrayBuffer, 16, 12);
    const encryptedData = new Uint8Array(arrayBuffer, 28);
    
    const key = await _zkDeriveKey(password, salt);
    const decryptedContent = await window.crypto.subtle.decrypt(
        { name: "AES-GCM", iv: iv },
        key,
        encryptedData
    );
    
    return new Blob([decryptedContent]);
}

window.uploadToVault = async function (event) {
    let file = event.target.files[0];
    if (!file) return;

    const token = localStorage.getItem("access_token");
    if (!token) return;

    const anchorIpfs = document.getElementById('rv-anchor-ipfs').checked;
    const classification = document.getElementById('rv-classification').value;

    // FASE 3: Privacidad Zero-Knowledge en Cliente
    if (classification === 'confidential') {
        const password = prompt("🔐 Defina una contraseña de seguridad (Zero-Knowledge) para cifrar este archivo.\n\nSTAR-DOC NO almacenará esta contraseña en sus servidores y solo usted podrá descifrar el documento para ver su contenido:");
        if (!password) {
            _vaultNotify("Subida cancelada. Los archivos confidenciales requieren contraseña para su cifrado local.");
            event.target.value = '';
            return;
        }
        
        try {
            document.getElementById('rv-doc-list').innerHTML = '<div class="flex flex-col items-center justify-center p-8 space-y-3"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-500"></div><p class="text-xs text-amber-500 font-medium">Cifrando archivo localmente con AES-GCM 256 bits...</p></div>';
            const encryptedBlob = await zkEncryptFile(file, password);
            file = new File([encryptedBlob], file.name + ".zkenc", { type: "application/octet-stream" });
            _vaultNotify("✓ Archivo cifrado localmente con éxito.");
        } catch (encErr) {
            console.error("Error cifrando archivo:", encErr);
            _vaultNotify("❌ Error al cifrar el archivo localmente.");
            fetchVaultDocuments();
            event.target.value = '';
            return;
        }
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("anchor_ipfs", anchorIpfs);
    formData.append("classification", classification);

    document.getElementById('rv-doc-list').innerHTML = '<div class="flex flex-col items-center justify-center p-8 space-y-3"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div><p class="text-xs text-indigo-600 font-medium">Interpretando y asegurando documento...</p></div>';

    try {
        const res = await fetch('/api/documents/upload', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token },
            body: formData
        });

        if (res.ok) {
            fetchVaultDocuments();
            if (window.appIaReference && typeof window.appIaReference.reloadKnowledgeFiles === 'function') {
                window.appIaReference.reloadKnowledgeFiles();
            }
        } else {
            const err = await res.json();
            _vaultNotify('Error al subir: ' + (err.detail || 'Desconocido'));
            fetchVaultDocuments();
        }
    } catch (e) {
        console.error(e);
        _vaultNotify('Error al procesar el archivo.');
        fetchVaultDocuments();
    }

    event.target.value = '';
}

window.uploadFolderToVault = async function (event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    const folderName = prompt("Ingrese el nombre del Expediente para esta carpeta:", files[0].webkitRelativePath.split('/')[0] || "Nuevo Expediente");
    if (!folderName) {
        event.target.value = '';
        return;
    }

    const token = localStorage.getItem("access_token");
    if (!token) return;

    const classification = document.getElementById('rv-classification').value;

    const formData = new FormData();
    formData.append("classification", classification);
    formData.append("folder_name", folderName);
    for (let i = 0; i < files.length; i++) {
        formData.append("files", files[i]);
    }

    document.getElementById('rv-doc-list').innerHTML = '<div class="flex flex-col items-center justify-center p-8 space-y-3"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div><p class="text-xs text-indigo-600 font-medium">Subiendo carpeta y creando expediente criptográfico...</p></div>';

    try {
        const res = await fetch('/ipfs/upload-folder', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token },
            body: formData
        });

        if (res.ok) {
            const data = await res.json();
            if (window.showToast) window.showToast(`Expediente "${data.folder_name}" creado con éxito en IPFS.`, 'success');
            fetchVaultDocuments();
            switchVaultTab('audits');
        } else {
            const err = await res.json();
            _vaultNotify('Error al subir carpeta: ' + (err.detail || 'Desconocido'));
            fetchVaultDocuments();
        }
    } catch (e) {
        console.error(e);
        _vaultNotify('Error al procesar la carpeta.');
        fetchVaultDocuments();
    }

    event.target.value = '';
}

// AJUSTES Y MANTENIMIENTO AVANZADO IPFS
let activeMaintOption = 'stats';

window.selectMantenimientoOption = function (option) {
    activeMaintOption = option;
    const optStats = document.getElementById('maint-opt-stats');
    const optIpns = document.getElementById('maint-opt-ipns');
    const optWebhooks = document.getElementById('maint-opt-webhooks');

    if (optStats) {
        optStats.className = "group relative p-3 rounded-xl bg-white/5 border border-white/10 hover:border-cyan-500/30 shadow-sm hover:shadow-md transition-all cursor-pointer flex items-center gap-3";
    }
    if (optIpns) {
        optIpns.className = "group relative p-3 rounded-xl bg-white/5 border border-white/10 hover:border-cyan-500/30 shadow-sm hover:shadow-md transition-all cursor-pointer flex items-center gap-3";
    }
    if (optWebhooks) {
        optWebhooks.className = "group relative p-3 rounded-xl bg-white/5 border border-white/10 hover:border-cyan-500/30 shadow-sm hover:shadow-md transition-all cursor-pointer flex items-center gap-3";
    }

    const selectedOpt = document.getElementById(`maint-opt-${option}`);
    if (selectedOpt) {
        selectedOpt.className = "group relative p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/40 shadow-sm hover:shadow-md transition-all cursor-pointer flex items-center gap-3";
    }

    if (option === 'stats') {
        showMantenimientoStats();
    } else if (option === 'ipns') {
        showIPNSKeys();
    } else if (option === 'webhooks') {
        showWebhooks();
    }
}

window.showMantenimientoStats = async function () {
    const token = localStorage.getItem("access_token");
    const contentDiv = document.getElementById('rv-preview-content');
    contentDiv.innerHTML = '<div class="flex justify-center mt-20"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400"></div></div>';

    document.getElementById('rv-preview-header').classList.remove('hidden');
    document.getElementById('rv-preview-title').textContent = "Estadísticas del Repositorio IPFS";
    document.getElementById('rv-preview-meta').textContent = "Mantenimiento del nodo local Kubo";
    const wrapper = document.getElementById('rv-preview-icon-wrapper');
    if (wrapper) {
        wrapper.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
        `;
    }

    try {
        const res = await fetch('/ipfs/repo/stats', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            const stats = await res.json();
            const sizeMB = (stats.RepoSize / (1024 * 1024)).toFixed(2);
            const maxMB = (stats.StorageMax / (1024 * 1024)).toFixed(2);
            const usagePercent = Math.min(((stats.RepoSize / stats.StorageMax) * 100), 100).toFixed(1);

            contentDiv.innerHTML = `
                <div class="p-6 max-w-xl mx-auto space-y-6 font-sans text-left">
                    <div class="bg-gradient-to-br from-indigo-500/15 to-purple-500/10 rounded-2xl p-5 border border-indigo-500/20 shadow-sm relative overflow-hidden">
                        <div class="absolute right-0 top-0 translate-x-4 -translate-y-4 opacity-5 text-indigo-400">
                            <svg class="w-36 h-36" fill="currentColor" viewBox="0 0 20 20"><path d="M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z"></path><path d="M12 2.252A8.014 8.014 0 0117.748 8H12V2.252z"></path></svg>
                        </div>
                        <h4 class="text-sm font-bold text-white uppercase tracking-wider mb-3">Capacidad de Almacenamiento</h4>
                        <div class="flex justify-between text-xs text-indigo-300 font-semibold mb-1">
                            <span>Espacio Utilizado: ${sizeMB} MB</span>
                            <span>Límite: ${maxMB} MB</span>
                        </div>
                        <div class="w-full bg-white/10 rounded-full h-2.5 overflow-hidden mb-2">
                            <div class="bg-indigo-500 h-2.5 rounded-full" style="width: ${usagePercent}%"></div>
                        </div>
                        <div class="text-[10px] text-indigo-400 font-medium flex justify-between">
                            <span>Uso del Repositorio: ${usagePercent}%</span>
                            <span>Objetos Guardados: ${stats.NumObjects}</span>
                        </div>
                    </div>

                    <div class="bg-white/5 rounded-xl border border-white/10 p-5 shadow-sm space-y-4">
                        <h4 class="text-xs font-bold text-white uppercase tracking-wider font-sans">Mantenimiento y Garbage Collection</h4>
                        <p class="text-xs text-gray-400 leading-relaxed font-sans">
                            IPFS almacena bloques localmente. Ejecutar el recolector de basura (Garbage Collection) elimina de forma segura los bloques huérfanos que no están anclados (pinned), liberando espacio en el disco duro del servidor de STAR-DOC.
                        </p>
                        <div class="pt-2">
                            <button onclick="runGarbageCollection(this)" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold px-4 py-2 rounded-xl text-xs flex items-center gap-1.5 transition-all shadow-sm active:scale-95">
                                🧹 Ejecutar Garbage Collection
                            </button>
                        </div>
                    </div>
                    
                    <div class="text-[10px] text-gray-500 font-mono space-y-1">
                        <p>Ruta Repo: ${stats.RepoPath || 'N/A'}</p>
                        <p>Kubo Versión: ${stats.Version || 'N/A'}</p>
                    </div>
                </div>
            `;
        } else {
            contentDiv.innerHTML = '<p class="text-red-500 text-sm font-sans">Error al consultar estadísticas del nodo local.</p>';
        }
    } catch (e) {
        console.error(e);
        contentDiv.innerHTML = '<p class="text-red-500 text-sm font-sans">Fallo al conectar con el endpoint de estadísticas.</p>';
    }
}

window.runGarbageCollection = async function (btn) {
    const token = localStorage.getItem("access_token");
    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `
        <svg class="animate-spin h-3.5 w-3.5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        Limpiando Repositorio...
    `;

    try {
        const res = await fetch('/ipfs/gc', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            _vaultNotify(`✓ Garbage Collection Ejecutado:\nSe han liberado bloques no referenciados correctamente.`);
            showMantenimientoStats();
        } else {
            const err = await res.json();
            _vaultNotify("Error en GC: " + (err.detail || "Desconocido"));
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    } catch (e) {
        console.error(e);
        _vaultNotify("Error al ejecutar Garbage Collection.");
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

window.showIPNSKeys = async function () {
    const token = localStorage.getItem("access_token");
    const contentDiv = document.getElementById('rv-preview-content');
    contentDiv.innerHTML = '<div class="flex justify-center mt-20"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400"></div></div>';

    document.getElementById('rv-preview-header').classList.remove('hidden');
    document.getElementById('rv-preview-title').textContent = "Versionado Criptográfico (IPNS)";
    document.getElementById('rv-preview-meta').textContent = "Claves criptográficas y direcciones mutables";
    const wrapper = document.getElementById('rv-preview-icon-wrapper');
    if (wrapper) {
        wrapper.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
        `;
    }

    try {
        const res = await fetch('/ipfs/ipns/keys', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            const keys = await res.json();
            
            let tableRows = keys.map(key => {
                const dateStr = key.last_published_at ? new Date(key.last_published_at).toLocaleString() : 'Nunca';
                return `
                    <tr class="border-b border-white/5 hover:bg-white/5 transition-colors font-sans text-xs">
                        <td class="px-3 py-2.5 text-white font-semibold truncate max-w-[100px]">${key.key_name}</td>
                        <td class="px-3 py-2.5 text-gray-400 font-mono text-[10px] truncate max-w-[130px]" title="${key.ipns_id}">${key.ipns_id}</td>
                        <td class="px-3 py-2.5 text-cyan-400 font-mono text-[10px] truncate max-w-[100px]" title="${key.current_cid || ''}">${key.current_cid || 'Sin CID'}</td>
                        <td class="px-3 py-2.5 text-gray-500 text-[10px]">${dateStr}</td>
                        <td class="px-3 py-2.5 text-right">
                            <div class="flex justify-end gap-1.5 font-sans">
                                <button onclick="publishToIPNSKey('${key.key_name}')" class="px-2 py-1 bg-indigo-600/20 text-indigo-400 hover:bg-indigo-600 hover:text-white rounded-lg text-[10px] font-bold transition-all" title="Publicar nueva versión">
                                    Publicar CID
                                </button>
                                <button onclick="resolveIPNSKey('${key.ipns_id}')" class="px-2 py-1 bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600 hover:text-white rounded-lg text-[10px] font-bold transition-all" title="Resolver destino actual">
                                    Resolver
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');

            if (keys.length === 0) {
                tableRows = `
                    <tr>
                        <td colspan="5" class="px-4 py-8 text-center text-gray-400 text-xs font-sans">
                            No hay claves IPNS generadas. Use el formulario superior para crear una clave.
                        </td>
                    </tr>
                `;
            }

            contentDiv.innerHTML = `
                <div class="p-4 sm:p-6 space-y-6 font-sans text-left">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div class="bg-white/5 rounded-xl border border-white/10 p-4 shadow-sm space-y-3">
                            <h4 class="text-xs font-bold text-white uppercase tracking-wider font-sans">Generar Clave de Versionado</h4>
                            <div class="flex gap-2">
                                <input type="text" id="ipns-new-key-name" placeholder="Nombre de clave (ej. contrato_arriendo)" class="flex-1 px-3 py-1.5 text-xs rounded-lg bg-slate-900 border border-white/10 focus:outline-none focus:ring-1 focus:ring-indigo-500 text-white font-sans">
                                <button onclick="generateIPNSKey(this)" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold px-3 py-1.5 rounded-lg text-xs transition-all active:scale-95 font-sans">
                                    Generar
                                </button>
                            </div>
                        </div>
                        <div class="bg-indigo-500/10 rounded-xl border border-indigo-500/20 p-4 shadow-sm flex flex-col justify-between">
                            <div>
                                <h4 class="text-xs font-bold text-white uppercase tracking-wider font-sans">Redirecciones Mutables</h4>
                                <p class="text-[10px] sm:text-xs text-indigo-300 mt-1 font-sans">
                                    IPFS es inmutable por diseño. IPNS crea un hash único persistente que apunta dinámicamente al CID del documento/contrato que consideres su "última versión".
                                </p>
                            </div>
                            <div class="pt-2">
                                <button onclick="republishAllIPNSKeys(this)" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold px-3 py-1.5 rounded-lg text-xs transition-all active:scale-95 flex items-center gap-1.5 font-sans">
                                    🔄 Forzar Republicación Global
                                </button>
                            </div>
                        </div>
                    </div>

                    <div class="bg-white/5 rounded-xl border border-white/10 shadow-sm overflow-hidden">
                        <div class="px-4 py-3 bg-white/5 border-b border-white/10">
                            <h4 class="text-xs font-bold text-white uppercase tracking-wider font-sans">Listado de Claves Registradas</h4>
                        </div>
                        <div class="w-full overflow-x-auto">
                            <table class="min-w-full bg-transparent font-sans">
                                <thead class="bg-white/5 border-b border-white/10 text-[10px] text-gray-400 uppercase tracking-wider font-bold text-left">
                                    <tr>
                                        <th class="px-3 py-2.5">Clave / Nombre</th>
                                        <th class="px-3 py-2.5">ID IPNS (Nombre Mutable)</th>
                                        <th class="px-3 py-2.5">CID de Versión Actual</th>
                                        <th class="px-3 py-2.5">Última Publicación</th>
                                        <th class="px-3 py-2.5"></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${tableRows}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            `;
        } else {
            contentDiv.innerHTML = '<p class="text-red-500 text-sm font-sans">Error al obtener las claves IPNS de base de datos.</p>';
        }
    } catch (e) {
        console.error(e);
        contentDiv.innerHTML = '<p class="text-red-500 text-sm font-sans">Fallo al conectar con el servidor.</p>';
    }
}

window.generateIPNSKey = async function (btn) {
    const nameInput = document.getElementById('ipns-new-key-name');
    const keyName = nameInput.value.trim();
    if (!keyName) {
        _vaultNotify("Por favor ingrese un nombre para la clave.");
        return;
    }

    const token = localStorage.getItem("access_token");
    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = 'Generando...';

    try {
        const res = await fetch(`/ipfs/ipns/key?key_name=${encodeURIComponent(keyName)}`, {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            _vaultNotify(`✓ Clave IPNS '${keyName}' generada con éxito.`);
            showIPNSKeys();
        } else {
            const err = await res.json();
            _vaultNotify("Error: " + (err.detail || "No se pudo crear la clave."));
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    } catch (e) {
        console.error(e);
        _vaultNotify("Error al procesar la clave.");
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

window.republishAllIPNSKeys = async function (btn) {
    const token = localStorage.getItem("access_token");
    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = 'Republicando...';

    try {
        const res = await fetch('/ipfs/ipns/republish-all', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            const data = await res.json();
            _vaultNotify(`✓ Republicación iniciada:\nSe han republicado ${data.republished_count} claves IPNS activas.`);
            showIPNSKeys();
        } else {
            _vaultNotify("Error al republicar las claves.");
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    } catch (e) {
        console.error(e);
        _vaultNotify("Error al contactar el servidor.");
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

window.resolveIPNSKey = async function (ipnsId) {
    try {
        const res = await fetch(`/ipfs/ipns/resolve?ipns_name=${encodeURIComponent(ipnsId)}`);
        if (res.ok) {
            const data = await res.json();
            _vaultNotify(`✓ Nombre IPNS Resuelto:\n\nNombre Mutable:\n${ipnsId}\n\nDestino (CID Inmutable):\n${data.current_cid}\n\nURL de acceso:\n${data.gateway_url}`);
        } else {
            _vaultNotify("No se pudo resolver el nombre IPNS en la red actual.");
        }
    } catch (e) {
        console.error(e);
        _vaultNotify("Error al resolver IPNS.");
    }
}

window.publishToIPNSKey = async function (keyName) {
    const cid = prompt("Ingrese el CID inmutable de IPFS que desea asignar a esta clave mutable (IPNS):");
    if (!cid) return;

    const token = localStorage.getItem("access_token");
    try {
        const res = await fetch(`/ipfs/ipns/publish?key_name=${encodeURIComponent(keyName)}&cid=${encodeURIComponent(cid)}`, {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            const data = await res.json();
            _vaultNotify(`✓ Versión Publicada exitosamente!\nNombre IPNS: ${data.ipns_name}\nAhora apunta a: ${data.target_cid}`);
            showIPNSKeys();
        } else {
            const err = await res.json();
            _vaultNotify("Error al publicar: " + (err.detail || "Desconocido"));
        }
    } catch (e) {
        console.error(e);
        _vaultNotify("Error al enviar la solicitud.");
    }
}

window.showWebhooks = async function () {
    const token = localStorage.getItem("access_token");
    const contentDiv = document.getElementById('rv-preview-content');
    contentDiv.innerHTML = '<div class="flex justify-center mt-20"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400"></div></div>';

    document.getElementById('rv-preview-header').classList.remove('hidden');
    document.getElementById('rv-preview-title').textContent = "Webhooks de Integración";
    document.getElementById('rv-preview-meta').textContent = "Notificaciones automáticas ante eventos criptográficos";
    const wrapper = document.getElementById('rv-preview-icon-wrapper');
    if (wrapper) {
        wrapper.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
        `;
    }

    try {
        const res = await fetch('/ipfs/webhooks', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            const subs = await res.json();
            
            let tableRows = subs.map(sub => {
                const eventsBadge = sub.events.map(ev => {
                    let color = 'bg-white/5 text-gray-400';
                    if (ev === 'upload') color = 'bg-green-500/10 text-green-400 border border-green-500/20';
                    if (ev === 'download') color = 'bg-blue-500/10 text-blue-400 border border-blue-500/20';
                    if (ev === 'archive') color = 'bg-amber-500/10 text-amber-400 border border-amber-500/20';
                    if (ev === 'publish_ipns') color = 'bg-purple-500/10 text-purple-400 border border-purple-500/20';
                    return `<span class="px-1.5 py-0.5 rounded-md text-[9px] font-bold font-sans uppercase border ${color}">${ev}</span>`;
                }).join(' ');

                return `
                    <tr class="border-b border-white/5 hover:bg-white/5 transition-colors font-sans text-xs">
                        <td class="px-3 py-2.5 text-white font-semibold truncate max-w-[100px]">${sub.name}</td>
                        <td class="px-3 py-2.5 text-gray-400 font-mono text-[10px] truncate max-w-[200px]" title="${sub.url}">${sub.url}</td>
                        <td class="px-3 py-2.5 text-gray-500 font-mono text-[10px] truncate max-w-[80px]" title="${sub.secret}">${sub.secret}</td>
                        <td class="px-3 py-2.5">${eventsBadge}</td>
                        <td class="px-3 py-2.5 text-right">
                            <button onclick="deleteWebhookSubscription(${sub.id})" class="p-1 rounded text-red-400 hover:bg-white/10 focus:outline-none" title="Eliminar Webhook">
                                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');

            if (subs.length === 0) {
                tableRows = `
                    <tr>
                        <td colspan="5" class="px-4 py-8 text-center text-gray-400 text-xs font-sans">
                            No hay webhooks registrados. Registre uno usando el formulario superior.
                        </td>
                    </tr>
                `;
            }

            contentDiv.innerHTML = `
                <div class="p-4 sm:p-6 space-y-6 font-sans text-left">
                    <div class="bg-white/5 rounded-xl border border-white/10 p-5 shadow-sm space-y-4">
                        <h4 class="text-xs font-bold text-white uppercase tracking-wider font-sans">Registrar Nuevo Webhook</h4>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div class="space-y-3">
                                <div>
                                    <label class="block text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1 font-sans">URL de Destino</label>
                                    <input type="text" id="wh-url" placeholder="https://mi-servidor.com/webhook" class="w-full px-3 py-1.5 text-xs rounded-lg bg-slate-900 border border-white/10 focus:outline-none focus:ring-1 focus:ring-indigo-500 text-white font-sans">
                                </div>
                                <div>
                                    <label class="block text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1 font-sans">Clave Secreta HMAC (Opcional)</label>
                                    <input type="text" id="wh-secret" placeholder="Deje en blanco para auto-generar" class="w-full px-3 py-1.5 text-xs rounded-lg bg-slate-900 border border-white/10 focus:outline-none focus:ring-1 focus:ring-indigo-500 text-white font-sans">
                                </div>
                            </div>
                            <div class="flex flex-col justify-between">
                                <div>
                                    <label class="block text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2 font-sans">Eventos a Escuchar</label>
                                    <div class="grid grid-cols-2 gap-2 text-xs text-gray-400">
                                        <label class="flex items-center gap-1.5 cursor-pointer font-sans">
                                            <input type="checkbox" id="wh-ev-upload" class="rounded border-white/20 bg-white/5 text-cyan-500 focus:ring-cyan-500" checked>
                                            Subida (upload)
                                        </label>
                                        <label class="flex items-center gap-1.5 cursor-pointer font-sans">
                                            <input type="checkbox" id="wh-ev-download" class="rounded border-white/20 bg-white/5 text-cyan-500 focus:ring-cyan-500" checked>
                                            Descarga (download)
                                        </label>
                                        <label class="flex items-center gap-1.5 cursor-pointer font-sans">
                                            <input type="checkbox" id="wh-ev-archive" class="rounded border-white/20 bg-white/5 text-cyan-500 focus:ring-cyan-500">
                                            Despineado (archive)
                                        </label>
                                        <label class="flex items-center gap-1.5 cursor-pointer font-sans">
                                            <input type="checkbox" id="wh-ev-ipns" class="rounded border-white/20 bg-white/5 text-cyan-500 focus:ring-cyan-500">
                                            IPNS (publish_ipns)
                                        </label>
                                    </div>
                                </div>
                                <div class="pt-3">
                                    <button onclick="createWebhookSubscription(this)" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold px-4 py-2 rounded-xl text-xs transition-all shadow-sm active:scale-95 font-sans">
                                        ✓ Registrar Suscripción
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="bg-white/5 rounded-xl border border-white/10 shadow-sm overflow-hidden">
                        <div class="px-4 py-3 bg-white/5 border-b border-white/10">
                            <h4 class="text-xs font-bold text-white uppercase tracking-wider font-sans">Webhooks Activos</h4>
                        </div>
                        <div class="w-full overflow-x-auto">
                            <table class="min-w-full bg-transparent font-sans">
                                <thead class="bg-white/5 border-b border-white/10 text-[10px] text-gray-400 uppercase tracking-wider font-bold text-left">
                                    <tr>
                                        <th class="px-3 py-2.5">Nombre</th>
                                        <th class="px-3 py-2.5">URL de Destino</th>
                                        <th class="px-3 py-2.5">Secreto HMAC</th>
                                        <th class="px-3 py-2.5">Eventos Suscritos</th>
                                        <th class="px-3 py-2.5"></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${tableRows}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            `;
        } else {
            contentDiv.innerHTML = '<p class="text-red-500 text-sm font-sans">Error al listar los Webhooks.</p>';
        }
    } catch (e) {
        console.error(e);
        contentDiv.innerHTML = '<p class="text-red-500 text-sm font-sans">Fallo al conectar con el servidor.</p>';
    }
}

window.createWebhookSubscription = async function (btn) {
    const urlInput = document.getElementById('wh-url');
    const secretInput = document.getElementById('wh-secret');
    const url = urlInput.value.trim();
    const secret = secretInput.value.trim() || null;

    if (!url) {
        _vaultNotify("Por favor ingrese la URL del webhook.");
        return;
    }

    const events = [];
    if (document.getElementById('wh-ev-upload').checked) events.push('upload');
    if (document.getElementById('wh-ev-download').checked) events.push('download');
    if (document.getElementById('wh-ev-archive').checked) events.push('archive');
    if (document.getElementById('wh-ev-ipns').checked) events.push('publish_ipns');

    if (events.length === 0) {
        _vaultNotify("Por favor seleccione al menos un evento.");
        return;
    }

    const token = localStorage.getItem("access_token");
    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = 'Registrando...';

    try {
        const res = await fetch('/ipfs/webhooks', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url, secret, events })
        });

        if (res.ok) {
            _vaultNotify("✓ Webhook registrado exitosamente.");
            showWebhooks();
        } else {
            const err = await res.json();
            _vaultNotify("Error: " + (err.detail || "No se pudo registrar."));
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    } catch (e) {
        console.error(e);
        _vaultNotify("Error al conectar con el servidor.");
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

window.deleteWebhookSubscription = async function (id) {
    if (!confirm("¿Estás seguro de eliminar este webhook? Dejarás de recibir notificaciones en esa URL.")) return;
    const token = localStorage.getItem("access_token");

    try {
        const res = await fetch(`/ipfs/webhooks/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            _vaultNotify("✓ Webhook eliminado.");
            showWebhooks();
        } else {
            _vaultNotify("Error al eliminar el webhook.");
        }
    } catch (e) {
        console.error(e);
        _vaultNotify("Error al enviar la solicitud.");
    }
}

window.syncDocumentPinata = async function (event, cid, btn) {
    event.stopPropagation();
    const token = localStorage.getItem("access_token");
    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `
        <svg class="animate-spin h-3.5 w-3.5 text-sky-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
    `;

    try {
        const res = await fetch(`/ipfs/sync-pinata?cid=${encodeURIComponent(cid)}`, {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            if (window.showToast) window.showToast('Documento sincronizado con Pinata', 'success');
            else _vaultNotify('✓ Documento sincronizado con Pinata Cloud con éxito.');
            fetchVaultDocuments();
        } else {
            const err = await res.json();
            _vaultNotify("Error de sincronización: " + (err.detail || "Desconocido"));
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    } catch (e) {
        console.error(e);
        _vaultNotify("Error al intentar sincronizar.");
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

window.unpinDocumentKubo = async function (event, cid, btn) {
    event.stopPropagation();
    if (!confirm("¿Estás seguro de despinear este documento de tu nodo local? Se mantendrá en Pinata si está sincronizado, pero se eliminará del almacenamiento local para liberar espacio.")) return;

    const token = localStorage.getItem("access_token");
    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `
        <svg class="animate-spin h-3.5 w-3.5 text-amber-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
    `;

    try {
        const res = await fetch(`/ipfs/${encodeURIComponent(cid)}`, {
            method: 'DELETE',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            if (window.showToast) window.showToast('Documento archivado (despineado local)', 'success');
            else _vaultNotify('✓ Documento despineado localmente con éxito.');
            fetchVaultDocuments();
        } else {
            const err = await res.json();
            _vaultNotify("Error al despinear: " + (err.detail || "Desconocido"));
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    } catch (e) {
        console.error(e);
        _vaultNotify("Error al contactar el servidor.");
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

// --- Soporte del Workflow de Aprobación Documental (Opción B) ---
function getDecodedToken() {
    const token = localStorage.getItem("access_token");
    if (!token) return null;
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(window.atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        return JSON.parse(jsonPayload);
    } catch (e) {
        return null;
    }
}

window.solicitarAprobacion = async function(id) {
    const token = localStorage.getItem("access_token");
    try {
        const res = await fetch(`/api/documents/${id}/submit-approval`, {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            if (window.showToast) window.showToast('Enviado a revisión de cumplimiento exitosamente', 'success');
            else _vaultNotify('✓ Documento enviado a revisión.');
            await fetchVaultDocuments();
            await viewDocument(id);
        } else {
            const err = await res.json();
            if (window.showToast) window.showToast('Error: ' + (err.detail || 'Desconocido'), 'error');
            else _vaultNotify('Error: ' + (err.detail || 'Desconocido'));
        }
    } catch (e) {
        console.error(e);
        if (window.showToast) window.showToast('Error de conexión', 'error');
    }
};

window.mostrarCajaComentarios = function() {
    const box = document.getElementById('review-comment-box');
    if (box) box.classList.remove('hidden');
    const btnTrigger = document.getElementById('btn-reject-trigger');
    if (btnTrigger) btnTrigger.classList.add('hidden');
    const btnConfirm = document.getElementById('btn-reject-confirm');
    if (btnConfirm) btnConfirm.classList.remove('hidden');
};

window.enviarDecisionReview = async function(id, action) {
    const token = localStorage.getItem("access_token");
    const comments = document.getElementById('review-comments')?.value || '';
    
    if (action === 'reject' && !comments.trim()) {
        if (window.showToast) window.showToast('Debe ingresar comentarios para rechazar el contrato.', 'warning');
        else _vaultNotify('Debe ingresar comentarios para rechazar.');
        return;
    }
    
    try {
        const res = await fetch(`/api/documents/${id}/review`, {
            method: 'POST',
            headers: { 
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ action, comments })
        });
        if (res.ok) {
            const msg = action === 'approve' ? 'Contrato aprobado con éxito' : 'Contrato rechazado';
            if (window.showToast) window.showToast(msg, 'success');
            else _vaultNotify(msg);
            await fetchVaultDocuments();
            await viewDocument(id);
        } else {
            const err = await res.json();
            if (window.showToast) window.showToast('Error: ' + (err.detail || 'Desconocido'), 'error');
            else _vaultNotify('Error: ' + (err.detail || 'Desconocido'));
        }
    } catch (e) {
        console.error(e);
        if (window.showToast) window.showToast('Error de conexión', 'error');
    }
};


// --- FUNCIONES DE CO-EDICIÓN COLABORATIVA EN LA NUBE CON CRYPTPAD.FR ---

let colabSelectedFile = null;
let colabActiveDocId = null;
let colabActiveDocContent = "";
let colabActiveDocFilename = "";
let colabActiveDocExt = "";

function _setupColabDragZone() {
    const zone = document.getElementById('colab-drag-zone');
    if (zone && !zone.dataset.dragBound) {
        zone.dataset.dragBound = "true";
        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            zone.classList.add('border-purple-500', 'bg-purple-500/10');
        });
        zone.addEventListener('dragleave', () => {
            zone.classList.remove('border-purple-500', 'bg-purple-500/10');
        });
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('border-purple-500', 'bg-purple-500/10');
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                const input = document.getElementById('colab-file-input');
                if (input) {
                    input.files = e.dataTransfer.files;
                    const event = { target: input };
                    handleColabFileSelected(event);
                }
            }
        });
    }
}

window.copiarBorradorAlPortapapelesManual = function (event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    if (!colabActiveDocContent) {
        if (window.showToast) window.showToast("No hay contenido del borrador disponible para copiar.", "warning");
        return;
    }
    navigator.clipboard.writeText(colabActiveDocContent).then(() => {
        if (window.showToast) window.showToast("Contenido del borrador copiado al portapapeles.", "success");
        else _vaultNotify("✓ Borrador copiado.");
    }).catch(err => {
        console.error("Error al copiar borrador:", err);
        if (window.showToast) window.showToast("No se pudo copiar automáticamente. Selecciónalo manualmente.", "error");
    });
};

window.descargarBorradorLocal = async function (event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    
    // Respaldo robusto: si no hay contenido en memoria pero tenemos el ID, lo recuperamos del backend
    if (!colabActiveDocContent && colabActiveDocId) {
        try {
            const token = localStorage.getItem("access_token");
            const res = await fetch(`/api/documents/${colabActiveDocId}`, {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            if (res.ok) {
                const docData = await res.json();
                colabActiveDocContent = docData.content_text || "";
                colabActiveDocFilename = docData.filename || colabActiveDocFilename;
                colabActiveDocExt = docData.filename ? docData.filename.split('.').pop().toLowerCase() : colabActiveDocExt;
            }
        } catch (e) {
            console.error("Error al recuperar el borrador desde el backend:", e);
        }
    }

    if (!colabActiveDocContent) {
        if (window.showToast) window.showToast("No hay contenido del borrador disponible para descargar.", "warning");
        return;
    }
    try {
        let blob;
        let mimeType = 'text/plain;charset=utf-8';
        if (colabActiveDocExt === 'md') {
            mimeType = 'text/markdown;charset=utf-8';
            blob = new Blob([colabActiveDocContent], { type: mimeType });
        } else {
            blob = new Blob([colabActiveDocContent], { type: mimeType });
        }
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        let downloadName = colabActiveDocFilename || "contrato_borrador.txt";
        if (colabActiveDocExt === 'md' && !downloadName.endsWith('.md')) {
            downloadName = downloadName.replace(/\.[^/.]+$/, "") + ".md";
        } else if (colabActiveDocExt === 'docx' && !downloadName.endsWith('.txt')) {
            downloadName = downloadName.replace(/\.[^/.]+$/, "") + "_borrador.txt";
        }
        a.download = downloadName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        if (window.showToast) window.showToast("Borrador descargado para importar en CryptPad.", "success");
    } catch (err) {
        console.error("Fallo al descargar borrador:", err);
        if (window.showToast) window.showToast("Fallo al descargar el borrador.", "error");
    }
};

window.openColabNubeModal = function (docId, panelMode, ext = "") {
    colabActiveDocId = docId;
    const modal = document.getElementById('colab_nube_modal');
    const content = document.getElementById('colab-modal-card');
    const linkPanel = document.getElementById('colab-link-panel');
    const finalizePanel = document.getElementById('colab-finalize-panel');
    const loader = document.getElementById('colab-loader');
    
    if (modal) {
        // Resetear vistas
        linkPanel.classList.add('hidden');
        finalizePanel.classList.add('hidden');
        loader.classList.add('hidden');
        
        document.getElementById('colab-url-input').value = '';
        document.getElementById('colab-file-input').value = '';
        const nameText = document.getElementById('colab-selected-filename');
        nameText.classList.add('hidden');
        nameText.textContent = '';
        colabSelectedFile = null;
        
        const colabEmails = document.getElementById('colab-emails-input');
        if (colabEmails) colabEmails.value = '';
        const colabMsg = document.getElementById('colab-message-input');
        if (colabMsg) colabMsg.value = '';
        
        const finalizeBtn = document.getElementById('colab-btn-finalize');
        finalizeBtn.disabled = true;

        if (panelMode === 'link') {
            linkPanel.classList.remove('hidden');
            
            // Configurar instrucciones personalizadas según la extensión
            const instrText = document.getElementById('colab-instructions-text');
            if (instrText) {
                if (ext === 'md') {
                    instrText.innerHTML = `Hemos copiado el borrador en tu portapapeles de forma automática para pegarlo directamente con <span class="text-white font-semibold">Ctrl+V</span>. También puedes descargar el archivo <span class="text-cyan-400">.md</span> y subirlo en CryptPad con el menú <span class="text-white font-semibold">Archivo -> Importar</span> para una importación limpia de formato.`;
                } else {
                    instrText.innerHTML = `Hemos copiado el borrador en tu portapapeles. Puedes pegarlo con <span class="text-white font-semibold">Ctrl+V</span> o descargar el borrador en texto plano y subirlo en CryptPad con <span class="text-white font-semibold">Archivo -> Importar</span> para comenzar a editar.`;
                }
            }
        } else if (panelMode === 'finalize') {
            finalizePanel.classList.remove('hidden');
            _setupColabDragZone();
        }

        modal.classList.remove('hidden');
        setTimeout(() => {
            modal.style.opacity = '1';
            content.classList.remove('scale-95');
            content.classList.add('scale-100');
        }, 10);
    }
};

window.closeColabNubeModal = function () {
    const modal = document.getElementById('colab_nube_modal');
    const content = document.getElementById('colab-modal-card');
    if (modal) {
        modal.style.opacity = '0';
        content.classList.remove('scale-100');
        content.classList.add('scale-95');
        setTimeout(() => {
            modal.classList.add('hidden');
        }, 300);
    }
};

window.startNubeCollaboration = async function (docId, ext) {
    const token = localStorage.getItem("access_token");
    if (window.showToast) {
        window.showToast("Iniciando co-edición colaborativa...", "info");
    }
    try {
        const res = await fetch(`/api/documents/${docId}/start-collaborative`, {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.ok) {
            const data = await res.json();
            
            // 1. Almacenar contenido en memoria y copiar automáticamente al portapapeles del navegador
            colabActiveDocContent = data.content_text || "";
            colabActiveDocFilename = data.filename || `contrato_borrador.${ext}`;
            colabActiveDocExt = ext;

            if (colabActiveDocContent) {
                navigator.clipboard.writeText(colabActiveDocContent).then(() => {
                    if (window.showToast) window.showToast("Borrador copiado al portapapeles de forma automática", "success");
                }).catch(err => {
                    console.warn("Fallo al copiar portapapeles de forma automática:", err);
                });
            }
            
            // 2. Abrir CryptPad.fr en una nueva pestaña
            window.open(data.cryptpad_init_url, '_blank');
            
            // 3. Abrir modal en STAR-DOC para vincular el enlace
            openColabNubeModal(docId, 'link', ext);
        } else {
            const err = await res.json();
            if (window.showToast) window.showToast('Error: ' + (err.detail || 'Desconocido'), 'error');
            else _vaultNotify('Error: ' + (err.detail || 'Desconocido'));
        }
    } catch (e) {
        console.error(e);
        if (window.showToast) window.showToast('Fallo al iniciar colaboración', 'error');
    }
};

window.linkNubeCollaboration = async function () {
    const token = localStorage.getItem("access_token");
    const urlInput = document.getElementById('colab-url-input');
    const url = urlInput ? urlInput.value.trim() : '';

    if (!url) {
        if (window.showToast) window.showToast("Por favor pegue el enlace de la sala de CryptPad", "warning");
        return;
    }

    // Validación de seguridad de enlace de Compartir en CryptPad (Safe Links)
    if (!url.startsWith("https://cryptpad.fr/")) {
        if (window.showToast) window.showToast("El enlace debe ser de la plataforma oficial https://cryptpad.fr", "warning");
        return;
    }
    if (!url.includes("#")) {
        if (window.showToast) window.showToast("Enlace inválido. Por favor, abre el menú 'Compartir' (arriba a la derecha) en CryptPad y copia el 'Enlace de edición'.", "error");
        return;
    }
    const tieneEdit = url.includes("/edit/");
    const tieneView = url.includes("/view/");
    if (!tieneEdit && !tieneView) {
        if (window.showToast) window.showToast("Permiso no definido. Copia el enlace desde el menú 'Compartir' en CryptPad.", "error");
        return;
    }
    const tokenClave = tieneEdit ? url.split("/edit/")[1] : url.split("/view/")[1];
    const claveLimpia = tokenClave ? tokenClave.trim().replace("/", "").split("?")[0] : "";
    if (!claveLimpia || claveLimpia.length < 15) {
        if (window.showToast) {
            window.showToast("⚠️ Enlace incompleto o copiado de la barra de direcciones. Copia el 'Enlace de edición' desde el menú 'Compartir' de CryptPad.", "error");
        }
        return;
    }

    const emailsInput = document.getElementById('colab-emails-input')?.value || '';
    const customMessage = document.getElementById('colab-message-input')?.value || '';
    
    // Parsear correos electrónicos separados por comas
    const emails = emailsInput.split(',')
        .map(e => e.trim())
        .filter(e => e.length > 0);

    try {
        const btn = document.getElementById('colab-btn-link');
        btn.disabled = true;
        
        const res = await fetch(`/api/documents/${colabActiveDocId}/link-collaborative`, {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                cryptpad_url: url,
                collaborator_emails: emails,
                custom_message: customMessage
            })
        });
        
        btn.disabled = false;

        if (res.ok) {
            if (window.showToast) window.showToast('Sala de CryptPad vinculada con éxito. Co-edición activa.', 'success');
            closeColabNubeModal();
            fetchVaultDocuments();
            viewDocument(colabActiveDocId);
        } else {
            const err = await res.json();
            if (window.showToast) window.showToast('Error: ' + (err.detail || 'Desconocido'), 'error');
            else _vaultNotify('Error: ' + (err.detail || 'Desconocido'));
        }
    } catch (e) {
        console.error(e);
        document.getElementById('colab-btn-link').disabled = false;
        if (window.showToast) window.showToast('Fallo de conexión al vincular', 'error');
    }
};

window.openFinalizeNubeModal = function (docId) {
    openColabNubeModal(docId, 'finalize');
};

window.handleColabFileSelected = function (event) {
    const input = event.target;
    if (input.files && input.files.length > 0) {
        colabSelectedFile = input.files[0];
        const nameText = document.getElementById('colab-selected-filename');
        if (nameText) {
            nameText.textContent = `Archivo seleccionado: ${colabSelectedFile.name}`;
            nameText.classList.remove('hidden');
        }
        const finalizeBtn = document.getElementById('colab-btn-finalize');
        if (finalizeBtn) {
            finalizeBtn.disabled = false;
        }
    }
};

window.finalizeNubeCollaboration = async function () {
    if (!colabSelectedFile) {
        if (window.showToast) window.showToast("Por favor seleccione o arrastre el archivo consolidado", "warning");
        return;
    }

    const token = localStorage.getItem("access_token");
    const finalizeBtn = document.getElementById('colab-btn-finalize');
    const finalizePanel = document.getElementById('colab-finalize-panel');
    const loader = document.getElementById('colab-loader');

    // Cambiar a vista de carga
    finalizePanel.classList.add('hidden');
    loader.classList.remove('hidden');

    try {
        const formData = new FormData();
        formData.append('file', colabSelectedFile);

        const res = await fetch(`/api/documents/${colabActiveDocId}/finalize-collaborative`, {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token },
            body: formData
        });

        if (res.ok) {
            if (window.showToast) window.showToast('Contrato consolidado y PDF compilado con éxito. Estado: Borrador.', 'success');
            closeColabNubeModal();
            fetchVaultDocuments();
            viewDocument(colabActiveDocId);
        } else {
            const err = await res.json();
            if (window.showToast) window.showToast('Error: ' + (err.detail || 'Desconocido'), 'error');
            else _vaultNotify('Error: ' + (err.detail || 'Desconocido'));
            
            // Revertir a panel de finalización
            loader.classList.add('hidden');
            finalizePanel.classList.remove('hidden');
        }
    } catch (e) {
        console.error(e);
        if (window.showToast) window.showToast('Fallo de conexión al consolidar', 'error');
        loader.classList.add('hidden');
        finalizePanel.classList.remove('hidden');
    }
};

