/**
 * index-controller.js
 * Lógica JavaScript para la vista principal de STAR-DOC.
 * Administra el selector de archivos de Google Drive, la edición de plantillas,
 * la generación interactiva/lotes y la programación (Scheduling) con cron.
 */

// --- Global State ---
const googleFilePickerState = { targetInputId: null, targetNameId: null, mimeType: null, modal: null };

// --- Utils ---
const getAuthHeaders = () => ({ 'Authorization': `Bearer ${localStorage.getItem('access_token')}` });

// Helper para debouncing de eventos
const debounce = (func, wait) => {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
};

// Función para guardar inputs del formulario en IndexedDB (con fallback a localStorage)
const saveFormToStorage = async (formId, key) => {
    const form = document.getElementById(formId);
    if (!form) return;
    const formData = new FormData(form);
    const data = {};
    formData.forEach((value, k) => {
        const inputEl = form.querySelector(`[name="${k}"]`);
        if (inputEl && inputEl.type !== 'file' && inputEl.type !== 'password') {
            data[k] = value;
        }
    });

    // Intentar guardar en IndexedDB usando la API de pwa-controller
    if (window.localDb) {
        try {
            await window.localDb.saveDraft(key, data);
            return;
        } catch (e) {
            console.error('[PWA DB] Error guardando borrador en IndexedDB, fallback a localStorage:', e);
        }
    }
    // Fallback
    localStorage.setItem(key, JSON.stringify(data));
};

// Función para restaurar inputs del formulario desde IndexedDB (con fallback a localStorage)
const restoreFormFromStorage = async (formId, key) => {
    const form = document.getElementById(formId);
    if (!form) return;

    let data = null;

    // Intentar restaurar desde IndexedDB usando la API de pwa-controller
    if (window.localDb) {
        try {
            data = await window.localDb.getDraft(key);
        } catch (e) {
            console.error('[PWA DB] Error leyendo borrador de IndexedDB, fallback a localStorage:', e);
        }
    }

    // Fallback si no se obtuvo nada de IndexedDB
    if (!data) {
        const stored = localStorage.getItem(key);
        if (!stored) return;
        try {
            data = JSON.parse(stored);
        } catch (e) {
            console.error('Error al parsear localStorage:', e);
            return;
        }
    }

    if (!data) return;

    try {
        Object.entries(data).forEach(([k, val]) => {
            const inputEl = form.querySelector(`[name="${k}"]`);
            if (inputEl && inputEl.type !== 'file' && inputEl.type !== 'password') {
                if (inputEl.type === 'checkbox') {
                    inputEl.checked = (val === 'true' || val === true || val === 'on');
                    inputEl.dispatchEvent(new Event('change', { bubbles: true }));
                } else if (inputEl.type === 'radio') {
                    if (inputEl.value === val) {
                        inputEl.checked = true;
                        inputEl.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                } else {
                    inputEl.value = val;
                    inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                    inputEl.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        });
    } catch (e) {
        console.error('Error al restaurar del borrador:', e);
    }
};

const handleAuthError = (res) => {
    if (res.status === 401) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('isWalletConnected');
        window.location.href = '/login?expired=true';
        throw new Error('Sesión expirada');
    }
    return res;
};

function openFilePicker(mimeType, targetInputId, targetNameId) {
    googleFilePickerState.mimeType = mimeType;
    googleFilePickerState.targetInputId = targetInputId;
    googleFilePickerState.targetNameId = targetNameId;

    const modal = document.getElementById('googleFilePickerModal');
    document.getElementById('picker-title').textContent = mimeType.includes('spreadsheet') ? 'Seleccionar Hoja de Cálculo' : 'Seleccionar Documento';
    modal.showModal();
    fetchAndRenderFiles(mimeType);
}

async function fetchAndRenderFiles(mimeType, query = '') {
    const listContainer = document.getElementById('file-picker-list-container');
    listContainer.innerHTML = '<div class="text-center p-4"><span class="loading loading-spinner text-primary"></span></div>';

    try {
        const response = await fetch(`/api/drive/files?mime_type=${encodeURIComponent(mimeType)}&q=${encodeURIComponent(query)}`, { headers: getAuthHeaders() });
        handleAuthError(response);
        if (!response.ok) throw new Error('Error al cargar archivos');
        const data = await response.json();

        listContainer.innerHTML = '';
        if (!data.files.length) {
            listContainer.innerHTML = '<div class="p-4 text-center text-white/50">No se encontraron archivos</div>';
            return;
        }

        data.files.forEach(file => {
            const item = document.createElement('div');
            item.className = 'flex items-center gap-3 p-3 hover:bg-white/5 rounded-lg cursor-pointer transition-colors border border-transparent hover:border-white/10';
            item.innerHTML = `
                <img src="${file.iconLink}" class="w-5 h-5 opacity-80">
                <div class="flex-1 min-w-0">
                    <div class="font-medium truncate text-sm text-gray-200">${file.name}</div>
                    <div class="text-xs text-gray-500">Modificado: ${new Date(file.modifiedTime).toLocaleDateString()}</div>
                </div>
            `;
            item.onclick = () => {
                document.getElementById(googleFilePickerState.targetInputId).value = file.id;
                document.getElementById(googleFilePickerState.targetNameId).value = file.name;
                document.getElementById(googleFilePickerState.targetNameId).parentNode.classList.remove('hidden'); // Show badge
                if (googleFilePickerState.targetInputId === 'google-doc-id' ||
                    googleFilePickerState.targetInputId === 'google-sheet-id' ||
                    googleFilePickerState.targetInputId === 'interactive-google-doc-id') {
                    document.getElementById(googleFilePickerState.targetInputId).dispatchEvent(new Event('change')); // Trigger validation / variable extraction
                }
                document.getElementById('googleFilePickerModal').close();
            };
            listContainer.appendChild(item);
        });
    } catch (e) {
        listContainer.innerHTML = `<div class="text-error text-center p-4">${e.message}</div>`;
    }
}

// --- Search Debounce ---
let searchTimeout;
document.getElementById('file-picker-search-input')?.addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => fetchAndRenderFiles(googleFilePickerState.mimeType, e.target.value), 300);
});

// --- Template Management ---
let allTemplates = [];
let activeFilterFormat = 'all';

// Función global para filtrar por extensión
window.filterTemplatesByFormat = (format) => {
    activeFilterFormat = format;
    
    // Actualizar apariencia de los chips
    const chips = document.querySelectorAll('#template-filter-chips button');
    chips.forEach(btn => {
        const filterAttr = btn.getAttribute('data-filter');
        if (filterAttr === format) {
            btn.className = 'btn btn-xs rounded-full border border-accent/30 bg-accent/15 text-accent font-semibold hover:bg-accent/25 transition-all duration-200 px-3 cursor-pointer shadow-sm shadow-accent/5';
        } else {
            btn.className = 'btn btn-xs rounded-full border border-white/10 bg-black/40 text-gray-400 font-semibold hover:bg-white/5 hover:text-white transition-all duration-200 px-3 cursor-pointer';
        }
    });

    // Re-filtrar y renderizar
    const term = (document.getElementById('manage-search-input')?.value || '').toLowerCase();
    applyFilters(term);
};

