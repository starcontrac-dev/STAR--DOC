/**
 * Controlador TTS (Text-to-Speech) para el chat de IA de STAR-DOC.
 * 
 * REFACTORIZADO: Este controlador es un servicio puro de audio.
 * NO manipula el DOM directamente. Alpine.js se encarga de la UI
 * leyendo las propiedades `isPlaying` y `isPaused` del controlador.
 * 
 * Integración: Se carga en ia.html y se conecta con el backend /api/tts/*
 */
window.TTSController = (() => {
    // === ESTADO INTERNO ===
    let currentAudio = null;           // Instancia Audio() del fragmento actual sonando
    let _isPlaying = false;            // Si la cola de reproducción está activa
    let _isPaused = false;             // Si la reproducción está pausada
    let autoReadEnabled = true;       // Lectura automática de respuestas (activo por defecto)
    let voices = [];                   // Voces disponibles cargadas del backend
    
    // Cola de reproducción fragmentada
    let audioQueue = [];               // Fragmentos de texto a leer
    let currentQueueIndex = 0;         // Índice del fragmento actual en la cola
    let prefetchedAudios = {};         // Mapa de index -> { audio, url } precargados en background
    let activeButtonEl = null;         // Botón que activó la reproducción para feedback visual
    let queueAbortController = null;     // Controlador de cancelación para peticiones activas

    let settings = {
        voice: 'es-MX-JorgeNeural',
        rate: '+35%',                  // Aumentado a +35% para una reproducción ágil y rápida
        volume: '+0%',
        pitch: '+0Hz',
        provider: 'auto'
    };

    // === CONSTANTES ===
    const STORAGE_KEY = 'stardoc_tts_settings';
    const API_BASE = '/api/tts';

    // === INICIALIZACIÓN ===

    /**
     * Inicializa el controlador TTS: carga preferencias y voces disponibles.
     */
    async function init() {
        loadPreferences();
        await loadVoices();
        console.log('[TTS] Controlador inicializado con cola de reproducción y precarga en background');
    }

    // === REPRODUCCIÓN DE AUDIO CON COLA Y PRECARGA ===

    /**
     * Divide el texto largo en oraciones o partes manejables de forma inteligente.
     * @param {string} text - Texto limpio a dividir
     * @param {number} maxLength - Longitud máxima ideal por fragmento
     * @returns {string[]} Arreglo de fragmentos de texto
     */
    function chunkText(text, maxLength = 1000) {
        if (text.length <= maxLength) return [text];

        const chunks = [];
        // Separar por oraciones respetando puntos, signos de interrogación o exclamación
        const sentences = text.match(/[^.!?]+[.!?]+(?:\s+|$)/g) || [text];
        
        let currentChunk = "";
        for (const sentence of sentences) {
            if (currentChunk.length + sentence.length <= maxLength) {
                currentChunk += sentence;
            } else {
                if (currentChunk.trim()) {
                    chunks.push(currentChunk.trim());
                }
                if (sentence.length > maxLength) {
                    // Si una sola oración es excepcionalmente larga, la dividimos por comas o punto y coma
                    const parts = sentence.match(/[^,;]+[,;]?(?:\s+|$)/g) || [sentence];
                    for (const part of parts) {
                        if (currentChunk.length + part.length <= maxLength) {
                            currentChunk += part;
                        } else {
                            if (currentChunk.trim()) {
                                chunks.push(currentChunk.trim());
                            }
                            currentChunk = part;
                        }
                    }
                } else {
                    currentChunk = sentence;
                }
            }
        }
        if (currentChunk.trim()) {
            chunks.push(currentChunk.trim());
        }
        return chunks;
    }

    /**
     * Convierte texto completo a voz y lo reproduce usando la cola asíncrona.
     * @param {string} text - Texto a convertir en audio
     * @param {HTMLElement} [buttonEl] - Botón que activó la reproducción (para feedback visual)
     */
    async function speakText(text, buttonEl = null) {
        // Detener cualquier audio o cola en curso
        stopSpeaking();

        if (!text || text.trim().length === 0) {
            console.warn('[TTS] Texto vacío, no se genera audio');
            return;
        }

        activeButtonEl = buttonEl;

        // Limpiar markdown y HTML del texto antes de enviarlo al TTS
        let cleanText = text
            .replace(/```[\s\S]*?```/g, '')       // Eliminar bloques de código
            .replace(/`[^`]*`/g, '')               // Eliminar código inline
            .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1') // Links: mantener texto
            .replace(/[#*_~>|]/g, '')              // Eliminar marcadores markdown
            .replace(/<[^>]*>/g, '')               // Eliminar tags HTML
            .replace(/\n{2,}/g, '. ')              // Párrafos a pausas
            .replace(/\n/g, ' ')                   // Saltos a espacios
            .trim();

        if (!cleanText) {
            console.warn('[TTS] Texto vacío después de limpiar');
            return;
        }

        // Fragmentar el texto en bloques para reproducción de baja latencia (soporte ilimitado de caracteres)
        audioQueue = chunkText(cleanText, 1000);
        currentQueueIndex = 0;
        prefetchedAudios = {};
        _isPlaying = true;
        _isPaused = false;

        console.log(`[TTS] Cola iniciada: ${audioQueue.length} fragmentos a procesar`);

        // Feedback visual: botón en estado "cargando"
        if (activeButtonEl) {
            activeButtonEl.classList.add('tts-loading');
            activeButtonEl.disabled = true;
        }

        // Reproducir el primer paso de la cola
        playQueueStep(0);
    }

    /**
     * Reproduce el fragmento en el índice indicado de la cola.
     * @param {number} index - Índice del fragmento
     */
    async function playQueueStep(index) {
        if (!_isPlaying) return;

        // Si hemos terminado la cola
        if (index >= audioQueue.length) {
            console.log('[TTS] Reproducción de cola completada.');
            finishSpeech();
            return;
        }

        currentQueueIndex = index;

        try {
            let audioObj = prefetchedAudios[index];
            let audioUrl = null;

            if (audioObj) {
                console.log(`[TTS] Reproduciendo fragmento precargado ${index + 1}/${audioQueue.length}`);
                currentAudio = audioObj.audio;
                audioUrl = audioObj.url;
            } else {
                console.log(`[TTS] Descargando fragmento al vuelo ${index + 1}/${audioQueue.length}...`);
                
                if (activeButtonEl && index === 0) {
                    activeButtonEl.classList.add('tts-loading');
                    activeButtonEl.disabled = true;
                }

                const result = await fetchSpeechAudio(audioQueue[index]);
                if (!result) return; // Cancelado o error

                currentAudio = result.audio;
                audioUrl = result.url;
            }

            // Manejadores de reproducción
            currentAudio.onended = () => {
                if (audioUrl) URL.revokeObjectURL(audioUrl);
                delete prefetchedAudios[index];
                playQueueStep(index + 1);
            };

            currentAudio.onerror = (e) => {
                console.error(`[TTS] Error en fragmento ${index + 1}:`, e);
                if (audioUrl) URL.revokeObjectURL(audioUrl);
                delete prefetchedAudios[index];
                // Saltar al siguiente fragmento para no colgar la reproducción global
                playQueueStep(index + 1);
            };

            // Activar estado visual de reproducción en el botón
            if (activeButtonEl) {
                activeButtonEl.classList.remove('tts-loading');
                activeButtonEl.classList.add('tts-playing');
                activeButtonEl.disabled = false;
            }

            await currentAudio.play();
            _isPaused = false;

            // Lanzar la precarga en background del siguiente fragmento
            prefetchQueueStep(index + 1);

        } catch (error) {
            console.error(`[TTS] Error en el paso de cola ${index}:`, error);
            playQueueStep(index + 1);
        }
    }

    /**
     * Realiza la descarga del fragmento de audio.
     * @param {string} textChunk - Fragmento de texto
     * @param {AbortSignal} [signal] - Señal de cancelación
     * @returns {Promise<{audio: HTMLAudioElement, url: string}|null>} Objeto de audio o null
     */
    async function fetchSpeechAudio(textChunk, signal = null) {
        try {
            if (!signal) {
                if (queueAbortController) queueAbortController.abort();
                queueAbortController = new AbortController();
                signal = queueAbortController.signal;
            }

            const response = await fetch(`${API_BASE}/speak`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: textChunk,
                    voice: settings.voice,
                    rate: settings.rate,
                    volume: settings.volume,
                    pitch: settings.pitch,
                    provider: settings.provider
                }),
                signal: signal
            });

            if (!response.ok) {
                throw new Error(`Servidor devolvió HTTP ${response.status}`);
            }

            const audioBlob = await response.blob();
            if (signal.aborted) return null;

            if (audioBlob.size === 0) {
                throw new Error('Audio vacío');
            }

            const url = URL.createObjectURL(audioBlob);
            const audio = new Audio(url);
            return { audio, url };
        } catch (e) {
            if (e.name !== 'AbortError') {
                console.error('[TTS] Error en descarga:', e.message);
            }
            return null;
        }
    }

    /**
     * Precarga en segundo plano el fragmento de audio del siguiente índice.
     * @param {number} nextIndex - Índice a precargar
     */
    async function prefetchQueueStep(nextIndex) {
        if (!_isPlaying || nextIndex >= audioQueue.length) return;
        if (prefetchedAudios[nextIndex]) return; // Ya precargado

        console.log(`[TTS] Precargando en background fragmento ${nextIndex + 1}/${audioQueue.length}...`);

        const prefetchController = new AbortController();
        if (queueAbortController) {
            queueAbortController.signal.addEventListener('abort', () => prefetchController.abort());
        }

        const result = await fetchSpeechAudio(audioQueue[nextIndex], prefetchController.signal);
        if (result && _isPlaying) {
            prefetchedAudios[nextIndex] = result;
            console.log(`[TTS] Precarga lista para fragmento ${nextIndex + 1}/${audioQueue.length}`);
        }
    }

    /**
     * Limpia estados al finalizar correctamente la lectura.
     */
    function finishSpeech() {
        _isPlaying = false;
        _isPaused = false;

        // Limpiar todas las URLs de blobs y audios precargados restantes
        for (const key in prefetchedAudios) {
            if (prefetchedAudios[key]) {
                if (prefetchedAudios[key].url) {
                    URL.revokeObjectURL(prefetchedAudios[key].url);
                }
            }
        }

        prefetchedAudios = {};
        audioQueue = [];
        currentAudio = null;

        if (activeButtonEl) {
            activeButtonEl.classList.remove('tts-playing', 'tts-loading');
            activeButtonEl.disabled = false;
            activeButtonEl = null;
        }

        document.querySelectorAll('.tts-playing, .tts-loading').forEach(el => {
            el.classList.remove('tts-playing', 'tts-loading');
            el.disabled = false;
        });
    }

    /**
     * Detiene la reproducción de audio actual y limpia colas.
     */
    function stopSpeaking() {
        _isPlaying = false;
        _isPaused = false;

        if (queueAbortController) {
            queueAbortController.abort();
            queueAbortController = null;
        }

        if (currentAudio) {
            try {
                currentAudio.pause();
                currentAudio.currentTime = 0;
            } catch (e) {}
            currentAudio = null;
        }

        // Limpiar y liberar blobs precargados
        for (const key in prefetchedAudios) {
            if (prefetchedAudios[key]) {
                if (prefetchedAudios[key].audio) {
                    try { prefetchedAudios[key].audio.pause(); } catch(e){}
                }
                if (prefetchedAudios[key].url) {
                    URL.revokeObjectURL(prefetchedAudios[key].url);
                }
            }
        }
        prefetchedAudios = {};
        audioQueue = [];

        if (activeButtonEl) {
            activeButtonEl.classList.remove('tts-playing', 'tts-loading');
            activeButtonEl.disabled = false;
            activeButtonEl = null;
        }

        document.querySelectorAll('.tts-playing, .tts-loading').forEach(el => {
            el.classList.remove('tts-playing', 'tts-loading');
            el.disabled = false;
        });
    }

    /**
     * Pausa o reanuda la reproducción actual de la cola.
     * @returns {boolean} true si está reproduciendo, false si está pausado
     */
    function togglePlayPause() {
        if (!currentAudio) return false;

        if (currentAudio.paused) {
            currentAudio.play();
            _isPaused = false;
            console.log('[TTS] Cola reanudada');
            return true;
        } else {
            currentAudio.pause();
            _isPaused = true;
            console.log('[TTS] Cola pausada');
            return false;
        }
    }

    // === VOCES ===

    /**
     * Carga las voces disponibles desde el backend.
     */
    async function loadVoices() {
        try {
            const response = await fetch(`${API_BASE}/voices?locale=es`);
            if (response.ok) {
                const data = await response.json();
                voices = data.voices || [];
                console.log(`[TTS] ${voices.length} voces cargadas`);
            } else {
                console.warn(`[TTS] Error cargando voces: HTTP ${response.status}`);
            }
        } catch (error) {
            console.error('[TTS] Error cargando voces:', error.message);
        }
    }

    /**
     * Retorna la lista de voces disponibles.
     */
    function getVoices() {
        return voices;
    }

    // === CONFIGURACIÓN ===

    /**
     * Actualiza la configuración de voz.
     * @param {Object} newSettings - Nuevas configuraciones parciales
     */
    function updateSettings(newSettings) {
        settings = { ...settings, ...newSettings };
        savePreferences();
        console.log('[TTS] Configuración actualizada:', settings);
    }

    /**
     * Retorna la configuración actual.
     */
    function getSettings() {
        return { ...settings };
    }

    // === AUTO-LECTURA ===

    /**
     * Activa o desactiva la lectura automática de respuestas del bot.
     * @param {boolean} [enabled] - Si no se pasa, alterna el estado
     * @returns {boolean} Estado actual de auto-lectura
     */
    function toggleAutoRead(enabled) {
        if (typeof enabled === 'boolean') {
            autoReadEnabled = enabled;
        } else {
            autoReadEnabled = !autoReadEnabled;
        }
        savePreferences();
        console.log(`[TTS] Auto-lectura: ${autoReadEnabled ? 'ACTIVADA' : 'DESACTIVADA'}`);
        return autoReadEnabled;
    }

    /**
     * Retorna si la auto-lectura está activa.
     */
    function isAutoReadEnabled() {
        return autoReadEnabled;
    }

    /**
     * Debe llamarse cuando llega una nueva respuesta del bot.
     * Si auto-lectura está activa, reproduce el texto.
     * @param {string} text - Texto de la respuesta del bot
     */
    function onBotResponse(text) {
        if (autoReadEnabled && text) {
            console.log('[TTS] Auto-lectura: leyendo respuesta del bot');
            speakText(text);
        }
    }

    // === PERSISTENCIA ===

    /**
     * Guarda las preferencias en localStorage.
     */
    function savePreferences() {
        try {
            const prefs = {
                ...settings,
                autoRead: autoReadEnabled
            };
            localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
        } catch (e) {
            console.warn('[TTS] No se pudo guardar preferencias:', e);
        }
    }

    /**
     * Carga las preferencias de localStorage.
     */
    function loadPreferences() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {
                const prefs = JSON.parse(saved);
                settings.voice = prefs.voice || settings.voice;
                settings.rate = prefs.rate || settings.rate;
                settings.volume = prefs.volume || settings.volume;
                settings.pitch = prefs.pitch || settings.pitch;
                settings.provider = prefs.provider || settings.provider;
                autoReadEnabled = (prefs.autoRead !== undefined) ? prefs.autoRead : true;
                console.log('[TTS] Preferencias cargadas. Auto-lectura:', autoReadEnabled);
            }
        } catch (e) {
            console.warn('[TTS] No se pudo cargar preferencias:', e);
        }
    }

    // === API PÚBLICA ===
    return {
        init,
        speakText,
        stopSpeaking,
        loadVoices,
        getVoices,
        updateSettings,
        getSettings,
        toggleAutoRead,
        isAutoReadEnabled,
        togglePlayPause,
        onBotResponse,
        // Getters reactivos para que Alpine.js lea el estado
        get isPlaying() { return _isPlaying; },
        get isPaused() { return _isPaused; }
    };
})();

// Inicializar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    TTSController.init();
});
