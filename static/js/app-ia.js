/**
 * =====================================================
 * STAR-DOC :: Componente Alpine.js del Chat de IA
 * =====================================================
 * Sistema de interacción inteligente con comandos / y menciones @
 * 
 * Funcionalidades:
 * - Slash Commands (/) : Menú contextual de comandos rápidos
 * - @ Mentions         : Autocompletado de plantillas y documentos
 * - Skills dinámicos   : Carga de agentes especializados desde backend
 * - TTS               : Lectura automática de respuestas en voz alta
 * - Streaming SSE     : Respuestas en tiempo real desde Gemini
 */
document.addEventListener('alpine:init', () => {
    Alpine.data('chatApp', () => ({
        // --- Estado del chat ---
        chatHistory: [],
        userInput: '',
        status: { message: '', color: '' },
        isRecording: false,
        recognition: null,

        // --- Historial de Hilos (Multithread) ---
        threads: [],
        currentThreadId: null,
        historySidebarOpen: true,
        editingThreadId: null,
        editingThreadTitle: '',

        // --- Sidebar de Análisis Legal ---
        sidebarOpen: false,
        sidebarTab: 'auditoria', // 'auditoria' | 'documento'
        legalAnalysis: null, // Objeto con score, riesgos, mapa_normatividad, etc.
        legalAnalysisLoading: false, // Indicador de carga de análisis

        // --- Adjuntos y Skills ---
        attachmentMenuOpen: false, // Controla la visibilidad del menú de adjuntos y acciones
        currentAttachment: null, // { name: '', text: '' }
        activeSkill: null,       // { id: '', cmd: '', desc: '', sysPrompt: '' }
        activeSystemPrompt: '',

        // --- Templates (modal legacy) ---
        templates: [],
        isTemplateModalOpen: false,

        // --- Formulario Dinámico de Plantilla (Modal) ---
        fieldsModal: {
            isOpen: false,
            templateName: '',
            fields: [],
            values: {},
            currentStep: 1,
            steps: [],
            totalSteps: 1
        },

        // --- Sugerencia Proactiva de Plantilla ---
        proactiveTemplateSuggestion: null,

        // --- Formulario de Liquidaciones (Modal) ---
        liquidacionModal: {
            isOpen: false,
            values: {
                salario_mensual: '',
                fecha_ingreso: '',
                fecha_retiro: '',
                tiene_auxilio_transporte: true,
                es_salario_integral: false,
                es_salario_variable: false,
                salario_promedio_prestaciones: '',
                salario_promedio_vacaciones: '',
                cesantias_pendientes_desde: '',
                prima_pendiente_desde: '',
                dias_vacaciones_pendientes: '',
                vacaciones_disfrutadas: 0,
                tipo_contrato: 'indefinido',
                causa_retiro: 'renuncia',
                fecha_fin_contrato: '',
                fecha_estimada_fin_obra: '',
                fecha_calculo_sancion_mora: '',
                estimar_sancion_mora: true
            }
        },

        // --- Formulario de Videollamada (Modal) ---
        meetingModal: {
            isOpen: false,
            emails: '',
            documentName: '',
            reason: 'Debate de documento legal',
            sendInvitations: true,
            classification: 'chain_of_custody',
            disableIpfs: false,
            loading: false
        },

        // --- TTS ---
        ttsAutoRead: true,
        ttsPaused: false,
        isTTSPlaying: false,

        // --- Slash Menu (/) ---
        slashMenu: { visible: false, activeIndex: 0 },
        slashFilter: '',

        // --- @ Mention Menu ---
        atMenu: { visible: false, activeIndex: 0 },
        atFilter: '',
        availableTemplates: [],  // [{name: 'tutela.docx', displayName: 'tutela', ext: '.docx'}, ...]
        lastSuggestions: [],     // Sugerencias inteligentes ( chips )

        // --- Comandos Slash base (hardcoded) ---
        allSlashCommands: [
            {
                id: 'riesgos',
                cmd: '/riesgos',
                desc: 'Analizar riesgos legales',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>',
                prompt: 'Identifica las cláusulas de mayor riesgo legal para mi cliente en este documento, citando la normativa colombiana aplicable y sugiriendo mitigaciones.',
                systemPrompt: 'Actúa como un Auditor Legal Senior experto en derecho colombiano (Código Civil, Código de Comercio). Tu objetivo es proteger los intereses del cliente identificando riesgos severos, ambigüedades y cláusulas abusivas.'
            },
            {
                id: 'resumir',
                cmd: '/resumir',
                desc: 'Resumen ejecutivo',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>',
                prompt: 'Genera un resumen ejecutivo estructurado de este documento. Incluye: Objeto, Partes, Vigencia, Valor/Pagos, y Obligaciones principales.',
                systemPrompt: 'Eres un asistente legal eficiente. Genera resúmenes concisos, estructurados y fáciles de leer para gerentes y abogados.'
            },
            {
                id: 'fechas',
                cmd: '/fechas',
                desc: 'Tabla de fechas clave',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>',
                prompt: 'Extrae todas las fechas, plazos y vencimientos del documento y preséntalos en una tabla Markdown con las columnas: Evento/Obligación, Fecha Límite, y Responsable.',
                systemPrompt: 'Eres un asistente administrativo legal meticuloso. Extrae fechas con precisión exacta.'
            },
            {
                id: 'diagrama',
                cmd: '/diagrama',
                desc: 'Crear flujo procesal',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"/>',
                prompt: 'Crea un diagrama de flujo en sintaxis Mermaid (graph TD) que represente el proceso o los pasos descritos en el texto. Solo devuelve el código Mermaid dentro de un bloque ```mermaid ```.',
                systemPrompt: 'Eres un generador de diagramas experto. Tu ÚNICA tarea es generar código Mermaid válido (graph TD). 1. Usa SIEMPRE la sintaxis `graph TD`. 2. Envuelve el código estrictamente en un bloque ```mermaid```. 3. IMPORTANTE: Usa SIEMPRE comillas dobles para los textos de los nodos, ejemplo: A["Texto con (parentesis) o > símbolos"]. 4. Usa IDs de nodos simples (A, B, C, Node1). 5. NO incluyas explicaciones.'
            },
            {
                id: 'mejorar',
                cmd: '/mejorar',
                desc: 'Mejorar redacción',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>',
                prompt: 'Reescribe el texto seleccionado o el documento adjunto con un tono más formal, jurídico y preciso, eliminando ambigüedades.',
                systemPrompt: 'Actúa como un Redactor Jurídico experto. Tu redacción debe ser impecable, formal, precisa y elegante, propia de contratos de alto nivel.'
            },
            {
                id: 'buscar',
                cmd: '/buscar',
                desc: 'Buscar en web',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>',
                prompt: 'Busca en internet información actualizada sobre: ',
                systemPrompt: ''
            },
            {
                id: 'expediente',
                cmd: '/expediente',
                desc: 'Consultar expediente judicial',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-4-4"/>',
                prompt: 'Consulta el estado del expediente judicial con radicación: ',
                systemPrompt: 'Eres un asistente legal experto en consulta de expedientes judiciales colombianos. Usa la herramienta buscar_expediente_judicial para consultar portales oficiales. Presenta los resultados de forma clara y estructurada.'
            },
            {
                id: 'ingestar',
                cmd: '/ingestar',
                desc: 'Ingestar jurisprudencia',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>',
                prompt: 'Indexa e ingesta la jurisprudencia o ley colombiana: ',
                systemPrompt: 'Eres un especialista en gestión documental y jurisprudencia colombiana. Utiliza `notebook_ingest_jurisprudencia` para buscar portales oficiales, filtrar la información e indexarla al cuaderno legal.'
            },
            {
                id: 'linea-juris',
                cmd: '/linea-juris',
                desc: 'Línea jurisprudencial',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 002 2h2a2 2 0 002-2"/>',
                prompt: 'Genera un análisis y línea jurisprudencial del precedente judicial sobre: ',
                systemPrompt: 'Eres un analista de precedentes de las Altas Cortes de Colombia. Utiliza la herramienta `notebook_linea_jurisprudencial` para procesar el cuaderno y estructurar la sentencia hito, ratio decidendi, confirmatorias y modificatorias.'
            },
            {
                id: 'red-team',
                cmd: '/red-team',
                desc: 'Red Team Judicial',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/>',
                prompt: 'Realiza una auditoría adversarial tipo Red Team de mi escrito/documento para identificar vacíos y contraargumentos sobre: ',
                systemPrompt: 'Actúa como el abogado de la CONTRAPARTE. Tu objetivo es auditar el escrito, encontrar vulnerabilidades argumentativas, verificar vigencia de citas normativas colombianas y proponer sugerencias para blindarlo usando `notebook_red_team_legal`.'
            },
            {
                id: 'comparar',
                cmd: '/comparar',
                desc: 'Comparar dos textos contractuales',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />',
                prompt: 'Compara los siguientes dos textos e identifica sus diferencias legales y riesgos: \n\n[Texto Original]: \n\n[Texto Modificado]: ',
                systemPrompt: 'Eres un analista de contratos senior. Compara los textos proporcionados usando `compare_documents` y evalúa el impacto legal.'
            },
            {
                id: 'tutela',
                cmd: '/tutela',
                desc: 'Contestar acción de tutela',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />',
                prompt: 'Analiza la tutela adjunta y genera un borrador completo de contestación jurídica, pronunciándote sobre hechos y citando sentencias T y SU de la Corte Constitucional colombiana relevantes.',
                systemPrompt: 'Actúa como Abogado Constitucionalista y Litigante Senior experto en Colombia. Tu objetivo es redactar la contestación de la tutela adjunta con el mayor rigor legal, desvirtuando los cargos y proponiendo excepciones de fondo. Llama a validate_data con ContestacionTutelaSchema antes de generate_document.'
            },
            {
                id: 'peticion',
                cmd: '/peticion',
                desc: 'Responder derecho de petición',
                icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 4v-4z"/>',
                prompt: 'Analiza el derecho de petición adjunto y redacta una respuesta de fondo, clara, precisa y oportuna de conformidad con la Ley 1755 de 2015.',
                systemPrompt: 'Actúa como Consultor Jurídico experto. Responde de fondo la petición adjunta, punto por punto, citando jurisprudencia administrativa y de la Corte Constitucional si es pertinente. Llama a validate_data con RespuestaPeticionSchema antes de generate_document.'
            },
            {
                id: 'gestor_liquidaciones',
                cmd: '/gestor-liquidaciones',
                desc: 'Cálculos y Acreencias Laborales (Colombia)',
                icon: '<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>',
                isSkill: true,
                skillId: 'gestor_liquidaciones',
                prompt: ''
            },
            {
                id: 'videollamada',
                cmd: '/videollamada',
                desc: 'Crear videollamada de Meet para debate/firma',
                icon: '<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 00-2 2z"/></svg>',
                prompt: '',
                isMeeting: true
            },
            {
                id: 'generador_documentos',
                cmd: '/generador-documentos',
                desc: 'Generador dinámico guiado de documentos',
                icon: '<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/><circle cx="18" cy="18" r="3" fill="currentColor" class="text-cyan-400 animate-pulse"/></svg>',
                prompt: ''
            }
        ],

        // --- Acciones rápidas (botones) ---
        quickActions: [],

        // =====================================================
        // COMPUTED PROPERTIES
        // =====================================================

        /**
         * Detecta si hay una mención de plantilla (@nombre.docx o @nombre.md) en el input del chat
         */
        get detectedTemplate() {
            if (!this.userInput) return null;
            // Buscar un patrón tipo @nombre_archivo.extension en cualquier parte del input
            const match = this.userInput.match(/@([\w\-\.]+\.(docx|md|txt))/i);
            return match ? match[1] : null;
        },

        /**
         * Filtra los slash commands según lo que el usuario ha escrito después de /
         */
        get filteredSlashCommands() {
            const pattern = this.slashFilter.replace(/^\//, '').toLowerCase();
            let filtered = [];

            if (pattern.length === 0) {
                filtered = this.allSlashCommands.slice();
            } else {
                filtered = this.allSlashCommands.filter(c =>
                    c.cmd.toLowerCase().includes(pattern) ||
                    (c.desc && c.desc.toLowerCase().includes(pattern))
                );
            }

            // Priorizar comandos contextuales si hay documento adjunto
            if (this.currentAttachment) {
                filtered.sort((a, b) => {
                    const aContext = ['/riesgos', '/resumir', '/fechas', '/mejorar'].includes(a.cmd) ? 1 : 0;
                    const bContext = ['/riesgos', '/resumir', '/fechas', '/mejorar'].includes(b.cmd) ? 1 : 0;
                    return bContext - aContext;
                });
            }

            return filtered;
        },

        /**
         * Filtra las plantillas disponibles según lo escrito después de @
         */
        get filteredAtMentions() {
            const pattern = this.atFilter.toLowerCase();
            if (pattern.length === 0) {
                return this.availableTemplates.slice();
            }
            return this.availableTemplates.filter(t =>
                t.name.toLowerCase().includes(pattern) ||
                t.displayName.toLowerCase().includes(pattern)
            );
        },

        // =====================================================
        // INICIALIZACIÓN
        // =====================================================

        init() {
            localforage.config({ name: 'StarDocAI', storeName: 'chat_store' });

            // Cargar estado del sidebar de historial
            const savedSidebar = localStorage.getItem('history-sidebar-open');
            this.historySidebarOpen = savedSidebar !== null ? savedSidebar === 'true' : true;

            // Cargar índice de hilos e inicializar
            this.loadThreadsIndex().then(async () => {
                // Migración de historial legacy a multihilo si existe
                try {
                    const legacyHistory = await localforage.getItem('chat_history');
                    if (legacyHistory && Array.isArray(legacyHistory) && legacyHistory.length > 0) {
                        console.log("Migrando historial heredado a un nuevo hilo...");
                        const migId = this.generateUUID();
                        const migThread = {
                            id: migId,
                            title: 'Conversación Migrada',
                            lastUpdated: Date.now()
                        };
                        this.threads.push(migThread);
                        this.currentThreadId = migId;

                        await localforage.setItem(`chat_history_${migId}`, legacyHistory);
                        await localforage.removeItem('chat_history');
                        await this.saveThreadsIndex();
                    }
                } catch (migrationError) {
                    console.error("Error migrating legacy history:", migrationError);
                }

                // Cargar historial del hilo activo
                this.loadHistory().then(restored => {
                    if (!restored) {
                        this.pushWelcomeMessage();
                    } else {
                        this.showStatus("Conversación restaurada.", "green", 2000);
                    }
                });
            });

            // Cargar skills dinámicos y plantillas para autocompletado
            this.loadSkills();
            this.loadAvailableTemplates();
            this.setupSpeechRecognition();

            // Sincronizar estado TTS con Alpine.js
            if (window.TTSController) {
                this.ttsAutoRead = TTSController.isAutoReadEnabled();
                console.log('[Alpine/TTS] Estado inicial auto-lectura:', this.ttsAutoRead);
            }

            // Observador periódico para sincronizar estado de reproducción
            setInterval(() => {
                if (window.TTSController) {
                    this.isTTSPlaying = TTSController.isPlaying;
                    // Sincronizar pausa solo si hay audio activo
                    if (!this.isTTSPlaying) {
                        this.ttsPaused = false;
                    }
                }
            }, 300);

            // Atajo global Alt+P para pausar/reanudar TTS
            document.addEventListener('keydown', (e) => {
                if (e.altKey && e.key.toLowerCase() === 'p') {
                    e.preventDefault();
                    this.toggleTTSGlobalPause();
                }
            });

            // Configurar renderer de Markdown
            const mdRenderer = new marked.Renderer();
            mdRenderer.table = function (header, body) {
                return `<div class="overflow-x-auto my-4 rounded-lg border border-white/10 shadow-lg"><table class="table table-zebra w-full text-sm bg-black/20"><thead class="bg-white/5 text-blue-300 font-bold uppercase tracking-wider">${header}</thead><tbody class="divide-y divide-white/5">${body}</tbody></table></div>`;
            };
            mdRenderer.blockquote = function (quote) {
                return `<blockquote class="border-l-4 border-blue-500/50 pl-4 py-2 italic text-gray-400 bg-white/5 rounded-r-lg my-4">${quote}</blockquote>`;
            };
            marked.use({ renderer: mdRenderer });

            this.scrollToBottom();
        },

        getScoreColor(score, type = 'stroke') {
            if (score >= 80) return type === 'stroke' ? 'text-green-500' : 'text-green-400';
            if (score >= 50) return type === 'stroke' ? 'text-amber-500' : 'text-amber-400';
            return type === 'stroke' ? 'text-red-500' : 'text-red-400';
        },

        // =====================================================
        // CARGA DE DATOS
        // =====================================================

        pushWelcomeMessage() {
            const welcomeMessage = "¡Hola! Soy el asistente Legal de STARCONTRACT. ¿En qué puedo ayudarte hoy?";
            this.chatHistory.push({
                id: Date.now(),
                role: 'model',
                text: welcomeMessage,
                html: marked.parse(welcomeMessage),
                timestamp: '',
                isStreaming: false
            });
        },

        async loadHistory() {
            if (!this.currentThreadId) return false;
            try {
                const stored = await localforage.getItem(`chat_history_${this.currentThreadId}`);
                if (!stored) return false;

                const parsed = typeof stored === 'string' ? JSON.parse(stored) : stored;
                if (!Array.isArray(parsed) || parsed.length === 0) return false;

                this.chatHistory = parsed.map(item => {
                    const text = item?.parts?.[0]?.text || '';
                    return {
                        id: Math.random().toString(36).substr(2, 9),
                        role: item.role === 'user' ? 'user' : 'model',
                        text: text,
                        html: item.role === 'user' ? text.replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, '<br>') : marked.parse(text),
                        timestamp: item.timestamp || '',
                        isStreaming: false
                    };
                });

                this.scrollToBottom();
                return true;
            } catch (e) {
                console.error('Error loading chat history:', e);
                return false;
            }
        },

        async saveHistory() {
            if (!this.currentThreadId) return;
            try {
                const toSave = this.chatHistory
                    .filter(item => item.timestamp)
                    .map(item => ({
                        role: item.role === 'user' ? 'user' : 'model',
                        parts: [{ text: item.text }],
                        timestamp: item.timestamp
                    }));
                const rawHistory = JSON.parse(JSON.stringify(toSave));
                await localforage.setItem(`chat_history_${this.currentThreadId}`, rawHistory);

                // Actualizar timestamp de modificación del hilo
                const activeThread = this.threads.find(t => t.id === this.currentThreadId);
                if (activeThread) {
                    activeThread.lastUpdated = Date.now();
                    // Reordenar para que el hilo más reciente esté arriba
                    this.threads.sort((a, b) => b.lastUpdated - a.lastUpdated);
                    await this.saveThreadsIndex();
                }
            } catch (e) {
                console.error('Error saving chat history:', e);
            }
        },

        // --- Manejo de Hilos (Multithread) ---

        generateUUID() {
            return 'thread-' + Math.random().toString(36).substr(2, 9) + '-' + Date.now().toString(36);
        },

        async loadThreadsIndex() {
            try {
                const stored = await localforage.getItem('chat_threads');
                if (stored) {
                    this.threads = typeof stored === 'string' ? JSON.parse(stored) : stored;
                } else {
                    this.threads = [];
                }

                const activeId = await localforage.getItem('active_thread_id');
                if (activeId && this.threads.some(t => t.id === activeId)) {
                    this.currentThreadId = activeId;
                } else if (this.threads.length > 0) {
                    this.currentThreadId = this.threads[0].id;
                } else {
                    await this.createNewThread();
                }
            } catch (e) {
                console.error("Error loading threads index:", e);
                this.threads = [];
                await this.createNewThread();
            }
        },

        async saveThreadsIndex() {
            try {
                const rawThreads = JSON.parse(JSON.stringify(this.threads));
                await localforage.setItem('chat_threads', rawThreads);
                await localforage.setItem('active_thread_id', this.currentThreadId);
            } catch (e) {
                console.error("Error saving threads index:", e);
            }
        },

        async createNewThread() {
            const newId = this.generateUUID();
            const newThread = {
                id: newId,
                title: 'Nueva Conversación',
                lastUpdated: Date.now()
            };
            this.threads.unshift(newThread);
            this.currentThreadId = newId;
            this.chatHistory = [];
            this.pushWelcomeMessage();
            await this.saveThreadsIndex();
            await this.saveHistory();
        },

        async switchThread(threadId) {
            if (this.currentThreadId === threadId) return;
            await this.saveHistory();

            this.currentThreadId = threadId;
            await localforage.setItem('active_thread_id', threadId);

            const restored = await this.loadHistory();
            if (!restored) {
                this.chatHistory = [];
                this.pushWelcomeMessage();
            }

            // Limpiar estados de interacción
            this.removeSkill();
            this.currentAttachment = null;
            this.lastSuggestions = [];
            this.editingThreadId = null;

            this.scrollToBottom();
        },

        async deleteThread(threadId) {
            if (!confirm('¿Estás seguro de que deseas eliminar esta conversación?')) return;
            try {
                await localforage.removeItem(`chat_history_${threadId}`);
                this.threads = this.threads.filter(t => t.id !== threadId);

                if (this.currentThreadId === threadId) {
                    if (this.threads.length > 0) {
                        this.currentThreadId = this.threads[0].id;
                        await this.loadHistory();
                    } else {
                        await this.createNewThread();
                    }
                }
                await this.saveThreadsIndex();
                this.showStatus("Conversación eliminada.", "indigo", 2000);
            } catch (e) {
                console.error("Error deleting thread:", e);
                this.showStatus("Error al eliminar conversación.", "red");
            }
        },

        startRename(thread) {
            this.editingThreadId = thread.id;
            this.editingThreadTitle = thread.title;
        },

        async saveRename(threadId) {
            if (!this.editingThreadTitle.trim()) {
                this.editingThreadId = null;
                return;
            }
            const thread = this.threads.find(t => t.id === threadId);
            if (thread) {
                thread.title = this.editingThreadTitle.trim();
                await this.saveThreadsIndex();
            }
            this.editingThreadId = null;
        },

        toggleHistorySidebar() {
            this.historySidebarOpen = !this.historySidebarOpen;
            localStorage.setItem('history-sidebar-open', this.historySidebarOpen);
        },

        /**
         * Carga skills dinámicos desde el backend y los agrega al menú slash
         */
        async loadSkills() {
            try {
                const response = await fetch('/api/skills');
                if (response.ok) {
                    const data = await response.json();
                    const skills = data.skills || data;
                    (Array.isArray(skills) ? skills : []).forEach(skill => {
                        this.allSlashCommands.push({
                            id: skill.id,
                            cmd: '/' + skill.id.replace(/_/g, '-'),
                            desc: skill.description || 'Agente especializado',
                            icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>',
                            isSkill: true,
                            prompt: '',
                            skillId: skill.id
                        });
                    });
                    console.log(`[Skills] ${(Array.isArray(skills) ? skills : []).length} skills cargados.`);
                }
            } catch (e) {
                console.error("Error cargando skills:", e);
            }
        },

        /**
         * Carga la lista de plantillas disponibles para el autocompletado @
         */
        async loadAvailableTemplates() {
            try {
                const token = localStorage.getItem('access_token');
                const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

                const response = await fetch('/api/templates-autocomplete', { headers });
                if (response.ok) {
                    const data = await response.json();
                    this.availableTemplates = (data.templates || []).map(name => {
                        const ext = name.includes('.') ? '.' + name.split('.').pop() : '';
                        const displayName = name.replace(/\.(md|docx|txt)$/i, '');
                        return { name, displayName, ext };
                    });
                    console.log(`[Templates] ${this.availableTemplates.length} plantillas cargadas para autocompletado @.`);
                } else {
                    console.warn('[Templates] Endpoint /api/templates-autocomplete no disponible, usando fallback.');
                    // Fallback: intentar cargar desde /templates
                    await this._loadTemplatesFallback();
                }
            } catch (e) {
                console.error("Error cargando plantillas para @:", e);
                // Fallback silencioso
                await this._loadTemplatesFallback();
            }
        },

        /**
         * Fallback para cargar plantillas si el endpoint principal no está disponible
         */
        async _loadTemplatesFallback() {
            try {
                const token = localStorage.getItem('access_token');
                if (!token) return;
                const response = await fetch('/templates', { headers: { 'Authorization': `Bearer ${token}` } });
                if (response.ok) {
                    const data = await response.json();
                    // Extraer nombres de las plantillas del JSON
                    const templateNames = [];
                    if (data.md_templates) templateNames.push(...data.md_templates);
                    if (data.docx_templates) templateNames.push(...data.docx_templates);
                    if (data.templates && Array.isArray(data.templates)) {
                        data.templates.forEach(t => {
                            if (typeof t === 'string') templateNames.push(t);
                            else if (t.filename) templateNames.push(t.filename);
                        });
                    }
                    this.availableTemplates = templateNames.map(name => {
                        const ext = name.includes('.') ? '.' + name.split('.').pop() : '';
                        const displayName = name.replace(/\.(md|docx|txt)$/i, '');
                        return { name, displayName, ext };
                    });
                }
            } catch (e) {
                console.warn('[Templates Fallback] No se pudieron cargar plantillas:', e.message);
            }
        },

        // =====================================================
        // INPUT HANDLING - Slash Commands y @ Mentions
        // =====================================================

        showStatus(message, color, duration = 3000) {
            this.status = { message, color };
            if (duration > 0) {
                setTimeout(() => {
                    if (this.status.message === message) {
                        this.status = { message: '', color: '' };
                    }
                }, duration);
            }
        },

        autoExpand() {
            this.$nextTick(() => {
                const textarea = this.$refs.textarea;
                if (!textarea) return;
                textarea.style.height = 'auto';
                const newHeight = textarea.scrollHeight;
                const maxHeight = 200;
                if (newHeight > maxHeight) {
                    textarea.style.height = `${maxHeight}px`;
                    textarea.style.overflowY = 'auto';
                } else {
                    textarea.style.height = `${newHeight}px`;
                    textarea.style.overflowY = 'hidden';
                }
            });
        },

        /**
         * Maneja cada pulsación de tecla en el textarea para detectar / y @
         * Usa el valor ACTUAL del textarea (e.target.value) para máxima precisión
         */
        handleInput(e) {
            const val = e.target.value;

            // --- Detección de SLASH COMMANDS ---
            // Se activa cuando el texto empieza con / y solo tiene caracteres de palabra
            if (val.startsWith('/')) {
                const match = val.match(/^\/(\w*)$/);
                if (match) {
                    this.slashFilter = val;
                    this.slashMenu.visible = true;
                    this.slashMenu.activeIndex = 0;
                    // Cerrar @ menu si estaba abierto
                    this.atMenu.visible = false;
                } else {
                    this.slashMenu.visible = false;
                }
            } else {
                this.slashMenu.visible = false;
            }

            // --- Detección de @ MENTIONS ---
            // Se activa cuando el usuario escribe @ en cualquier posición del texto
            if (!this.slashMenu.visible) {
                const cursorPos = e.target.selectionStart;
                const textBeforeCursor = val.substring(0, cursorPos);

                // Buscar el último @ antes del cursor que no esté precedido de una letra/número
                const atMatch = textBeforeCursor.match(/(^|[\s])@([\w\-\.]*)$/);

                if (atMatch) {
                    this.atFilter = atMatch[2] || '';  // Lo que viene después de @
                    this.atMenu.visible = true;
                    this.atMenu.activeIndex = 0;
                } else {
                    this.atMenu.visible = false;
                    this.atFilter = '';
                }
            } else {
                // Si slash menu está activo, cerrar @ menu
                this.atMenu.visible = false;
            }

            this.autoExpand();
        },

        /**
         * Maneja teclas especiales (flechas, Enter, Escape) para navegación de menús
         */
        handleKeydown(e) {
            // --- Navegación del SLASH MENU ---
            if (this.slashMenu.visible) {
                const itemsCount = this.filteredSlashCommands.length;
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    this.slashMenu.activeIndex = (this.slashMenu.activeIndex + 1) % itemsCount;
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    this.slashMenu.activeIndex = (this.slashMenu.activeIndex - 1 + itemsCount) % itemsCount;
                } else if (e.key === 'Enter') {
                    e.preventDefault();
                    if (this.filteredSlashCommands[this.slashMenu.activeIndex]) {
                        this.executeSlashCommand(this.filteredSlashCommands[this.slashMenu.activeIndex]);
                    }
                } else if (e.key === 'Escape') {
                    this.slashMenu.visible = false;
                } else if (e.key === 'Tab') {
                    e.preventDefault();
                    if (this.filteredSlashCommands[this.slashMenu.activeIndex]) {
                        this.executeSlashCommand(this.filteredSlashCommands[this.slashMenu.activeIndex]);
                    }
                }
                return;
            }

            // --- Navegación del @ MENU ---
            if (this.atMenu.visible) {
                const itemsCount = this.filteredAtMentions.length;
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    this.atMenu.activeIndex = (this.atMenu.activeIndex + 1) % itemsCount;
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    this.atMenu.activeIndex = (this.atMenu.activeIndex - 1 + itemsCount) % itemsCount;
                } else if (e.key === 'Enter' || e.key === 'Tab') {
                    e.preventDefault();
                    if (this.filteredAtMentions[this.atMenu.activeIndex]) {
                        this.selectAtMention(this.filteredAtMentions[this.atMenu.activeIndex]);
                    }
                } else if (e.key === 'Escape') {
                    this.atMenu.visible = false;
                }
                return;
            }

            // --- Enter normal (sin menú activo) ---
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.submitForm();
            }
        },

        // =====================================================
        // EJECUCIÓN DE COMANDOS
        // =====================================================

        /**
         * Ejecuta un slash command seleccionado del menú /
         */
        executeSlashCommand(command) {
            if (command.id === 'buscar' || command.id === 'expediente' || command.id === 'generador_documentos') {
                // Para /buscar, /expediente y /generador-documentos, dejar el prompt parcial para que el usuario complete
                this.userInput = command.cmd + " ";
            } else if (command.id === 'gestor_liquidaciones') {
                this.openLiquidacionModal();
            } else if (command.id === 'videollamada') {
                this.openMeetingModal();
                this.userInput = '';
                this.slashMenu.visible = false;
                return;
            } else {
                if (command.isSkill) {
                    // Activar modo agente especializado
                    this.activeSkill = {
                        id: command.skillId,
                        cmd: command.cmd,
                        desc: command.desc
                    };
                    this.userInput = "";
                    this.showStatus(`🟢 Agente activado: ${command.desc}`, "indigo", 3000);
                } else {
                    // Insertar prompt del comando
                    this.userInput = command.prompt;
                    if (command.systemPrompt) {
                        this.activeSystemPrompt = command.systemPrompt;
                        this.showStatus(`⚡ Modo activado: ${command.desc}`, "indigo", 3000);
                    }
                }
            }
            this.slashMenu.visible = false;
            this.$refs.textarea.focus();
            this.autoExpand();
        },

        openMeetingModal() {
            this.meetingModal.emails = '';
            this.meetingModal.documentName = this.currentAttachment ? this.currentAttachment.name : '';
            this.meetingModal.reason = 'Debate y Firma de Documento';
            this.meetingModal.sendInvitations = true;
            this.meetingModal.classification = 'chain_of_custody';
            this.meetingModal.disableIpfs = false;
            this.meetingModal.isOpen = true;
        },

        async submitMeetingCreate() {
            this.meetingModal.loading = true;
            try {
                const emailList = this.meetingModal.emails
                    .split(',')
                    .map(e => e.trim())
                    .filter(e => e.length > 0);

                const token = localStorage.getItem('access_token');
                const headers = { 'Content-Type': 'application/json' };
                if (token) headers['Authorization'] = `Bearer ${token}`;

                const response = await fetch('/api/meetings/create-instant', {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({
                        emails: emailList,
                        document_name: this.meetingModal.documentName || null,
                        reason: this.meetingModal.reason,
                        send_invitations: this.meetingModal.sendInvitations,
                        classification: this.meetingModal.classification,
                        disable_ipfs: this.meetingModal.disableIpfs
                    })
                });

                if (!response.ok) {
                    const errData = await response.json();
                    throw new Error(errData.detail || 'Error al crear la videollamada');
                }

                const data = await response.json();
                this.meetingModal.isOpen = false;

                if (window.showToast) {
                    window.showToast("¡Videollamada creada con éxito!", "success");
                }
                const docText = data.local_meeting_link;
                const messageText = '### 🎥 Sala de Videoconferencia Creada\n' +
                    'Se ha generado una sala de Meet para debatir/firmar.\n\n' +
                    '* **Motivo:** `' + this.meetingModal.reason + '`\n' +
                    '* **Documento:** `' + (this.meetingModal.documentName || 'Ninguno') + '`\n' +
                    '* **Invitados:** ' + (emailList.map(e => '`' + e + '`').join(', ') || 'Ninguno') + '\n\n' +
                    '👉 **[Entrar a la Videollamada (Star-Doc)](' + docText + ')**\n\n' +
                    '*Nota: Se han enviado las invitaciones correspondientes por correo electrónico.*';

                this.chatHistory.push({
                    id: Date.now(),
                    role: 'model',
                    text: messageText,
                    html: marked.parse(messageText),
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    isStreaming: false
                });

                this.saveHistory();
                this.scrollToBottom();

                const isPwa = window.isPwaStandalone && window.isPwaStandalone();
                const confirmMsg = isPwa
                    ? "¿Deseas entrar a la sala de videollamada ahora mismo?"
                    : "¿Deseas entrar a la sala de videollamada ahora mismo en una nueva pestaña?";
                const target = isPwa ? '_self' : '_blank';

                if (confirm(confirmMsg)) {
                    window.open(data.local_meeting_link, target);
                }
            } catch (e) {
                console.error(e);
                alert(e.message || "Error al crear videollamada.");
            } finally {
                this.meetingModal.loading = false;
            }
        },

        /**
         * Intercepta clics en enlaces dentro de los mensajes de chat para abrirlos en una pestaña nueva
         */
        handleMessageClick(e) {
            const link = e.target.closest('a');
            if (link) {
                const href = link.getAttribute('href');
                if (href) {
                    e.preventDefault();
                    const isPwa = window.isPwaStandalone && window.isPwaStandalone();
                    const isInternal = href.startsWith('/') || href.startsWith(window.location.origin);

                    if (isPwa && isInternal) {
                        window.location.href = href;
                    } else {
                        window.open(href, '_blank');
                    }
                }
            }
        },

        /**
         * Inserta una mención @plantilla en el textarea reemplazando el texto parcial
         */
        selectAtMention(template) {
            const textarea = this.$refs.textarea;
            const cursorPos = textarea.selectionStart;
            const text = this.userInput;

            // Encontrar la posición del @ que generó el menú
            const textBeforeCursor = text.substring(0, cursorPos);
            const atIndex = textBeforeCursor.lastIndexOf('@');

            if (atIndex !== -1) {
                // Reemplazar desde @ hasta el cursor con @nombre_archivo
                const before = text.substring(0, atIndex);
                const after = text.substring(cursorPos);
                // Usar el nombre de archivo sin extensión para mostrar, con extensión para el backend
                this.userInput = before + '@' + template.name + ' ' + after;

                // Mover cursor después de la mención insertada
                this.$nextTick(() => {
                    const newPos = atIndex + 1 + template.name.length + 1;
                    textarea.selectionStart = newPos;
                    textarea.selectionEnd = newPos;
                    textarea.focus();
                });
            }

            this.atMenu.visible = false;
            this.atFilter = '';
            this.showStatus(`📄 Plantilla '${template.displayName}' mencionada`, "green", 2000);
        },

        removeSkill() {
            this.activeSkill = null;
        },

        handleQuickAction(prompt) {
            this.userInput = prompt;
            this.submitForm();
        },

        selectSuggestion(text) {
            this.userInput = text;
            this.submitForm();
        },

        scrollToBottom() {
            this.$nextTick(() => {
                const container = this.$refs.messagesContainer;
                if (container) container.scrollTop = container.scrollHeight;
            });
        },

        // =====================================================
        // ARCHIVOS Y PLANTILLAS
        // =====================================================

        async handleFileUpload(e) {
            const file = e.target.files[0];
            if (!file) return;

            const validExtensions = ['.pdf', '.txt', '.md', '.docx'];
            const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
            if (!validExtensions.includes(fileExtension)) {
                this.showStatus("Formato no soportado. Usa PDF, DOCX, TXT o MD.", "red");
                this.$refs.fileInput.value = '';
                return;
            }

            this.showStatus(`Leyendo archivo: ${file.name}...`, "blue", 0);
            const formData = new FormData();
            formData.append('file', file);
            const token = localStorage.getItem('access_token');

            try {
                const response = await fetch('/api/documents/upload', {
                    method: 'POST',
                    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
                    body: formData
                });

                if (!response.ok) throw new Error("Error al procesar el archivo.");
                const data = await response.json();

                if (data.success && data.text) {
                    this.currentAttachment = { name: data.filename, text: data.text };
                    this.sidebarOpen = true;
                    this.sidebarTab = 'documento';
                    this.showStatus("Documento guardado en bóveda RAG.", "green");
                } else {
                    throw new Error("No se pudo extraer texto.");
                }
            } catch (error) {
                this.showStatus(`Error: ${error.message}`, "red");
                console.error(error);
            } finally {
                this.$refs.fileInput.value = '';
            }
        },

        async handleOcrUpload(e) {
            const file = e.target.files[0];
            if (!file) return;

            const validExtensions = ['.png', '.jpg', '.jpeg', '.webp', '.pdf'];
            const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
            if (!validExtensions.includes(fileExtension)) {
                this.showStatus("Formato no soportado para OCR. Usa PNG, JPG, JPEG, WEBP o PDF.", "red");
                this.$refs.ocrFileInput.value = '';
                return;
            }

            this.showStatus(`Iniciando OCR Multimodal con Gemini sobre: ${file.name}...`, "blue", 0);

            // Crear mensaje temporal de carga en el chat
            const tempMsgId = Date.now();
            const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            this.chatHistory.push({
                id: tempMsgId,
                role: 'model',
                text: '',
                html: `
                    <div class="flex items-center gap-3 py-2 text-indigo-400">
                        <div class="animate-spin rounded-full h-5 w-5 border-2 border-indigo-500 border-t-transparent"></div>
                        <span class="font-semibold text-sm">Procesando OCR con Gemini Multimodal... Leyendo "${file.name}"</span>
                    </div>
                `,
                timestamp: timestamp,
                isStreaming: true,
                statusText: 'Digitalizando e indexando en RAG...'
            });
            this.scrollToBottom();

            const formData = new FormData();
            formData.append('file', file);
            formData.append('category', 'OCR-Chat');

            const token = localStorage.getItem('access_token');

            try {
                const response = await fetch('/api/ocr/analyze', {
                    method: 'POST',
                    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
                    body: formData
                });

                // Remover el mensaje temporal para reemplazarlo por el definitivo
                const tempIndex = this.chatHistory.findIndex(m => m.id === tempMsgId);
                if (tempIndex !== -1) {
                    this.chatHistory.splice(tempIndex, 1);
                }

                if (!response.ok) {
                    const errData = await response.json().catch(() => ({}));
                    throw new Error(errData.detail || "Error al procesar el OCR del documento.");
                }

                const data = await response.json();

                if (data.success && data.extracted_text) {
                    // Guardar como attachment activo
                    this.currentAttachment = {
                        name: `OCR: ${data.filename}`,
                        text: data.extracted_text
                    };
                    this.sidebarOpen = true;
                    this.sidebarTab = 'documento';

                    // Formatear las variables en Markdown
                    let variablesMd = '';
                    if (data.variables && Object.keys(data.variables).length > 0) {
                        variablesMd = '\n### 🔑 Variables Contractuales Detectadas\n';
                        variablesMd += '| Variable | Valor Extraído |\n| --- | --- |\n';
                        for (const [key, val] of Object.entries(data.variables)) {
                            variablesMd += `| **${key}** | \`${val}\` |\n`;
                        }
                    } else {
                        variablesMd = '\n*(No se detectaron variables estructuradas específicas)*\n';
                    }

                    // Formatear un fragmento legible del texto extraído
                    const textSnippet = data.extracted_text.length > 500
                        ? data.extracted_text.substring(0, 500) + '\n\n...[Ver más en contexto adjunto]...'
                        : data.extracted_text;

                    // Crear respuesta premium
                    const finalMd = `### 🔍 OCR Multimodal - Digitalización Completa
El archivo **${data.filename}** ha sido procesado exitosamente usando **Gemini 2.5**.

#### 📄 Resumen de Operación:
- **Estado:** ✅ Completado con Éxito
- **Fragmentos Vectorizados en Bóveda:** \`${data.chunks_indexed} chunks\`
- **Mensaje:** ${data.message}

${variablesMd}

### 📝 Contenido Extraído (Vista Previa):
\`\`\`text
${textSnippet}
\`\`\`

---
> 📎 **Contexto Adjunto**: El texto completo de este documento ha sido cargado como **contexto activo** para tu chat. Puedes hacer preguntas directamente sobre él o pedirme que redacte un análisis legal detallado.`;

                    // Agregar mensaje del bot definitivo
                    this.chatHistory.push({
                        id: Date.now(),
                        role: 'model',
                        text: finalMd,
                        html: marked.parse(finalMd),
                        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                        isStreaming: false
                    });

                    this.showStatus("Documento digitalizado e indexado en la Bóveda RAG.", "green");
                } else {
                    throw new Error(data.message || "No se pudo extraer texto del archivo.");
                }
            } catch (error) {
                // Si falla, limpiar el temporal si aún existe
                const tempIndex = this.chatHistory.findIndex(m => m.id === tempMsgId);
                if (tempIndex !== -1) {
                    this.chatHistory.splice(tempIndex, 1);
                }

                this.showStatus(`Error OCR: ${error.message}`, "red");

                // Mostrar el error también en el chat
                this.chatHistory.push({
                    id: Date.now(),
                    role: 'model',
                    text: `❌ **Error procesando OCR Multimodal:** ${error.message}`,
                    html: `<div class="text-red-400 font-semibold p-2 border border-red-500/25 bg-red-950/20 rounded-xl">
                        <i class="bi bi-exclamation-triangle-fill mr-1.5"></i>
                        Error procesando OCR Multimodal: ${error.message}
                    </div>`,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    isStreaming: false
                });

                console.error(error);
            } finally {
                this.$refs.ocrFileInput.value = '';
                this.scrollToBottom();
                this.saveHistory();
            }
        },

        async openTemplateModal() {
            const token = localStorage.getItem('access_token');
            if (!token) { return this.showStatus("Error de autenticación.", "red"); }

            try {
                const response = await fetch('/templates-list/md', { headers: { 'Authorization': `Bearer ${token}` } });
                const result = await response.json();
                if (!response.ok || !result.success) throw new Error(result.detail || 'Error al cargar plantillas.');

                this.templates = result.templates;
                this.isTemplateModalOpen = true;
            } catch (error) {
                this.showStatus(error.message, 'red');
            }
        },

        async loadTemplateContent(filename) {
            const token = localStorage.getItem('access_token');
            if (!token) { return this.showStatus("Error de autenticación.", "red"); }

            try {
                const response = await fetch(`/template-content/${filename}`, { headers: { 'Authorization': `Bearer ${token}` } });
                if (!response.ok) throw new Error('No se pudo cargar el contenido.');
                const content = await response.text();

                this.currentAttachment = { name: filename + ' (Plantilla)', text: content };
                this.isTemplateModalOpen = false;
                this.showStatus(`Plantilla '${filename}' adjuntada como contexto.`, 'green');
            } catch (error) {
                this.showStatus(error.message, 'red');
            }
        },

        /**
         * Realiza una petición para obtener los campos clasificados de una plantilla y abre el modal
         */
        async openFieldsModal(templateName) {
            if (!templateName) return;
            const token = localStorage.getItem('access_token');
            this.showStatus(`Cargando campos de ${templateName}...`, "blue", 0);

            try {
                const response = await fetch(`/template-fields/${encodeURIComponent(templateName)}`, {
                    headers: token ? { 'Authorization': `Bearer ${token}` } : {}
                });

                if (!response.ok) throw new Error("No se pudieron cargar los campos de la plantilla.");
                const data = await response.json();

                if (data.success && data.fields) {
                    this.fieldsModal.templateName = templateName;
                    this.fieldsModal.fields = data.fields;
                    this.fieldsModal.values = {};

                    // Inicializar cada variable
                    data.fields.forEach(field => {
                        this.fieldsModal.values[field.name] = "";
                    });

                    // Inicializar el agrupamiento de pasos (Wizard)
                    this.initFieldsModalSteps();

                    this.fieldsModal.isOpen = true;
                    this.showStatus("Campos cargados.", "green", 1000);
                } else {
                    throw new Error(data.detail || "Error en la respuesta del servidor.");
                }
            } catch (error) {
                this.showStatus(`Error: ${error.message}`, "red");
                console.error(error);
            }
        },

        /**
         * Realiza una petición para obtener variables recomendadas por la IA para un documento inexistente en plantillas
         */
        async openDynamicFieldsModal(docDescription) {
            if (!docDescription) return;
            const token = localStorage.getItem('access_token');
            this.showStatus(`Analizando requisitos para "${docDescription}"...`, "blue", 0);

            try {
                const response = await fetch('/api/ai/dynamic-fields', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                    },
                    body: JSON.stringify({ description: docDescription })
                });

                if (!response.ok) throw new Error("No se pudieron generar las variables de redacción.");
                const data = await response.json();

                if (data.success && data.fields) {
                    this.fieldsModal.templateName = `Generador Guiado: ${docDescription}`;
                    this.fieldsModal.templateFilename = data.template_filename || null;
                    this.fieldsModal.fields = data.fields;
                    this.fieldsModal.values = {};

                    // Inicializar cada variable
                    data.fields.forEach(field => {
                        this.fieldsModal.values[field.name] = "";
                    });

                    // Inicializar el agrupamiento de pasos (Wizard)
                    this.initFieldsModalSteps();

                    this.fieldsModal.isOpen = true;
                    this.showStatus("Requisitos listos.", "green", 1000);
                } else {
                    throw new Error(data.detail || "Error en la respuesta del servidor.");
                }
            } catch (error) {
                this.showStatus(`Error: ${error.message}`, "red");
                console.error(error);
            }
        },

        /**
         * Evalúa si un campo de variable condicional debe ser visible basándose en su propiedad depends_on
         */
        isFieldVisible(field) {
            if (!field || !field.depends_on) return true;
            const parentName = field.depends_on.variable;
            const parentValue = this.fieldsModal.values[parentName];
            return parentValue === field.depends_on.equals;
        },

        /**
         * Procesa el formulario del modal, arma el prompt y lo pega en el chat
         */
        submitFieldsModal(sendDirectly = true) {
            if (!this.fieldsModal.templateName) return;

            let promptText = "";
            if (this.fieldsModal.templateFilename) {
                // Si el backend pre-creó una plantilla física Jinja2, usamos el flujo de llenado nativo
                promptText = `Por favor ayuda a llenar la plantilla @${this.fieldsModal.templateFilename} con los siguientes datos:\n`;
            } else if (this.fieldsModal.templateName.startsWith("Generador Guiado: ")) {
                const docName = this.fieldsModal.templateName.replace("Generador Guiado: ", "");
                promptText = `Actúa como un Abogado Senior Colombiano. Genera un borrador de contrato o documento legal completo, extenso, sumamente verboso y formal en formato Markdown para el siguiente tipo de documento: "${docName}".\n`;
                promptText += `Es crítico que redactes todas las cláusulas de forma exhaustiva e de nivel profesional, incluyendo declaraciones detalladas de las partes, objeto preciso del acuerdo, obligaciones sustanciales de cada parte, precio, formas de pago, plazos, cláusula penal pecuniaria, mecanismos alternativos de resolución de conflictos, domicilio contractual y espacios estructurados para firmas.\n`;
                promptText += `Fundamenta legalmente las cláusulas clave citando la normativa colombiana aplicable (ej. Código Civil, Código de Comercio o leyes especiales) para asegurar su validez probatoria.\n`;
                promptText += `Utiliza de forma obligatoria los siguientes datos recolectados para la redacción del borrador, asegurándote de no dejar campos vacíos ni placeholders genéricos:\n`;
            } else {
                promptText = `Por favor ayuda a llenar la plantilla @${this.fieldsModal.templateName} con los siguientes datos:\n`;
            }

            // Filtrar solo las variables de campos que son visibles actualmente
            const visibleFields = (this.fieldsModal.fields || []).filter(f => this.isFieldVisible(f));
            const visibleFieldNames = new Set(visibleFields.map(f => f.name));

            Object.entries(this.fieldsModal.values).forEach(([key, val]) => {
                if (visibleFieldNames.has(key)) {
                    const cleanVal = val ? val.toString().trim() : '';
                    promptText += `- ${key}: ${cleanVal || '(no especificado)'}\n`;
                }
            });

            this.userInput = promptText;
            this.fieldsModal.isOpen = false;

            this.$nextTick(() => {
                if (sendDirectly) {
                    this.submitForm();
                } else {
                    const textarea = this.$refs.textarea;
                    if (textarea) {
                        textarea.focus();
                        this.autoExpand();
                    }
                }
            });
        },

        /**
         * Agrupa dinámicamente las variables de la plantilla en pasos coherentes (Wizard)
         */
        initFieldsModalSteps() {
            const grouped = {
                partes: { id: 1, name: 'Partes', fields: [] },
                condiciones: { id: 2, name: 'Condiciones', fields: [] },
                pretensiones: { id: 3, name: 'Pretensiones / Cláusulas', fields: [] },
                anexos: { id: 4, name: 'Pruebas / Anexos', fields: [] },
                general: { id: 5, name: 'Otros datos', fields: [] }
            };

            const regexPartes = /(nombre|cedula|cc|identificacion|nit|representante|accionante|demandante|accionado|demandado|arrendador|arrendatario|deudor|acreedor|cliente|empresa|razon|correo|email|mail|telefono|celular|direccion|domicilio|partes|ciudad_cedula)/i;
            const regexCondiciones = /(fecha|plazo|canon|precio|valor|monto|hechos|descripcion|antecedentes|objeto|duracion|vencimiento|pago)/i;
            const regexPretensiones = /(pretension|peticion|solicitud|clausula|obligacion|multa|sancion|juramento|pretensiones|peticiones|clausulas)/i;
            const regexAnexos = /(prueba|anexo|documento|firma|testigo|pruebas|anexos)/i;

            this.fieldsModal.fields.forEach(field => {
                const fieldName = (field.name || '').toLowerCase();
                const fieldLabel = (field.label || '').toLowerCase();
                const searchStr = `${fieldName} ${fieldLabel}`;

                if (regexPartes.test(searchStr)) {
                    grouped.partes.fields.push(field);
                } else if (regexPretensiones.test(searchStr)) {
                    grouped.pretensiones.fields.push(field);
                } else if (regexCondiciones.test(searchStr)) {
                    grouped.condiciones.fields.push(field);
                } else if (regexAnexos.test(searchStr)) {
                    grouped.anexos.fields.push(field);
                } else {
                    grouped.general.fields.push(field);
                }
            });

            // Filtrar solo los grupos con campos y asignar IDs secuenciales
            const activeGroups = [];
            let stepId = 1;

            ['partes', 'condiciones', 'pretensiones', 'anexos', 'general'].forEach(key => {
                if (grouped[key].fields.length > 0) {
                    activeGroups.push({
                        id: stepId++,
                        name: grouped[key].name,
                        fields: grouped[key].fields
                    });
                }
            });

            // Paso de revisión final
            activeGroups.push({
                id: stepId++,
                name: 'Revisión',
                fields: [],
                isReview: true
            });

            this.fieldsModal.steps = activeGroups;
            this.fieldsModal.totalSteps = activeGroups.length;
            this.fieldsModal.currentStep = 1;
        },

        nextFieldsModalStep() {
            if (this.fieldsModal.currentStep < this.fieldsModal.totalSteps) {
                this.fieldsModal.currentStep++;
            }
        },

        prevFieldsModalStep() {
            if (this.fieldsModal.currentStep > 1) {
                this.fieldsModal.currentStep--;
            }
        },

        goToFieldsModalStep(stepId) {
            if (stepId >= 1 && stepId <= this.fieldsModal.totalSteps) {
                this.fieldsModal.currentStep = stepId;
            }
        },

        /**
         * Detecta si el texto indica intención de crear alguna plantilla disponible
         */
        detectDocumentIntent(text) {
            if (!text || !this.availableTemplates || this.availableTemplates.length === 0) return null;

            const cleanText = text.toLowerCase()
                .normalize("NFD").replace(/[\u0300-\u036f]/g, "");

            const intentPatterns = [
                /\b(crear|redactar|hacer|generar|llenar|necesito|quiero|elaborar|preparar|diseñar|formul[aó]r)\b/i,
                /\b(contrato|tutela|peticion|minuta|solicitud|formato|plantilla|documento)\b/i
            ];

            const hasIntent = intentPatterns.some(pattern => pattern.test(text));

            for (const tpl of this.availableTemplates) {
                let cleanTplName = tpl.displayName.toLowerCase()
                    .replace(/plantilla_/gi, '')
                    .replace(/_/g, ' ')
                    .normalize("NFD").replace(/[\u0300-\u036f]/g, "");

                // Coincidencia directa
                if (cleanText.includes(cleanTplName)) {
                    return tpl;
                }

                // Coincidencia difusa por palabras clave si hay intención general
                const words = cleanTplName.split(' ').filter(w => w.length > 3);
                if (hasIntent && words.length > 0 && words.every(word => cleanText.includes(word))) {
                    return tpl;
                }
            }

            return null;
        },

        openLiquidacionModal() {
            this.liquidacionModal.values = {
                salario_mensual: '',
                fecha_ingreso: '',
                fecha_retiro: '',
                tiene_auxilio_transporte: true,
                es_salario_integral: false,
                es_salario_variable: false,
                salario_promedio_prestaciones: '',
                salario_promedio_vacaciones: '',
                cesantias_pendientes_desde: '',
                prima_pendiente_desde: '',
                dias_vacaciones_pendientes: '',
                vacaciones_disfrutadas: 0,
                tipo_contrato: 'indefinido',
                causa_retiro: 'renuncia',
                fecha_fin_contrato: '',
                fecha_estimada_fin_obra: '',
                fecha_calculo_sancion_mora: new Date().toISOString().split('T')[0],
                estimar_sancion_mora: true
            };
            this.liquidacionModal.isOpen = true;
            this.slashMenu.visible = false;
        },

        submitLiquidacionModal(sendDirectly = true) {
            const vals = this.liquidacionModal.values;

            // Validaciones básicas de entrada
            if (!vals.salario_mensual || !vals.fecha_ingreso || !vals.fecha_retiro) {
                this.showStatus("Error: Salario mensual, Fecha de ingreso y de retiro son requeridos.", "red");
                return;
            }

            // Construir prompt estructurado
            let promptText = `Por favor, calcula la liquidación laboral para un empleado en Colombia (2026) con los siguientes datos:\n`;
            promptText += `- **Salario Mensual:** \$${vals.salario_mensual} COP\n`;
            promptText += `- **Fecha de Ingreso:** ${vals.fecha_ingreso}\n`;
            promptText += `- **Fecha de Retiro:** ${vals.fecha_retiro}\n`;
            promptText += `- **Tipo de Contrato:** ${vals.tipo_contrato}\n`;
            promptText += `- **Causa de Retiro:** ${vals.causa_retiro}\n`;
            promptText += `- **Auxilio de Transporte:** ${vals.tiene_auxilio_transporte ? 'Sí' : 'No'}\n`;
            promptText += `- **Salario Integral:** ${vals.es_salario_integral ? 'Sí' : 'No'}\n`;
            promptText += `- **Salario Variable:** ${vals.es_salario_variable ? 'Sí' : 'No'}\n`;

            if (vals.es_salario_variable) {
                if (vals.salario_promedio_prestaciones) promptText += `- **Salario Promedio Prestaciones:** \$${vals.salario_promedio_prestaciones} COP\n`;
                if (vals.salario_promedio_vacaciones) promptText += `- **Salario Promedio Vacaciones:** \$${vals.salario_promedio_vacaciones} COP\n`;
            }
            if (vals.tipo_contrato === 'termino_fijo' && vals.fecha_fin_contrato) {
                promptText += `- **Fecha Pactada Fin Contrato:** ${vals.fecha_fin_contrato}\n`;
            }
            if (vals.tipo_contrato === 'obra_labor' && vals.fecha_estimada_fin_obra) {
                promptText += `- **Fecha Estimada Fin Obra:** ${vals.fecha_estimada_fin_obra}\n`;
            }
            if (vals.cesantias_pendientes_desde) {
                promptText += `- **Cesantías/Intereses pendientes desde:** ${vals.cesantias_pendientes_desde}\n`;
            }
            if (vals.prima_pendiente_desde) {
                promptText += `- **Prima pendiente desde:** ${vals.prima_pendiente_desde}\n`;
            }
            if (vals.dias_vacaciones_pendientes !== null && vals.dias_vacaciones_pendientes !== '') {
                promptText += `- **Días de vacaciones pendientes:** ${vals.dias_vacaciones_pendientes}\n`;
            } else {
                promptText += `- **Días de vacaciones disfrutados:** ${vals.vacaciones_disfrutadas}\n`;
            }
            if (vals.estimar_sancion_mora && vals.fecha_calculo_sancion_mora) {
                promptText += `- **Fecha de Cálculo para Mora (Art. 65 CST):** ${vals.fecha_calculo_sancion_mora}\n`;
            }

            this.userInput = promptText;
            this.liquidacionModal.isOpen = false;

            // Activar skill en la barra del chat
            this.activeSkill = {
                id: 'gestor_liquidaciones',
                cmd: '/gestor-liquidaciones',
                desc: 'Cálculos y Acreencias Laborales (Colombia)'
            };

            this.$nextTick(() => {
                if (sendDirectly) {
                    this.submitForm();
                } else {
                    const textarea = this.$refs.textarea;
                    if (textarea) {
                        textarea.focus();
                        this.autoExpand();
                    }
                }
            });
        },

        // =====================================================
        // ENVÍO DE MENSAJES (Streaming SSE)
        // =====================================================

        async submitForm() {
            let userQuery = this.userInput.trim();
            if (!userQuery && !this.currentAttachment) return;

            // Interceptar comando /generador-documentos
            if (userQuery.toLowerCase().startsWith('/generador-documentos')) {
                const docDescription = userQuery.replace(/^\/generador-documentos\s*/i, '').trim();
                if (!docDescription) {
                    this.showStatus("Por favor especifica qué documento deseas generar. Ej: /generador-documentos Contrato de arrendamiento", "yellow", 4000);
                    return;
                }
                this.userInput = '';
                this.autoExpand();
                this.openDynamicFieldsModal(docDescription);
                return;
            }

            // Intentar detectar si el usuario está solicitando un documento específico de forma proactiva
            const suggestedTemplate = this.detectDocumentIntent(userQuery);
            if (suggestedTemplate) {
                this.proactiveTemplateSuggestion = suggestedTemplate;
            } else {
                this.proactiveTemplateSuggestion = null;
            }

            // Interceptar comando /riesgos escrito a mano
            if (userQuery.toLowerCase().startsWith('/riesgos')) {
                const cmdRiesgos = this.allSlashCommands.find(c => c.id === 'riesgos');
                if (cmdRiesgos) {
                    const extraText = userQuery.replace(/^\/riesgos\s*/i, '');
                    userQuery = cmdRiesgos.prompt + (extraText ? ' Enfoque específico: ' + extraText : '');
                    this.activeSystemPrompt = cmdRiesgos.systemPrompt;
                }
            } else if (userQuery.toLowerCase().startsWith('/ingestar')) {
                const cmdIngestar = this.allSlashCommands.find(c => c.id === 'ingestar');
                if (cmdIngestar) {
                    const extraText = userQuery.replace(/^\/ingestar\s*/i, '');
                    userQuery = cmdIngestar.prompt + extraText;
                    this.activeSystemPrompt = cmdIngestar.systemPrompt;
                }
            } else if (userQuery.toLowerCase().startsWith('/linea-juris')) {
                const cmdLinea = this.allSlashCommands.find(c => c.id === 'linea-juris');
                if (cmdLinea) {
                    const extraText = userQuery.replace(/^\/linea-juris\s*/i, '');
                    userQuery = cmdLinea.prompt + extraText;
                    this.activeSystemPrompt = cmdLinea.systemPrompt;
                }
            } else if (userQuery.toLowerCase().startsWith('/red-team')) {
                const cmdRedTeam = this.allSlashCommands.find(c => c.id === 'red-team');
                if (cmdRedTeam) {
                    const extraText = userQuery.replace(/^\/red-team\s*/i, '');
                    userQuery = cmdRedTeam.prompt + extraText;
                    this.activeSystemPrompt = cmdRedTeam.systemPrompt;
                }
            }

            let currentSysPrompt = this.activeSystemPrompt;
            this.activeSystemPrompt = ""; // Reset after use

            // Si es un análisis de riesgos, abrir la sidebar de inmediato y limpiar el estado previo
            const esRiesgos = currentSysPrompt && currentSysPrompt.includes("Auditor Legal Senior");
            if (esRiesgos) {
                this.sidebarOpen = true;
                this.sidebarTab = 'auditoria';
                this.legalAnalysis = null;
                this.legalAnalysisLoading = true;
            }

            this.userInput = '';
            this.autoExpand();

            const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            this.chatHistory.push({
                id: Date.now(),
                role: 'user',
                text: userQuery,
                html: userQuery.replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, '<br>'),
                timestamp: timestamp,
                isStreaming: false
            });
            this.lastSuggestions = []; // Limpiar sugerencias anteriores al enviar

            // Auto-titulado si es una conversación nueva
            const activeThread = this.threads.find(t => t.id === this.currentThreadId);
            if (activeThread && activeThread.title === 'Nueva Conversación') {
                let newTitle = userQuery.trim();
                newTitle = newTitle.replace(/^\/[a-zA-Z0-9-]+\s*/, '');
                newTitle = newTitle.split('\n')[0];
                if (newTitle.length > 28) {
                    newTitle = newTitle.substring(0, 25).trim() + '...';
                }
                if (!newTitle) {
                    newTitle = 'Consulta rápida';
                }
                activeThread.title = newTitle;
                this.saveThreadsIndex();
            }

            this.saveHistory();
            this.scrollToBottom();

            const modelMsgId = Date.now() + 1;
            const modelMsg = {
                id: modelMsgId,
                role: 'model',
                text: '',
                html: '',
                timestamp: '',
                isStreaming: true,
                statusText: 'Conectando...'
            };
            this.chatHistory.push(modelMsg);
            this.scrollToBottom();

            try {
                const token = localStorage.getItem('access_token');
                if (!token) throw new Error("No autenticado");

                const defaultPrompt = "Eres el asistente legal de STARCONTRACT... (reglas previas aplicables)";
                let systemPrompt = currentSysPrompt && currentSysPrompt.trim() ? currentSysPrompt.trim() : defaultPrompt;

                const cleanHistory = this.chatHistory
                    .filter(m => m.id !== modelMsgId && m.timestamp)
                    .map(m => ({ role: m.role, parts: [{ text: m.text }] }));

                const payload = {
                    prompt: userQuery,
                    history: cleanHistory,
                    system_instruction: systemPrompt,
                    stream: true
                };

                if (this.activeSkill) payload.skill_id = this.activeSkill.id;
                if (this.currentAttachment) {
                    payload.prompt = `CONTEXTO DEL DOCUMENTO ADJUNTO (${this.currentAttachment.name}):\n${this.currentAttachment.text}\n\n--- FIN DOCUMENTO ---\n\nPREGUNTA USUARIO:\n` + userQuery;
                }

                const genericSearchPattern = /\b(precio|cotizaci[oó]n|valor|cu[áa]nto vale|cotizaci[oó]n de|buscar|google|noticia|noticias|actualidad|novedad|novedades|reciente|hoy|ayer|últim[ao]|ley|decreto|sentencia|jurisprudencia)\b/i;
                if (genericSearchPattern.test(userQuery)) {
                    payload.web_search = true;
                    payload.search_query = userQuery;
                    payload.system_instruction = "Eres el asistente de STARCONTRACT... (Modo Búsqueda)";
                }

                const response = await fetch("/api/gemini", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);

                const reader = response.body.getReader();
                const decoder = new TextDecoder("utf-8");
                let done = false;
                let fullText = "";

                while (!done) {
                    const { value, done: readerDone } = await reader.read();
                    done = readerDone;
                    if (value) {
                        const chunk = decoder.decode(value, { stream: true });
                        const lines = chunk.split('\n');

                        for (const line of lines) {
                            if (line.startsWith('data: ')) {
                                try {
                                    const data = JSON.parse(line.substring(6));

                                    if (data.type === 'status') {
                                        modelMsg.statusText = data.msg;
                                    } else if (data.type === 'suggestions') {
                                        console.log('💡 Recibidas sugerencias inteligentes:', data.data);
                                        this.lastSuggestions = data.data;
                                    } else if (data.type === 'chunk') {
                                        modelMsg.statusText = '';
                                        fullText += data.text;
                                        modelMsg.text = fullText;

                                        // Extraer/ocultar sugerencias en tiempo real
                                        let displayText = fullText;
                                        const rMatch = displayText.match(/\|\|\|Suggestions:\s*(?:```json)?\s*(\[.*?\])\s*(?:```)?\s*\|\|\|/s);
                                        if (rMatch) {
                                            displayText = displayText.replace(rMatch[0], "").trim();
                                            try {
                                                this.lastSuggestions = JSON.parse(rMatch[1]);
                                            } catch (e) { }
                                        } else {
                                        }
                                        modelMsg.html = marked.parse(displayText);

                                        // Extraer Análisis Legal si viene en formato JSON estructurado
                                        const aMatch = fullText.match(/\|\|\|LegalAnalysis:\s*({.*?})\s*\|\|\|/s);
                                        if (aMatch) {
                                            try {
                                                let jsonStr = aMatch[1];
                                                // Limpieza robusta de formatos comunes de LLM que rompen JSON.parse
                                                jsonStr = jsonStr.replace(/True/g, "true").replace(/False/g, "false").replace(/None/g, "null");
                                                this.legalAnalysis = JSON.parse(jsonStr);
                                                this.sidebarOpen = true;
                                                this.legalAnalysisLoading = false;
                                                // Limpiar el tag de la respuesta visible
                                                modelMsg.html = marked.parse(displayText.replace(aMatch[0], "").trim());
                                            } catch (e) {
                                                console.warn("Error parseando LegalAnalysis:", e, aMatch[1]);
                                            }
                                        }
                                    } else if (data.type === 'error') {
                                        modelMsg.statusText = '';
                                        const errorMsg = data.msg || data.error || 'Error desconocido';
                                        fullText += `\n\n⚠️ **Error de API:** ${errorMsg}`;
                                        modelMsg.text = fullText;

                                        let errDisplayText = fullText;
                                        const openIdxE = errDisplayText.indexOf("|||Suggestions:");
                                        if (openIdxE !== -1) errDisplayText = errDisplayText.substring(0, openIdxE).trim();

                                        modelMsg.html = marked.parse(errDisplayText);
                                    }

                                    const index = this.chatHistory.findIndex(m => m.id === modelMsgId);
                                    if (index !== -1) {
                                        this.chatHistory.splice(index, 1, { ...modelMsg });
                                    }
                                    this.scrollToBottom();

                                } catch (e) {
                                    console.warn("Parse SSE error", e, line);
                                }
                            }
                        }
                    }
                }

                modelMsg.statusText = '';
                if (!fullText) fullText = "No se recibió respuesta.";

                modelMsg.text = fullText;

                // Extraer/ocultar al final de la lectura
                let finalDisplayText = fullText;
                const rMatch = finalDisplayText.match(/\|\|\|Suggestions:\s*(?:```json)?\s*(\[.*?\])\s*(?:```)?\s*\|\|\|/s);
                if (rMatch) {
                    finalDisplayText = finalDisplayText.replace(rMatch[0], "").trim();
                    try {
                        this.lastSuggestions = JSON.parse(rMatch[1]);
                    } catch (e) { }
                } else {
                    const openIdx = finalDisplayText.indexOf("|||Suggestions:");
                    if (openIdx !== -1) finalDisplayText = finalDisplayText.substring(0, openIdx).trim();
                }

                modelMsg.html = marked.parse(finalDisplayText);
                modelMsg.timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                modelMsg.isStreaming = false;

                // Buscar si la respuesta de la IA sugiere alguna plantilla disponible
                const suggestedTemplateAi = this.detectDocumentIntent(finalDisplayText);
                if (suggestedTemplateAi) {
                    this.proactiveTemplateSuggestion = suggestedTemplateAi;
                }

                const index = this.chatHistory.findIndex(m => m.id === modelMsgId);
                if (index !== -1) this.chatHistory.splice(index, 1, { ...modelMsg });

                this.saveHistory();
                this.scrollToBottom();

                if (this.currentAttachment) this.currentAttachment = null;
                this.legalAnalysisLoading = false;

                if (window.TTSController && !this.ttsPaused && this.ttsAutoRead) {
                    TTSController.onBotResponse(fullText);
                }

            } catch (error) {
                modelMsg.statusText = '';
                modelMsg.text = "Error al obtener respuesta: " + error.message;
                modelMsg.html = `<span class="text-red-500">Error: ${error.message}</span>`;
                modelMsg.isStreaming = false;

                const index = this.chatHistory.findIndex(m => m.id === modelMsgId);
                if (index !== -1) this.chatHistory.splice(index, 1, { ...modelMsg });

                this.legalAnalysisLoading = false;
                this.showStatus("Error al obtener respuesta", "red");
            }
        },

        // =====================================================
        // POST-RENDERING (Mermaid, Highlight.js)
        // =====================================================

        processPostRender(element, msg) {
            if (!element) return;
            element.querySelectorAll('pre code').forEach((block) => {
                if (block.classList.contains('language-mermaid') && !block.hasAttribute('data-processed')) {
                    const pre = block.parentElement;
                    const mermaidDiv = document.createElement('div');
                    mermaidDiv.className = 'mermaid';
                    mermaidDiv.textContent = block.textContent;
                    pre.replaceWith(mermaidDiv);
                    try {
                        mermaid.init(undefined, mermaidDiv);
                        block.setAttribute('data-processed', 'true');
                    } catch (e) { }
                } else if (!block.hasAttribute('data-highlighted') && !block.classList.contains('language-mermaid')) {
                    hljs.highlightElement(block);
                    block.setAttribute('data-highlighted', 'true');
                }
            });
        },

        // =====================================================
        // VOZ / SPEECH RECOGNITION
        // =====================================================

        setupSpeechRecognition() {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (SpeechRecognition) {
                this.recognition = new SpeechRecognition();
                this.recognition.continuous = false;
                this.recognition.lang = 'es-CO';
                this.recognition.interimResults = false;
                this.recognition.maxAlternatives = 1;

                this.recognition.onstart = () => {
                    this.isRecording = true;
                    this.showStatus('Escuchando...', '#6366f1', 0);
                };
                this.recognition.onresult = (event) => {
                    this.userInput += event.results[0][0].transcript;
                    this.autoExpand();
                };
                this.recognition.onspeechend = () => this.recognition.stop();
                this.recognition.onend = () => {
                    this.isRecording = false;
                    this.showStatus("", "");
                };
                this.recognition.onerror = (event) => {
                    const errorMsg = event.error == 'not-allowed' ? "Permiso de micrófono denegado." : `Error de voz: ${event.error}`;
                    this.showStatus(errorMsg, 'red', 10000);
                };
            }
        },

        toggleMic() {
            if (!this.recognition) {
                this.showStatus("Tu navegador no soporta reconocimiento de voz.", "orange");
                return;
            }
            if (this.isRecording) {
                this.recognition.stop();
            } else {
                try {
                    this.recognition.start();
                } catch (e) {
                    this.showStatus("El reconocimiento ya está activo.", "orange");
                }
            }
        },

        // =====================================================
        // UTILIDADES
        // =====================================================

        async clearChat() {
            this.chatHistory = [];
            if (this.currentThreadId) {
                try {
                    await localforage.removeItem(`chat_history_${this.currentThreadId}`);
                } catch (e) {
                    console.error("Error clearing thread history:", e);
                }
            }
            this.pushWelcomeMessage();
            this.userInput = '';
            this.autoExpand();
            this.removeSkill();
        },

        exportChat() {
            const chatText = this.chatHistory.map(msg => {
                const prefix = msg.role === 'user' ? '**Usuario:**' : '**Asistente:**';
                return `${prefix}\n\n${msg.text}`;
            }).join('\n\n---\n\n');

            const blob = new Blob([chatText], { type: 'text/markdown;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `chat-starcontract-${new Date().toISOString().slice(0, 10)}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            this.showStatus("Chat exportado.", 'green');
        },

        copyToClipboard(text) {
            navigator.clipboard.writeText(text)
                .then(() => this.showStatus("Copiado al portapapeles", "green"))
                .catch(() => this.showStatus("Error al copiar", "red"));
        },

        createTemplateFromMsg(text) {
            const filename = prompt("Nombre de la plantilla (.md):", "nueva_plantilla.md");
            if (filename && filename.endsWith('.md')) {
                const token = localStorage.getItem('access_token');
                fetch('/create-template-from-ia', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                    body: JSON.stringify({ filename, content: text })
                }).then(r => r.json())
                    .then(d => this.showStatus(d.message || "Creado", "green"))
                    .catch(e => this.showStatus(e.message, "red"));
            }
        },

        /**
         * Envía el texto Markdown de un mensaje del bot al backend para su descarga en DOCX o PDF
         */
        async downloadDocFromMsg(msg, format = 'docx') {
            if (!msg || !msg.text) return;
            const token = localStorage.getItem('access_token');
            const formatUpper = format.toUpperCase();
            this.showStatus(`Generando archivo ${formatUpper}...`, "blue", 0);

            try {
                // Determinar un título por defecto basado en la conversación o el hilo
                const activeThread = this.threads.find(t => t.id === this.currentThreadId);
                const title = activeThread ? activeThread.title : "Documento_Generado";

                // Extraer únicamente el bloque legal del documento, excluyendo diálogos, saludos o análisis del chat
                let cleanContent = msg.text || '';
                
                // 1. Limpieza de tags de control comunes del backend
                cleanContent = cleanContent.replace(/\|\|\|Suggestions:[\s\S]*?\|\|\|/g, "");
                cleanContent = cleanContent.replace(/\|\|\|LegalAnalysis:[\s\S]*?\|\|\|/g, "");
                
                // 2. Extraer bloque de código de Markdown si existe (típicamente comillas triples ```markdown)
                const markdownBlockRegex = /```(?:markdown|txt|html)?\s*\n([\s\S]*?)\n```/i;
                const match = cleanContent.match(markdownBlockRegex);
                if (match && match[1]) {
                    cleanContent = match[1].trim();
                } else {
                    // 3. Fallback: Si no hay bloques de código triples, buscar el inicio formal del documento legal
                    // Los borradores legales usualmente inician con títulos de nivel 1 (#) o nombres directos en mayúsculas
                    const startIndex = cleanContent.search(/^(?:#|\*\*|CONTRATO|MINUTA|DERECHO DE PETICIÓN|ACCIÓN DE TUTELA)/im);
                    if (startIndex !== -1) {
                        cleanContent = cleanContent.substring(startIndex).trim();
                    }
                    
                    // Recortar saludos de despedida comunes
                    const footerIndex = cleanContent.search(/\n\n(?:Espero que este|Quedo a tu|Recuerda que|Cualquier duda|Si necesitas)/im);
                    if (footerIndex !== -1) {
                        cleanContent = cleanContent.substring(0, footerIndex).trim();
                    }
                }
                
                cleanContent = cleanContent.trim();

                const response = await fetch('/api/generation/markdown-to-document', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                    },
                    body: JSON.stringify({
                        markdown_content: cleanContent,
                        filename: title,
                        format: format
                    })
                });

                if (!response.ok) throw new Error(`Error en la generación del documento ${formatUpper}.`);
                const data = await response.json();

                if (data.success && data.download_url) {
                    this.showStatus(`¡Archivo ${formatUpper} generado con éxito! Descargando...`, "green", 3000);
                    // Forzar descarga del archivo
                    const link = document.createElement('a');
                    link.href = data.download_url;
                    // Aseguramos que se descargue como adjunto
                    link.setAttribute('download', data.filename || `documento.${format}`);
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                } else {
                    throw new Error("No se devolvió la URL de descarga.");
                }
            } catch (error) {
                this.showStatus(`Error al descargar: ${error.message}`, "red");
                console.error(error);
            }
        },

        // =====================================================
        // TTS (Text-to-Speech)
        // =====================================================

        speakMsg(text) {
            if (!window.TTSController) {
                console.warn('[Alpine/TTS] TTSController no disponible');
                this.showStatus('TTS no disponible', 'red');
                return;
            }

            // Si ya hay audio, detenerlo primero
            if (this.isTTSPlaying) {
                TTSController.stopSpeaking();
                this.isTTSPlaying = false;
                this.ttsPaused = false;
            } else {
                // Iniciar nueva reproducción
                console.log('[Alpine/TTS] Iniciando lectura de mensaje');
                this.showStatus('🔊 Generando audio...', 'indigo', 0);
                TTSController.speakText(text).then(() => {
                    // Limpiar status después de que empiece a reproducir
                    setTimeout(() => {
                        if (this.status.message === '🔊 Generando audio...') {
                            this.status = { message: '', color: '' };
                        }
                    }, 1500);
                });
            }
        },

        toggleTTSAuto() {
            if (!window.TTSController) {
                this.showStatus('TTS no disponible', 'red');
                return;
            }
            this.ttsAutoRead = TTSController.toggleAutoRead();
            this.showStatus(
                this.ttsAutoRead ? '🔊 Auto-lectura activada' : '🔇 Auto-lectura desactivada',
                this.ttsAutoRead ? 'green' : 'gray',
                2500
            );
        },

        toggleTTSGlobalPause() {
            if (!window.TTSController || !this.isTTSPlaying) return;

            const isNowPlaying = TTSController.togglePlayPause();
            this.ttsPaused = !isNowPlaying;
            this.showStatus(
                this.ttsPaused ? '⏸️ Audio pausado' : '▶️ Audio reanudado',
                'indigo',
                1500
            );
        }
    }));
});