// Combinar término de búsqueda y formato
const applyFilters = (term) => {
    let filtered = allTemplates;
    
    // 1. Filtrar por término
    if (term) {
        filtered = filtered.filter(t => t.filename.toLowerCase().includes(term));
    }
    
    // 2. Filtrar por extensión
    if (activeFilterFormat === 'docx') {
        filtered = filtered.filter(t => t.filename.toLowerCase().endsWith('.docx'));
    } else if (activeFilterFormat === 'md') {
        filtered = filtered.filter(t => t.filename.toLowerCase().endsWith('.md'));
    }
    
    renderTemplatesList(filtered);
};

const renderTemplatesList = (templates) => {
    const list = document.getElementById('existing-templates-list');
    if (!list) return;
    list.innerHTML = '';

    if (templates.length === 0) {
        list.innerHTML = `
            <div class="col-span-1 md:col-span-2 p-8 text-center bg-black/10 rounded-xl border border-white/5">
                <i class="bi bi-file-earmark-x text-3xl text-gray-600 mb-2"></i>
                <p class="text-sm text-gray-400">No se encontraron plantillas coincidentes</p>
            </div>
        `;
        return;
    }

    // Identificar rol del usuario actual
    const payload = getDecodedToken();
    const username = payload ? payload.sub : '';
    const role = payload ? payload.role : '';
    const isSenior = (username === 'starcontract') || (role === 'senior') || (role === 'admin') || (role === 'compliance');

    templates.forEach(t => {
        const isDocx = t.filename.endsWith('.docx');
        const isMd = t.filename.endsWith('.md');
        
        let iconClass = 'bi-file-earmark-text text-gray-400';
        let bgClass = 'hover:bg-blue-500/5 hover:border-blue-500/20';
        let badge = '<span class="badge badge-xs badge-neutral">Otro</span>';
        
        if (isDocx) {
            iconClass = 'bi-file-earmark-word-fill text-blue-400';
            bgClass = 'hover:bg-blue-500/5 hover:border-blue-500/20';
            badge = '<span class="badge badge-xs bg-blue-500/10 border-blue-500/20 text-blue-400 font-semibold uppercase">docx</span>';
        } else if (isMd) {
            iconClass = 'bi-file-earmark-code-fill text-purple-400';
            bgClass = 'hover:bg-purple-500/5 hover:border-purple-500/20';
            badge = '<span class="badge badge-xs bg-purple-500/10 border-purple-500/20 text-purple-400 font-semibold uppercase">markdown</span>';
        }

        // Definir badge de workflow de plantilla
        let workflowBadge = '';
        const status = (t.status || 'approved').toLowerCase();
        if (status === 'pending_approval') {
            workflowBadge = `<span class="badge badge-xs bg-amber-500/10 border-amber-500/20 text-amber-400 font-semibold uppercase" title="Subida por Junior. Requiere aprobación.">⏳ Pendiente</span>`;
        } else if (status === 'rejected') {
            workflowBadge = `<span class="badge badge-xs bg-red-500/10 border-red-500/20 text-red-400 font-semibold uppercase tooltip tooltip-top" data-tip="Motivo: ${t.comments || 'Rechazado'}">❌ Rechazada</span>`;
        }

        const card = document.createElement('div');
        card.className = `p-4 rounded-xl border border-white/10 bg-gradient-to-br from-white/5 to-white/[0.01] transition-all duration-300 flex items-center justify-between gap-3 group relative overflow-hidden ${bgClass}`;
        
        card.innerHTML = `
            <!-- Decorador de color de hover -->
            <div class="absolute left-0 top-0 bottom-0 w-1 bg-transparent group-hover:bg-accent transition-colors duration-300"></div>
            
            <div class="flex items-center gap-3 min-w-0">
                <div class="w-10 h-10 rounded-lg bg-black/30 border border-white/5 flex items-center justify-center text-xl shrink-0 group-hover:scale-105 transition-transform duration-300">
                    <i class="bi ${iconClass}"></i>
                </div>
                <div class="min-w-0">
                    <div class="text-sm font-semibold text-gray-200 truncate group-hover:text-white group-hover:whitespace-normal group-hover:break-all transition-all duration-300 cursor-pointer" title="${t.filename}">${t.filename}</div>
                    <div class="flex items-center gap-2 mt-1">
                        ${badge}
                        ${workflowBadge}
                        <span class="text-[10px] text-gray-500">Local</span>
                    </div>
                </div>
            </div>
            
            <div class="flex gap-1 shrink-0 bg-black/40 backdrop-blur-sm p-1 rounded-lg border border-white/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300 z-20">
                <!-- Botones de aprobación del workflow para Senior -->
                ${(isSenior && status === 'pending_approval' && t.id) ? `
                    <button type="button" class="btn btn-square btn-ghost btn-xs text-emerald-400 hover:bg-emerald-500/10 tooltip tooltip-top" data-tip="Aprobar Plantilla" onclick="aprobarPlantilla(${t.id})">
                        <i class="bi bi-check-lg text-sm"></i>
                    </button>
                    <button type="button" class="btn btn-square btn-ghost btn-xs text-red-400 hover:bg-red-500/10 tooltip tooltip-top" data-tip="Rechazar Plantilla" onclick="rechazarPlantilla(${t.id})">
                        <i class="bi bi-x-lg text-sm"></i>
                    </button>
                ` : ''}
                
                ${isSenior ? `
                    ${(isMd || isDocx) ? `
                        <button type="button" class="btn btn-square btn-ghost btn-xs text-info hover:bg-info/10 tooltip tooltip-top" data-tip="Editar Plantilla" onclick="openEditor('${t.filename}')">
                            <i class="bi bi-pencil text-sm"></i>
                        </button>
                    ` : ''}
                    <button type="button" class="btn btn-square btn-ghost btn-xs text-error hover:bg-error/10 tooltip tooltip-top" data-tip="Eliminar" onclick="deleteTemplate('${t.filename}')">
                        <i class="bi bi-trash text-sm"></i>
                    </button>
                ` : `
                    ${(isMd || isDocx) ? `
                        <button type="button" class="btn btn-square btn-ghost btn-xs text-info hover:bg-info/10 tooltip tooltip-top" data-tip="Ver Plantilla" onclick="openEditor('${t.filename}')">
                            <i class="bi bi-eye text-sm"></i>
                        </button>
                    ` : ''}
                `}
            </div>
        `;
        list.appendChild(card);
    });
};

const refreshTemplates = async () => {
    const list = document.getElementById('existing-templates-list');
    if (!list) return;

    // Renderizar Skeletons premium de carga
    list.innerHTML = Array.from({ length: 4 }).map(() => `
        <div class="p-4 rounded-xl border border-white/5 bg-white/[0.02] flex items-center justify-between gap-3 animate-pulse">
            <div class="flex items-center gap-3 w-full">
                <div class="w-10 h-10 rounded-lg bg-white/10 shrink-0"></div>
                <div class="space-y-2 w-full">
                    <div class="h-3.5 bg-white/10 rounded w-3/4"></div>
                    <div class="h-2.5 bg-white/5 rounded w-1/4"></div>
                </div>
            </div>
        </div>
    `).join('');

    try {
        const res = await fetch('/templates', { headers: getAuthHeaders() });
        handleAuthError(res);
        if (!res.ok) throw new Error('Error cargando plantillas');
        allTemplates = await res.json();
        
        // Mantener filtro y término activos
        applyFilters((document.getElementById('manage-search-input')?.value || '').toLowerCase());
    } catch (e) {
        showToast(e.message, 'error');
    }
};

// Search Logic
document.getElementById('manage-search-input')?.addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase();
    applyFilters(term);
});

// --- Editor Logic ---
let cmEditor = null;
let editingFile = null;

window.closeEditorModal = () => {
    const modal = document.getElementById('editorModal');
    if (modal) {
        modal.classList.remove('modal-open');
    }

    if (typeof tinymce !== 'undefined' && tinymce.get('tinymce-editor')) {
        tinymce.remove('#tinymce-editor');
    }
    const container = document.getElementById('editor-container');
    if (container) {
        container.innerHTML = '';
    }
    cmEditor = null;
    editingFile = null;
};

window.openEditor = async (filename) => {
    editingFile = filename;
    const modal = document.getElementById('editorModal');
    
    // Identificar rol del usuario actual
    const payload = getDecodedToken();
    const username = payload ? payload.sub : '';
    const role = payload ? payload.role : '';
    const isSenior = (username === 'starcontract') || (role === 'senior') || (role === 'admin') || (role === 'compliance');

    if (isSenior) {
        document.getElementById('editor-filename').textContent = `Editando: ${filename}`;
        document.getElementById('save-template-btn')?.classList.remove('hidden');
    } else {
        document.getElementById('editor-filename').textContent = `Visualizando: ${filename}`;
        document.getElementById('save-template-btn')?.classList.add('hidden');
    }

    // Mostrar u ocultar botón de restaurar según si es .docx y es Senior
    const restoreBtn = document.getElementById('restore-template-btn');
    if (filename.endsWith('.docx') && isSenior) {
        restoreBtn.classList.remove('hidden');
    } else {
        restoreBtn.classList.add('hidden');
    }

    // Limpiar editores anteriores
    if (typeof tinymce !== 'undefined' && tinymce.get('tinymce-editor')) {
        tinymce.remove('#tinymce-editor');
    }

    try {
        if (filename.endsWith('.md')) {
            const res = await fetch(`/template-content/${filename}`, { headers: getAuthHeaders() });
            handleAuthError(res);
            const content = await res.text();

            modal.classList.add('modal-open');
            setTimeout(() => {
                const container = document.getElementById('editor-container');
                container.innerHTML = '';
                cmEditor = CodeMirror(container, {
                    value: content,
                    mode: 'markdown',
                    theme: 'dracula',
                    lineNumbers: false, // Turn off for Docs feel
                    lineWrapping: true,
                    scrollbarStyle: "native",
                    readOnly: !isSenior
                });

                // Force layout recalculation
                setTimeout(() => cmEditor.refresh(), 50);

                // --- Context Sharing Logic ---
                const iaFrame = document.querySelector('#ia-pane iframe');
                const sendContext = (text) => {
                    if (iaFrame && iaFrame.contentWindow) {
                        iaFrame.contentWindow.postMessage({ type: 'UPDATE_CONTEXT', text: text }, '*');
                    }
                };

                // Send initial context
                sendContext(content);

                // Debounce for updates (solo si es senior, si es de solo lectura no hace falta)
                if (isSenior) {
                    let timeout;
                    cmEditor.on('change', (doc) => {
                        clearTimeout(timeout);
                        timeout = setTimeout(() => sendContext(doc.getValue()), 1000);
                    });
                }

            }, 100);

        } else if (filename.endsWith('.docx')) {
            const res = await fetch(`/template-html/${filename}`, { headers: getAuthHeaders() });
            handleAuthError(res);
            const data = await res.json();

            // Fetch variables for TinyMCE toolbar
            let vList = [];
            try {
                const varsRes = await fetch(`/template-variables/${filename}`, { headers: getAuthHeaders() });
                if (varsRes.ok) {
                    const varsData = await varsRes.json();
                    if (varsData.success) vList = varsData.variables;
                }
            } catch (e) { console.warn("Could not fetch template variables"); }

            modal.classList.add('modal-open');
            setTimeout(() => {
                const container = document.getElementById('editor-container');
                container.innerHTML = '<textarea id="tinymce-editor"></textarea>';
                document.getElementById('tinymce-editor').value = data.html;

                tinymce.init({
                    selector: '#tinymce-editor',
                    height: '100%',
                    width: '100%',
                    menubar: false,
                    promotion: false,
                    skin: 'oxide-dark',
                    skin_url: 'https://cdn.jsdelivr.net/npm/tinymce@6.8.2/skins/ui/oxide-dark',
                    content_css: 'default',
                    readonly: !isSenior ? 1 : 0,
                    plugins: 'lists table code searchreplace wordcount charmap fullscreen link pagebreak visualblocks preview',
                    toolbar: isSenior 
                        ? 'undo redo | blocks fontfamily fontsize | bold italic underline strikethrough | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | table | insertvar | searchreplace charmap link pagebreak | visualblocks preview fullscreen code'
                        : 'fullscreen preview visualblocks searchreplace wordcount',
                    content_style: `
                        html {
                            background-color: #0f172a;
                            padding: 30px 10px;
                            height: auto;
                            box-sizing: border-box;
                        }
                        body {
                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                            padding: 50px 60px !important;
                            background: white !important;
                            color: black !important;
                            max-width: 800px;
                            margin: 0 auto !important;
                            min-height: 1056px;
                            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
                            border: 1px solid rgba(0, 0, 0, 0.15);
                            border-radius: 4px;
                            box-sizing: border-box;
                        }
                        table { border-collapse: collapse; width: 100%; }
                        table, th, td { border: 1px solid black; }
                    `,
                    setup: function (editor) {
                        editor.ui.registry.addMenuButton('insertvar', {
                            text: 'Variables { }',
                            tooltip: 'Insertar Variable Jinja',
                            fetch: function (callback) {
                                var items = vList.map(v => ({
                                    type: 'menuitem',
                                    text: v,
                                    onAction: function () {
                                        editor.insertContent('{{' + v + '}}');
                                    }
                                }));
                                if (items.length === 0) {
                                    items.push({ type: 'menuitem', text: 'Sin variables guardadas', disabled: true, onAction: function () { } });
                                }
                                callback(items);
                            }
                        });
                    }
                });
            }, 100);
        }
    } catch (e) { showToast(e.message, 'error'); }
};

document.getElementById('save-template-btn')?.addEventListener('click', async () => {
    if (!editingFile) return;
    showLoader('Guardando plantilla...');
    try {
        if (editingFile.endsWith('.md')) {
            if (!cmEditor) return;
            const res = await fetch(`/template-content/${editingFile}`, {
                method: 'POST',
                headers: { ...getAuthHeaders(), 'Content-Type': 'text/plain' },
                body: cmEditor.getValue()
            });
            handleAuthError(res);
        } else if (editingFile.endsWith('.docx')) {
            const editor = tinymce.get('tinymce-editor');
            if (!editor) return;
            const content = editor.getContent();
            const res = await fetch('/save-docx-template', {
                method: 'POST',
                headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ template_name: editingFile, html_content: content })
            });
            handleAuthError(res);
            const result = await res.json();
            if (!res.ok) throw new Error(result.detail || 'Error al guardar');
        }
        showToast('Guardado correctamente', 'success');
        closeEditorModal();
    } catch (e) { showToast(e.message, 'error'); }
    finally { hideLoader(); }
});

document.getElementById('restore-template-btn')?.addEventListener('click', async () => {
    if (!editingFile || !editingFile.endsWith('.docx')) return;
    if (!confirm(`¿Restaurar la versión anterior de ${editingFile} (perderás los últimos cambios)?`)) return;

    showLoader('Restaurando backup...');
    try {
        const res = await fetch(`/restore-docx-template/${editingFile}`, {
            method: 'POST',
            headers: getAuthHeaders()
        });
        handleAuthError(res);
        const result = await res.json();

        if (!res.ok) throw new Error(result.detail || 'Error al restaurar');
        showToast(result.message, 'success');

        const currentFile = editingFile;
        closeEditorModal();
        // Recargar para aplicar cambios inmediatamente
        openEditor(currentFile);
    } catch (e) { showToast(e.message, 'error'); }
    finally { hideLoader(); }
});

window.deleteTemplate = async (filename) => {
    if (!confirm(`¿Eliminar ${filename}?`)) return;
    showLoader('Eliminando...');
    try {
        const res = await fetch(`/delete-template/${filename}`, { method: 'DELETE', headers: getAuthHeaders() });
        handleAuthError(res);
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || `Error al eliminar plantilla (${res.status})`);
        }
        await refreshTemplates();
        showToast('Eliminado', 'success');
    } catch (e) { showToast(e.message, 'error'); }
    finally { hideLoader(); }
};

document.getElementById('refresh-templates')?.addEventListener('click', refreshTemplates);

// --- Template Select Redirect ---
document.getElementById('template-select')?.addEventListener('change', (e) => {
    if (e.target.value) window.location.href = `/home?template=${e.target.value}&active_tab=interactive`;
});

// --- Validation Logic ---
const runValidation = async () => {
    const formData = new FormData();
    const tFile = document.getElementById('batch-template-file').files[0];
    const gDoc = document.getElementById('google-doc-id').value;
    const dFile = document.getElementById('batch-data-file').files[0];
    const gSheet = document.getElementById('google-sheet-id').value;

    const templateSourceTypeChecked = document.querySelector('input[name="templateSourceType"]:checked');
    const dataSourceTypeChecked = document.querySelector('input[name="dataSourceType"]:checked');

    if (!templateSourceTypeChecked || !dataSourceTypeChecked) return;

    const useTFile = templateSourceTypeChecked.value === 'file';
    const useDFile = dataSourceTypeChecked.value === 'file';

    if (useTFile && tFile) formData.append('template_file', tFile);
    if (!useTFile && gDoc) formData.append('google_doc_id', gDoc);
    if (useDFile && dFile) formData.append('data_file', dFile);
    if (!useDFile && gSheet) formData.append('google_sheet_id', gSheet);

    if ((!useTFile && !gDoc) || (useTFile && !tFile) || (!useDFile && !gSheet) || (useDFile && !dFile)) return;

    const valContainer = document.getElementById('validation-container');
    const resDiv = document.getElementById('validation-result');
    valContainer.classList.remove('hidden');
    resDiv.innerHTML = '<span class="loading loading-spinner loading-sm"></span> Validando...';

    try {
        const res = await fetch('/api/validate', { method: 'POST', headers: getAuthHeaders(), body: formData });
        handleAuthError(res);
        const data = await res.json();

        if (data.match) {
            resDiv.innerHTML = `<div class="text-success"><i class="bi bi-check-circle-fill"></i> Plantilla compatible! Variables: ${data.template_vars.join(', ')}</div>`;
            valContainer.className = 'p-4 rounded-xl bg-success/10 border-l-4 border-success mt-4';
        } else {
            resDiv.innerHTML = `<div class="text-error"><i class="bi bi-exclamation-triangle"></i> Faltan variables: ${data.missing_in_data.join(', ')}</div>`;
            valContainer.className = 'p-4 rounded-xl bg-error/10 border-l-4 border-error mt-4';
        }
    } catch (e) { console.error(e); }
};

// Attach listeners for validation
['batch-template-file', 'batch-data-file', 'google-doc-id', 'google-sheet-id'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', runValidation);
});

// --- Render Generation Result helper ---
// --- Render Generation Result helper ---
const renderGenerationResult = (containerId, result) => {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = '';
    container.classList.remove('hidden');

    const card = document.createElement('div');
    card.className = 'glass-card p-4 sm:p-5 rounded-2xl border border-accent/20 mt-4 space-y-4 w-full box-sizing-border';

    let ipfsSection = '';
    if (result.ipfs) {
        const badgeClass = result.ipfs.classification === 'public' ? 'badge-success border-success/30 bg-success/10 text-success' :
                           result.ipfs.classification === 'confidential' ? 'badge-warning border-warning/30 bg-warning/10 text-warning' : 'badge-error border-error/30 bg-error/10 text-error';
        const badgeText = result.ipfs.classification === 'public' ? '🟢 Público' :
                          result.ipfs.classification === 'confidential' ? '🟡 Confidencial' : '🔴 Cadena de Custodia';
        
        ipfsSection = `
            <div class="bg-black/40 p-3 sm:p-4 rounded-xl border border-white/5 space-y-2 text-xs font-mono w-full box-sizing-border">
                <div class="flex justify-between items-center py-1 border-b border-white/5 gap-2">
                    <span class="text-gray-400">Estado IPFS</span>
                    <span class="badge badge-success badge-sm font-semibold text-[10px] sm:text-xs">Sellado en Kubo</span>
                </div>
                <div class="flex justify-between items-center py-1 border-b border-white/5 gap-2">
                    <span class="text-gray-400">Clasificación</span>
                    <span class="badge badge-sm font-semibold text-[10px] sm:text-xs ${badgeClass}">${badgeText}</span>
                </div>
                <div class="flex justify-between items-center py-1 border-b border-white/5 gap-2">
                    <span class="text-gray-400">IPFS CID</span>
                    <span class="text-white select-all text-right max-w-[120px] xs:max-w-[160px] sm:max-w-[200px] md:max-w-xs truncate" title="${result.ipfs.cid}">${result.ipfs.cid}</span>
                </div>
                <div class="flex justify-between items-center py-1 gap-2">
                    <span class="text-gray-400">SHA-256 Original</span>
                    <span class="text-white select-all text-right max-w-[120px] xs:max-w-[160px] sm:max-w-[200px] md:max-w-xs truncate" title="${result.ipfs.sha256_original}">${result.ipfs.sha256_original}</span>
                </div>
            </div>
        `;
    }

    const viewIpfsBtn = result.ipfs ? `
        <a href="${result.ipfs.gateway_url}" target="_blank" class="btn btn-sm btn-outline btn-info gap-2 w-full sm:w-auto text-xs">
            <i class="bi bi-link-45deg"></i> Ver en IPFS
        </a>
        <a href="/ipfs/certificate/${result.ipfs.cid}" target="_blank" class="btn btn-sm btn-outline btn-accent gap-2 w-full sm:w-auto text-xs">
            <i class="bi bi-file-earmark-pdf"></i> Descargar Certificado
        </a>
    ` : '';

    card.innerHTML = `
        <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-success/20 flex items-center justify-center text-success shrink-0">
                <i class="bi bi-check2-circle text-2xl animate-pulse"></i>
            </div>
            <div class="min-w-0 flex-1">
                <h4 class="font-bold text-white text-sm sm:text-base break-words">¡Proceso Completado Exitosamente!</h4>
                <p class="text-xs text-gray-400 font-mono mt-0.5 truncate max-w-[160px] xs:max-w-[220px] sm:max-w-xs md:max-w-md" title="${result.filename}">${result.filename}</p>
            </div>
        </div>
        
        ${ipfsSection}

        <div class="flex flex-col sm:flex-row flex-wrap gap-2 pt-2 border-t border-white/5">
            <a href="${result.download_url}" class="btn btn-sm btn-success text-white gap-2 w-full sm:w-auto text-xs" download>
                <i class="bi bi-download"></i> Descargar Archivo
            </a>
            ${viewIpfsBtn}
            <button type="button" onclick="openMeetingModalFromEditor('${result.filename}')" class="btn btn-sm btn-outline btn-primary gap-2 w-full sm:w-auto text-xs">
                <i class="bi bi-camera-video-fill"></i> Debatir en Videollamada
            </button>
        </div>
    `;
    container.appendChild(card);
    container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
};

window.openMeetingModalFromEditor = (docName) => {
    const modal = document.getElementById('meetingModal');
    if (!modal) return;
    
    let foundEmail = '';
    
    // Buscar dinámicamente el correo electrónico ingresado en las variables del formulario activo
    const forms = ['interactive-generate-form', 'interactive-generate-form-drive'];
    for (const formId of forms) {
        const form = document.getElementById(formId);
        if (form) {
            const inputs = form.querySelectorAll('input, textarea, select');
            for (const input of inputs) {
                const name = (input.getAttribute('name') || '').toLowerCase();
                const id = (input.getAttribute('id') || '').toLowerCase();
                const placeholder = (input.getAttribute('placeholder') || '').toLowerCase();
                
                // Buscar coincidencia semántica con campos de correo electrónico
                if ((name.includes('email') || name.includes('correo') || name.includes('mail') ||
                     id.includes('email') || id.includes('correo') || id.includes('mail') ||
                     placeholder.includes('email') || placeholder.includes('correo') || placeholder.includes('mail')) && 
                    input.value && input.value.trim() !== '') {
                    
                    const val = input.value.trim();
                    if (val.includes('@')) {
                        foundEmail = val;
                        break; // Se detiene al encontrar el primer correo válido
                    }
                }
            }
        }
        if (foundEmail) break;
    }
    
    document.getElementById('meet-emails').value = foundEmail;
    document.getElementById('meet-doc-name').value = docName || '';
    document.getElementById('meet-reason').value = docName ? `Debate del documento: ${docName}` : 'Debate y Firma de Documento';
    document.getElementById('meet-send-invitations').checked = true;
    
    // Inicializar el toggle de deshabilitar IPFS en falso por defecto
    const disableIpfsEl = document.getElementById('meet-disable-ipfs');
    if (disableIpfsEl) {
        disableIpfsEl.checked = false;
    }
    
    modal.showModal();
};

window.submitCreateMeetingFromEditor = async () => {
    const btn = document.getElementById('btn-create-meeting-editor');
    const originalContent = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="loading loading-spinner loading-xs"></span> Creando...';
    
    const emailsInput = document.getElementById('meet-emails').value;
    const docName = document.getElementById('meet-doc-name').value;
    const reason = document.getElementById('meet-reason').value;
    const sendInvitations = document.getElementById('meet-send-invitations').checked;
    
    // Obtener valor del toggle de deshabilitar IPFS
    const disableIpfsEl = document.getElementById('meet-disable-ipfs');
    const disableIpfs = disableIpfsEl ? disableIpfsEl.checked : false;
    
    const classificationEl = document.getElementById('meet-classification');
    let classification = "chain_of_custody";
    if (classificationEl) {
        classification = classificationEl.value;
    } else {
        const mainFormClassificationEl = document.querySelector('[name="classification"]');
        if (mainFormClassificationEl) {
            classification = mainFormClassificationEl.value;
        }
    }
    
    const emailList = emailsInput
        .split(',')
        .map(e => e.trim())
        .filter(e => e.length > 0);
        
    try {
        const response = await fetch('/api/meetings/create-instant', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({
                emails: emailList,
                document_name: docName || null,
                reason: reason,
                send_invitations: sendInvitations,
                classification: classification,
                disable_ipfs: disableIpfs
            })
        });
        
        handleAuthError(response);
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Error al crear la videollamada');
        }
        
        const data = await response.json();
        document.getElementById('meetingModal').close();
        
        showToast('¡Videollamada creada exitosamente!', 'success');
        
        const isPwa = window.isPwaStandalone && window.isPwaStandalone();
        const confirmMsg = isPwa 
            ? '¿Deseas entrar a la videollamada ahora mismo?' 
            : '¿Deseas entrar a la videollamada en una nueva pestaña ahora mismo?';
        const target = isPwa ? '_self' : '_blank';
        
        if (confirm(confirmMsg)) {
            window.open(data.local_meeting_link, target);
        }
    } catch (e) {
        showToast(e.message || 'Error al crear videollamada', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalContent;
    }
};

// --- Forms Submission ---
const handleForm = async (formId, url) => {
    const form = document.getElementById(formId);
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = form.querySelector('button[type="submit"]');
        const originalText = btn.innerHTML;
        btn.disabled = true;

        // Clear previous result card
        const resContainer = document.getElementById(formId + '-result');
        if (resContainer) {
            resContainer.innerHTML = '';
            resContainer.classList.add('hidden');
        }

        let loaderText = 'Procesando...';
        if (formId === 'upload-template-form') loaderText = 'Subiendo plantilla...';
        if (formId === 'interactive-generate-form') loaderText = 'Generando documento...';
        if (formId === 'batch-generate-form') loaderText = 'Procesando lote (esto puede tardar)...';

        showLoader(loaderText);

        try {
            const formData = new FormData(form);
            const res = await fetch(url, { method: 'POST', headers: getAuthHeaders(), body: formData });
            handleAuthError(res);
            const result = await res.json();

            if (!res.ok) throw new Error(result.detail || 'Error');

            if (result.download_url) {
                showToast('Documento generado!', 'success');
                
                if (resContainer) {
                    renderGenerationResult(formId + '-result', result);
                }

                // Disparar flujo de firma electrónica si está habilitado
                if (typeof triggerSignatureWorkflowIfEnabled === 'function') {
                    await triggerSignatureWorkflowIfEnabled(result.filename, formId);
                }

                // Preview logic reused
                if (result.filename.endsWith('.pdf')) {
                    const fRes = await fetch(result.download_url, { headers: getAuthHeaders() });
                    handleAuthError(fRes);
                    const blob = await fRes.blob();
                    const pdfUrl = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
                    document.getElementById('preview-iframe').src = pdfUrl;
                    document.getElementById('download-btn-preview').href = pdfUrl;
                    document.getElementById('download-btn-preview').download = result.filename;
                    document.getElementById('previewModal').showModal();
                } else if (!result.ipfs) {
                    try {
                        const fRes = await fetch(result.download_url, { headers: getAuthHeaders() });
                        handleAuthError(fRes);
                        if (!fRes.ok) throw new Error("Error al descargar el archivo generado");

                        const blob = await fRes.blob();
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.style.display = 'none';
                        a.href = url;
                        a.download = result.filename;
                        document.body.appendChild(a);
                        a.click();
                        window.URL.revokeObjectURL(url);
                    } catch (downloadError) {
                        console.error("Download error:", downloadError);
                        showToast("Error descargando el archivo: " + downloadError.message, 'error');
                    }
                }
            } else {
                showToast(result.message || 'Éxito', 'success');
                if (formId === 'upload-template-form') {
                    form.reset();
                    refreshTemplates();
                }
            }
        } catch (e) {
            showToast(e.message, 'error');
        } finally {
            hideLoader();
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    });
};

handleForm('interactive-generate-form', '/generate-document');
handleForm('batch-generate-form', '/generate-batch');
handleForm('upload-template-form', '/upload-template');

// --- Init ---
document.addEventListener('DOMContentLoaded', async () => {
    if (!localStorage.getItem('access_token')) window.location.href = '/';
    refreshTemplates();

    // --- LocalStorage/IndexedDB Auto-save for Local Templates ---
    const localForm = document.getElementById('interactive-generate-form');
    if (localForm) {
        const templateNameInput = localForm.querySelector('input[name="template_name"]');
        const templateName = templateNameInput ? templateNameInput.value : '';
        if (templateName) {
            const storageKey = `star_doc_local_${templateName}`;
            await restoreFormFromStorage('interactive-generate-form', storageKey);

            const debouncedSaveLocal = debounce(() => {
                saveFormToStorage('interactive-generate-form', storageKey);
            }, 300);

            localForm.addEventListener('input', debouncedSaveLocal);
            localForm.addEventListener('change', debouncedSaveLocal);
        }
    }

    // --- LocalStorage Auto-save for Google Drive Templates ---
    const driveForm = document.getElementById('interactive-generate-form-drive');
    if (driveForm) {
        const debouncedSaveDrive = debounce(() => {
            const docId = document.getElementById('interactive-google-doc-id')?.value;
            if (docId) {
                const storageKey = `star_doc_drive_${docId}`;
                saveFormToStorage('interactive-generate-form-drive', storageKey);
            }
        }, 300);

        driveForm.addEventListener('input', debouncedSaveDrive);
        driveForm.addEventListener('change', debouncedSaveDrive);
    }

    // Drag & Drop
    // Drag & Drop
    const dropZone = document.querySelector('.drag-drop-zone');
    const fileIn = document.getElementById('new-template-file');
    const defaultState = document.getElementById('drag-drop-default-state');
    const fileState = document.getElementById('drag-drop-file-state');
    const fileName = document.getElementById('selected-file-name');
    const fileSize = document.getElementById('selected-file-size');
    const clearBtn = document.getElementById('clear-selected-file');

    fileIn?.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            if (fileName) fileName.textContent = file.name;
            
            if (fileSize) {
                const sizeKb = file.size / 1024;
                const sizeDisplay = sizeKb > 1024 
                    ? (sizeKb / 1024).toFixed(1) + ' MB' 
                    : sizeKb.toFixed(0) + ' KB';
                fileSize.textContent = sizeDisplay;
            }
            
            defaultState?.classList.add('hidden');
            fileState?.classList.remove('hidden');
            dropZone?.classList.add('border-accent', 'bg-accent/5');
        }
    });

    clearBtn?.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (fileIn) fileIn.value = '';
        defaultState?.classList.remove('hidden');
        fileState?.classList.add('hidden');
        dropZone?.classList.remove('border-accent', 'bg-accent/5');
    });

    // Toggles
    const setupToggle = (name, boxId) => {
        document.querySelectorAll(`input[name="${name}"]`).forEach(r => {
            r.addEventListener('change', () => {
                const box = document.getElementById(boxId);
                if (r.value === 'file') box.classList.remove('hidden');
                else box.classList.add('hidden');

                // Toggle google containers logic inverse
                const gId = boxId === 'template-file-upload-container' ? 'google-doc-container' : 'google-sheet-container';
                const gBox = document.getElementById(gId);
                if (r.value !== 'file') gBox.classList.remove('hidden');
                else gBox.classList.add('hidden');
            });
        });
    };
    setupToggle('templateSourceType', 'template-file-upload-container');
    setupToggle('dataSourceType', 'file-upload-container');

    // Email Toggle
    document.getElementById('interactive-send-email-check')?.addEventListener('change', (e) => {
        const g = document.getElementById('interactive-email-recipient-group');
        if (e.target.checked) g.classList.remove('hidden'); else g.classList.add('hidden');
    });
    document.getElementById('batch-send-email-check')?.addEventListener('change', (e) => {
        const g = document.getElementById('batch-email-recipient-group');
        if (e.target.checked) g.classList.remove('hidden'); else g.classList.add('hidden');
    });

    // Drive email toggle
    document.getElementById('drive-send-email-check')?.addEventListener('change', (e) => {
        const g = document.getElementById('drive-email-recipient-group');
        if (e.target.checked) g.classList.remove('hidden'); else g.classList.add('hidden');
    });

    // --- Google Drive Variable Extraction (Interactive) ---
    document.getElementById('interactive-google-doc-id')?.addEventListener('change', async (e) => {
        const docId = e.target.value;
        if (!docId) {
            document.getElementById('interactive-variables-drive').classList.add('hidden');
            const serverSection = document.getElementById('interactive-variables-server');
            if (serverSection) serverSection.classList.remove('hidden');
            return;
        }

        const serverSection = document.getElementById('interactive-variables-server');
        if (serverSection) serverSection.classList.add('hidden');
        const driveSection = document.getElementById('interactive-variables-drive');
        driveSection.classList.remove('hidden');

        document.getElementById('drive-variables-loading').classList.remove('hidden');
        document.getElementById('drive-variables-error').classList.add('hidden');
        document.getElementById('drive-variables-fields').classList.add('hidden');
        document.getElementById('drive-no-variables').classList.add('hidden');

        document.getElementById('drive-form-google-doc-id').value = docId;

        try {
            const response = await fetch('/template-fields-from-drive', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...getAuthHeaders()
                },
                body: JSON.stringify({ google_doc_id: docId })
            });

            handleAuthError(response);

            if (!response.ok) {
                const errData = await response.json().catch(() => ({ detail: 'Error desconocido' }));
                throw new Error(errData.detail || 'Error extrayendo campos');
            }

            const data = await response.json();
            document.getElementById('drive-variables-loading').classList.add('hidden');

            // Notificar firmantes detectados al widget de Alpine
            window.dispatchEvent(new CustomEvent('drive-fields-loaded', {
                detail: { detected_signers: data.detected_signers || [] }
            }));

            const fields = data.fields || [];
            const fieldsContainer = document.querySelector('#drive-variables-fields .grid');
            fieldsContainer.innerHTML = '';

            if (fields.length > 0) {
                fields.forEach(field => {
                    const div = document.createElement('div');
                    div.className = 'form-control';
                    
                    let inputHtml = '';
                    if (field.type === 'textarea') {
                        inputHtml = `<textarea name="${field.name}" class="textarea textarea-bordered bg-black/20 focus:border-accent h-24" placeholder="${field.placeholder}" required></textarea>`;
                    } else {
                        inputHtml = `<input type="${field.type}" name="${field.name}" class="input input-bordered bg-black/20 focus:border-accent" placeholder="${field.placeholder}" required />`;
                    }
                    
                    div.innerHTML = `
                        <label class="label">
                            <span class="label-text text-primary font-medium">${field.label}</span>
                        </label>
                        ${inputHtml}
                    `;
                    fieldsContainer.appendChild(div);
                });
                document.getElementById('drive-variables-fields').classList.remove('hidden');

                // Restaurar inputs desde localStorage/IndexedDB para este Google Doc ID
                const storageKey = `star_doc_drive_${docId}`;
                await restoreFormFromStorage('interactive-generate-form-drive', storageKey);
            } else {
                document.getElementById('drive-no-variables').classList.remove('hidden');
            }

        } catch (err) {
            document.getElementById('drive-variables-loading').classList.add('hidden');
            document.getElementById('drive-variables-error').classList.remove('hidden');
            document.getElementById('drive-variables-error-msg').textContent = err.message;
        }
    });

    // Drive form submission
    document.getElementById('interactive-generate-form-drive')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const form = e.target;
        const formData = new FormData(form);

        const submitBtn = form.querySelector('button[type="submit"]');
        const originalHtml = submitBtn.innerHTML;
        submitBtn.innerHTML = '<span class="loading loading-spinner"></span> Generando...';
        submitBtn.disabled = true;

        const resContainer = document.getElementById('interactive-generate-form-drive-result');
        if (resContainer) {
            resContainer.innerHTML = '';
            resContainer.classList.add('hidden');
        }

        try {
            const response = await fetch('/generate-document', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: formData
            });

            handleAuthError(response);

            if (!response.ok) {
                const errData = await response.json().catch(() => ({ detail: 'Error desconocido' }));
                throw new Error(errData.detail || 'Error generando documento');
            }

            const result = await response.json();

            showToast('¡Documento generado!', 'success');
            if (resContainer) {
                renderGenerationResult('interactive-generate-form-drive-result', result);
            }

            // Disparar flujo de firma electrónica si está habilitado
            if (typeof triggerSignatureWorkflowIfEnabled === 'function') {
                await triggerSignatureWorkflowIfEnabled(result.filename, 'interactive-generate-form-drive');
            }

        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            submitBtn.innerHTML = originalHtml;
            submitBtn.disabled = false;
        }
    });
});

// --- Scheduling Logic (Smart) ---
let currentSchedTab = 'daily';

// Initialize Defaults
document.getElementById('schedule-interactive-btn')?.addEventListener('click', () => {
    if (!document.getElementById('sched-time').value) {
        const now = new Date();
        now.setHours(now.getHours() + 1);
        now.setMinutes(0);
        document.getElementById('sched-time').value = now.toTimeString().slice(0, 5);
    }
    updateSmartCron();
    document.getElementById('scheduleModal').showModal();
});

document.getElementById('schedule-interactive-btn-drive')?.addEventListener('click', () => {
    if (!document.getElementById('sched-time').value) {
        const now = new Date();
        now.setHours(now.getHours() + 1);
        now.setMinutes(0);
        document.getElementById('sched-time').value = now.toTimeString().slice(0, 5);
    }
    updateSmartCron();
    document.getElementById('scheduleModal').showModal();
});

window.switchScheduleTab = (tab, btn) => {
    currentSchedTab = tab;
    document.querySelectorAll('.tabs .tab').forEach(t => t.classList.remove('tab-active', 'bg-primary', 'text-white'));
    btn.classList.add('tab-active', 'bg-primary', 'text-white');

    document.getElementById('sched-weekly-opts').classList.add('hidden');
    document.getElementById('sched-monthly-opts').classList.add('hidden');

    if (tab === 'weekly') document.getElementById('sched-weekly-opts').classList.remove('hidden');
    if (tab === 'monthly') document.getElementById('sched-monthly-opts').classList.remove('hidden');

    updateSmartCron();
};

window.toggleDay = (btn) => {
    btn.classList.toggle('btn-primary');
    btn.classList.toggle('text-white');
    updateSmartCron();
};

window.updateSmartCron = () => {
    const timeVal = document.getElementById('sched-time').value || "00:00";
    const [hour, minute] = timeVal.split(':');
    let cron = `0 9 * * *`;
    let summary = "";

    if (currentSchedTab === 'daily') {
        cron = `${minute} ${hour} * * *`;
        summary = `Todos los días a las ${timeVal}`;
    } else if (currentSchedTab === 'weekly') {
        const days = Array.from(document.querySelectorAll('.day-btn.btn-primary'))
            .map(b => b.dataset.day).join(',');
        const daysStr = days || "*";

        cron = `${minute} ${hour} * * ${daysStr}`;

        const dayNames = days?.split(',').map(d =>
            ['Dom', 'Lun', 'Mar', 'Mie', 'Jue', 'Vie', 'Sab'][parseInt(d)]
        ).join(', ');

        summary = days ? `Todos los ${dayNames} a las ${timeVal}` : "Selecciona al menos un día";
    } else if (currentSchedTab === 'monthly') {
        const dom = document.getElementById('sched-dom').value;
        cron = `${minute} ${hour} ${dom} * *`;
        summary = dom === 'L' ? `El último día de cada mes a las ${timeVal}` : `El día ${dom} de cada mes a las ${timeVal}`;
    }

    document.getElementById('cron-expression-input').value = cron;
    document.getElementById('sched-summary').innerText = summary;
};

document.getElementById('confirm-schedule-btn')?.addEventListener('click', async () => {
    const cron = document.getElementById('cron-expression-input').value;
    if (!cron) { showToast('Ingrese una expresión CRON', 'error'); return; }

    const driveSection = document.getElementById('interactive-variables-drive');
    const isDriveForm = driveSection && !driveSection.classList.contains('hidden');

    const form = isDriveForm
        ? document.getElementById('interactive-generate-form-drive')
        : document.getElementById('interactive-generate-form');

    if (!form) { showToast('No hay formulario activo', 'error'); return; }

    const formData = new FormData(form);
    const formObj = {};

    formData.forEach((value, key) => {
        if (formObj[key]) {
            if (!Array.isArray(formObj[key])) formObj[key] = [formObj[key]];
            formObj[key].push(value);
        } else {
            formObj[key] = value;
        }
    });

    const sendEmailCheckbox = form.querySelector('[name="send_email"]');
    formObj['send_email'] = sendEmailCheckbox ? sendEmailCheckbox.checked : false;

    const templateName = formObj['template_name'];
    const googleDocId = formObj['google_doc_id'];
    const outputFormat = formObj['output_format'] || 'docx';

    const context = { ...formObj };
    delete context['template_name'];
    delete context['google_doc_id'];
    delete context['output_format'];
    delete context['cron_expression'];
    delete context['send_email'];

    const payload = {
        template_name: templateName,
        google_doc_id: googleDocId,
        output_format: outputFormat,
        cron_expression: cron,
        context: context
    };

    const btn = document.getElementById('confirm-schedule-btn');
    const originalText = btn.innerText;
    btn.disabled = true;
    btn.innerText = 'Guardando...';

    try {
        const res = await fetch('/schedule/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify(payload)
        });
        handleAuthError(res);

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Error al programar');
        }

        showToast('Tarea programada con éxito', 'success');
        document.getElementById('scheduleModal').close();
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerText = originalText;
    }
});

// =====================================================
// AUTOMATIZACIÓN E INTEGRACIÓN DE FIRMA ELECTRÓNICA
// =====================================================

async function triggerSignatureWorkflowIfEnabled(filename, formId) {
    const signatureWidgetEl = document.querySelector('[x-data="signatureWidget"]');
    if (!signatureWidgetEl) return;
    
    if (typeof Alpine !== 'undefined') {
        const signatureData = Alpine.$data(signatureWidgetEl);
        if (signatureData && signatureData.enabled && signatureData.allSigners.length > 0) {
            // Leer la clasificación seleccionada del formulario de generación
            const formEl = document.getElementById(formId);
            let classification = "chain_of_custody";
            if (formEl) {
                const formData = new FormData(formEl);
                classification = formData.get("classification") || "chain_of_custody";
            }
            
            showLoader('Despachando firma electrónica...');
            try {
                const sigRes = await fetch('/signatures/request', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({
                        document_filename: filename,
                        signers: signatureData.allSigners,
                        expiration_days: 7,
                        classification: classification
                    })
                });
                handleAuthError(sigRes);
                const sigResult = await sigRes.json();
                
                if (sigRes.ok && sigResult.success) {
                    showToast('¡Solicitud de firma enviada a los involucrados!', 'success');
                    
                    const resContainer = document.getElementById(formId + '-result');
                    if (resContainer) {
                        const sigDiv = document.createElement('div');
                        sigDiv.className = 'bg-indigo-950/30 p-4 rounded-xl border border-indigo-500/20 mt-3 space-y-2 text-xs text-left';
                        sigDiv.innerHTML = `
                            <div class="flex items-center gap-2 text-indigo-400 font-bold mb-1">
                                <i class="bi bi-pencil-square animate-pulse"></i> Firma Electrónica Despachada
                            </div>
                            <p class="text-gray-300">Se ha enviado el enlace único de firma a los siguientes correos:</p>
                            <ul class="list-disc list-inside space-y-1 text-gray-400">
                                ${signatureData.allSigners.map(s => `<li><strong>${s.name}</strong> (${s.email}) - <span class="text-amber-400">Pendiente ⌛</span></li>`).join('')}
                            </ul>
                        `;
                        resContainer.appendChild(sigDiv);
                        resContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                    }
                } else {
                    throw new Error(sigResult.detail || 'Fallo al procesar la solicitud de firma');
                }
            } catch (sigErr) {
                console.error("Signature Request Error:", sigErr);
                showToast("Error en firma: " + sigErr.message, 'error');
            } finally {
                hideLoader();
            }
        }
    }
}

// --- Alpine.js Signature Widget Integration ---
document.addEventListener('alpine:init', () => {
    Alpine.data('signatureWidget', () => ({
        enabled: false,
        signers: [],       // [{ role: '', name_var: '', email_var: '', name: '', email: '' }]
        manualSigners: [], // [{ name: '', email: '' }]
        
        init() {
            // Cargar firmantes locales (Jinja2)
            const rawSigners = document.getElementById('detected-signers-raw')?.value;
            if (rawSigners) {
                try {
                    const parsed = JSON.parse(rawSigners);
                    if (Array.isArray(parsed)) {
                        this.signers = parsed.map(s => ({
                            role: s.role,
                            name_var: s.name_var,
                            email_var: s.email_var,
                            name: '',
                            email: ''
                        }));
                        this.enabled = this.signers.length > 0;
                    }
                } catch(e) {
                    console.warn("Error parsing detected-signers-raw:", e);
                }
            }

            // Escuchar cambios en los formularios para autocompletar variables
            ['interactive-generate-form', 'interactive-generate-form-drive'].forEach(formId => {
                const form = document.getElementById(formId);
                if (form) {
                    form.addEventListener('input', () => this.syncFormValues(form));
                }
            });
            
            // Escuchar carga de campos desde Drive
            window.addEventListener('drive-fields-loaded', (e) => {
                const signersList = e.detail.detected_signers || [];
                this.signers = signersList.map(s => ({
                    role: s.role,
                    name_var: s.name_var,
                    email_var: s.email_var,
                    name: '',
                    email: ''
                }));
                this.enabled = this.signers.length > 0;
            });
        },
        
        syncFormValues(form) {
            const formData = new FormData(form);
            this.signers.forEach(s => {
                if (s.name_var) s.name = formData.get(s.name_var) || '';
                if (s.email_var) s.email = formData.get(s.email_var) || '';
            });
        },
        
        addManualSigner() {
            this.manualSigners.push({ name: '', email: '' });
        },
        
        removeManualSigner(index) {
            this.manualSigners.splice(index, 1);
        },
        
        get allSigners() {
            const list = [];
            this.signers.forEach(s => {
                if (s.name.trim() && s.email.trim()) {
                    list.push({ name: s.name.trim(), email: s.email.trim() });
                }
            });
            this.manualSigners.forEach(s => {
                if (s.name.trim() && s.email.trim()) {
                    list.push({ name: s.name.trim(), email: s.email.trim() });
                }
            });
            return list;
        }
    }));
});

// --- Workflow de Aprobación de Plantillas (Opción B ampliado) ---
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

window.aprobarPlantilla = async (templateId) => {
    const token = localStorage.getItem("access_token");
    try {
        const res = await fetch(`/api/templates/${templateId}/review`, {
            method: 'POST',
            headers: { 
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ action: 'approve' })
        });
        if (res.ok) {
            showToast('Plantilla aprobada con éxito. Ya está visible para todo el equipo.', 'success');
            await refreshTemplates();
        } else {
            const err = await res.json();
            showToast('Error: ' + (err.detail || 'Desconocido'), 'error');
        }
    } catch (e) {
        console.error(e);
        showToast('Error de conexión', 'error');
    }
};

window.rechazarPlantilla = async (templateId) => {
    const comments = prompt("Ingrese obligatoriamente el motivo del rechazo de la plantilla:");
    if (comments === null) return; // Cancelado
    if (!comments.trim()) {
        showToast('Debe ingresar un motivo para el rechazo.', 'warning');
        return;
    }
    const token = localStorage.getItem("access_token");
    try {
        const res = await fetch(`/api/templates/${templateId}/review`, {
            method: 'POST',
            headers: { 
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ action: 'reject', comments })
        });
        if (res.ok) {
            showToast('Plantilla rechazada con éxito.', 'info');
            await refreshTemplates();
        } else {
            const err = await res.json();
            showToast('Error: ' + (err.detail || 'Desconocido'), 'error');
        }
    } catch (e) {
        console.error(e);
        showToast('Error de conexión', 'error');
    }
};

