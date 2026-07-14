/**
 * =====================================================
 * STAR-DOC :: Controlador de Sala de Negociación Virtual
 * =====================================================
 */
document.addEventListener("DOMContentLoaded", () => {
    // 1. Cargar Variables de Contexto de la Sala (Inyectadas en meeting.html globalmente)
    const domain = window.JITSI_DOMAIN || "meet.jit.si";
    const roomName = window.ROOM_NAME;
    const documentFilename = window.DOCUMENT_FILENAME;
    const signerName = window.SIGNER_NAME || "Participante";

    // 2. Inicializar IFrame de Jitsi Meet con configuraciones de alta estabilidad y Closed Captions
    const container = document.querySelector('#jitsi-meet-container');
    const options = {
        roomName: roomName,
        width: '100%',
        height: '100%',
        parentNode: container,
        configOverwrite: {
            startWithAudioMuted: false,
            startWithVideoMuted: false,
            prejoinPageEnabled: false,
            enableWelcomePage: false,
            disableDeepLinking: true,
            lobby: { enabled: false }, // Desactivar lobby para evitar caídas
            requireDisplayName: true,
            // Parámetros de estabilidad y ahorro de ancho de banda
            channelLastN: 4, // Ver máximo 4 videos para priorizar ancho de banda de audio y red
            constraints: {
                video: {
                    height: { ideal: 360, max: 360, min: 180 } // Forzar resolución ligera para evitar caídas de red
                }
            },
            disableAudioLevels: true, // Reducir procesamiento en CPU
            enableLayerSuspension: true,
            enableGroupCall: true
        },
        interfaceConfigOverwrite: {
            TOOLBAR_BUTTONS: [
                'microphone', 'camera', 'closedcaptions', 'desktop', 'embedmeeting', 'fullscreen',
                'fodeviceselection', 'hangup', 'profile', 'chat', 'recording',
                'livestreaming', 'etherpad', 'sharedvideo', 'settings', 'raisehand',
                'videoquality', 'filmstrip', 'invite', 'feedback', 'stats', 'shortcuts',
                'tileview', 'videobackgroundblur', 'download', 'help', 'mute-everyone',
                'security'
            ],
            SETTINGS_SECTIONS: [ 'devices', 'language', 'moderator', 'profile', 'calendar' ],
            SHOW_JITSI_WATERMARK: false,
            SHOW_WATERMARK_FOR_GUESTS: false
        }
    };

    const api = new JitsiMeetExternalAPI(domain, options);
    window.jitsiApi = api;

    // 3. Medidor de Calidad de Red (Jitsi API Listener)
    api.addEventListener('connectionQualityChanged', (event) => {
        const quality = event.connectionQuality; // Rango de 0 a 100%
        console.log(`Calidad de red Jitsi: ${quality}%`);
        
        const netIndicator = document.getElementById("net-quality-indicator");
        if (netIndicator) {
            if (quality < 50) {
                netIndicator.classList.remove("hidden");
                netIndicator.innerHTML = `
                    <div class="flex items-center gap-2 px-3 py-1 bg-red-600/90 text-white rounded-lg border border-red-500 text-[10px] font-bold shadow-lg animate-pulse">
                        <span class="w-1.5 h-1.5 rounded-full bg-white animate-ping"></span>
                        Red inestable (${quality}%). Se recomienda pausar lecturas o firmas legales.
                    </div>
                `;
            } else {
                netIndicator.classList.add("hidden");
            }
        }
    });

    // 4. Lógica de Maximización y Responsividad del Layout
    const jitsiPanel = document.getElementById('jitsi-panel');
    const pdfPanel = document.getElementById('pdf-panel');
    const btnMaximizeJitsi = document.getElementById('btn-maximize-jitsi');
    const btnMaximizePdf = document.getElementById('btn-maximize-pdf');
    const btnClosePdf = document.getElementById('btn-close-pdf');
    const btnFloatingPdf = document.getElementById('btn-floating-pdf');

    let isJitsiMaximized = false;
    let isPdfMaximized = false;

    const svgExpand = `<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5" />
    </svg>`;

    const svgCollapse = `<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4h16v16H4V4z M9 9h6v6H9V9z" />
    </svg>`;

    function toggleJitsiMaximize() {
        if (isJitsiMaximized) {
            jitsiPanel.classList.remove('fixed', 'inset-0', 'inset-x-3', 'inset-y-16', 'md:inset-4', 'z-40', 'h-[85vh]', 'h-full', 'w-full', 'p-2', 'md:h-auto', 'bg-slate-950');
            jitsiPanel.classList.add('w-full', 'md:w-1/2', 'h-full');
            btnMaximizeJitsi.innerHTML = svgExpand;
            btnMaximizeJitsi.setAttribute('title', 'Maximizar videollamada');
            isJitsiMaximized = false;
        } else {
            if (isPdfMaximized) togglePdfMaximize(false);
            jitsiPanel.classList.remove('w-full', 'md:w-1/2', 'h-full');
            
            if (window.innerWidth < 768) {
                // En móviles ocupa toda la pantalla para evitar recortes de barras del navegador
                jitsiPanel.classList.add('fixed', 'inset-0', 'z-40', 'w-full', 'h-full', 'p-2', 'bg-slate-950');
            } else {
                // En desktop usa el recuadro flotante clásico
                jitsiPanel.classList.add('fixed', 'inset-x-3', 'inset-y-16', 'md:inset-4', 'z-40', 'md:h-[calc(100vh-2rem)]');
            }
            
            btnMaximizeJitsi.innerHTML = svgCollapse;
            btnMaximizeJitsi.setAttribute('title', 'Restaurar tamaño');
            isJitsiMaximized = true;
        }
    }

    function togglePdfMaximize(forceState = null) {
        const nextState = forceState !== null ? forceState : !isPdfMaximized;
        if (!nextState) {
            pdfPanel.classList.remove('fixed', 'inset-0', 'md:inset-4', 'z-40', 'w-full', 'h-full', 'md:h-[calc(100vh-2rem)]', 'p-3', 'md:p-0', 'bg-slate-950');
            pdfPanel.classList.add('hidden', 'md:flex', 'w-full', 'md:w-1/2', 'h-full');
            btnClosePdf.classList.add('hidden');
            btnMaximizePdf.classList.remove('hidden');
            btnMaximizePdf.innerHTML = svgExpand;
            btnMaximizePdf.setAttribute('title', 'Maximizar documento');
            isPdfMaximized = false;
        } else {
            if (isJitsiMaximized) toggleJitsiMaximize();
            pdfPanel.classList.remove('hidden', 'md:flex', 'w-full', 'md:w-1/2', 'h-full');
            pdfPanel.classList.add('fixed', 'inset-0', 'z-40', 'w-full', 'h-full', 'p-3', 'bg-slate-950');
            btnClosePdf.classList.remove('hidden');
            
            if (window.innerWidth < 768) {
                btnMaximizePdf.classList.add('hidden');
            } else {
                btnMaximizePdf.innerHTML = svgCollapse;
                btnMaximizePdf.setAttribute('title', 'Restaurar tamaño');
            }
            isPdfMaximized = true;
        }
    }

    btnMaximizeJitsi.addEventListener('click', toggleJitsiMaximize);
    btnMaximizePdf.addEventListener('click', () => togglePdfMaximize());
    btnClosePdf.addEventListener('click', () => togglePdfMaximize(false));
    btnFloatingPdf.addEventListener('click', () => togglePdfMaximize(true));

    window.addEventListener('resize', () => {
        if (isPdfMaximized && window.innerWidth >= 768) {
            btnMaximizePdf.classList.remove('hidden');
        } else if (isPdfMaximized && window.innerWidth < 768) {
            btnMaximizePdf.classList.add('hidden');
        }
    });

    // 5. Selector del PDF
    const pdfSelector = document.getElementById("pdf-selector");
    const pdfViewer = document.getElementById("pdf-viewer-iframe");
    const pdfNameDisplay = document.getElementById("pdf-name-display");

    pdfSelector.addEventListener("change", (e) => {
        const selectedFile = e.target.value;
        pdfViewer.src = `/output/${selectedFile}`;
        if (pdfNameDisplay) pdfNameDisplay.innerText = selectedFile;
    });

    // 6. Transcripción por Voz e Integración Híbrida Jitsi (Captions + Web Speech API)
    const btnToggleMic = document.getElementById("btn-toggle-mic");
    const micIndicator = document.getElementById("mic-indicator");
    const micText = document.getElementById("mic-text");
    const liveTranscriptionStatus = document.getElementById("live-transcription-status");

    let recognition = null;
    let wsSocket = null;
    let isTranscribingLocal = false;

    // Variables de control de audio de la sesión
    let sessionAudioStream = null;
    let sessionMediaRecorder = null;
    let sessionAudioChunks = [];
    let isRecordingSessionAudio = false;

    // Conectar WebSocket de fondo de forma automática para la sala al entrar en la reunión
    function connectTranscriptionWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/meetings/ws-transcription/${roomName}`;
        
        try {
            wsSocket = new WebSocket(wsUrl);
            
            wsSocket.onopen = () => {
                console.log("WebSocket de transcripción en segundo plano conectado exitosamente.");
            };
            
            wsSocket.onmessage = (event) => {
                console.log("ACK Servidor Transcripción:", event.data);
            };
            
            wsSocket.onclose = () => {
                console.log("WebSocket de transcripción cerrado. Intentando reconectar en 5 segundos...");
                setTimeout(connectTranscriptionWebSocket, 5000);
            };
            
            wsSocket.onerror = (err) => {
                console.error("Error en WebSocket de transcripción:", err);
            };
        } catch (wsErr) {
            console.error("Error al establecer conexión WebSocket:", wsErr);
        }
    }

    // Inicializar WebSocket de inmediato
    connectTranscriptionWebSocket();

    // ESCUCHAR SUBTÍTULOS DE JITSI MEET (Closed Captions)
    // El motor en la nube de Jitsi Meet transcribe el audio y emite el evento captionReceived.
    // Esto funciona incluso en HTTP sin SSL y sin conflictos de hardware.
    if (api) {
        api.addEventListener('captionReceived', (event) => {
            console.log("Transcripción/Subtítulo capturado de Jitsi Meet:", event);
            const sender = event.senderName || "Participante";
            const text = event.text;
            
            if (text && text.trim() !== "") {
                if (wsSocket && wsSocket.readyState === WebSocket.OPEN) {
                    wsSocket.send(`[${sender}]: ${text.trim()}`);
                    if (liveTranscriptionStatus) {
                        liveTranscriptionStatus.classList.remove("hidden");
                        liveTranscriptionStatus.innerText = "Jitsi transcribiendo...";
                        setTimeout(() => {
                            if (!isTranscribingLocal && liveTranscriptionStatus) {
                                liveTranscriptionStatus.classList.add("hidden");
                            }
                        }, 3000);
                    }
                }
            }
        });
    }

    // Inicializar la Web Speech API local en el navegador del cliente
    function initVoiceTranscription() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            if (window.showToast) window.showToast("Este navegador no soporta transcripción por voz local. Utilice Closed Captions de Jitsi o Chrome.", "warning");
            return;
        }

        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.lang = 'es-CO';

        try {
            isTranscribingLocal = true;

            // Iniciar reconocimiento de voz de manera síncrona en el hilo del evento del usuario
            try {
                recognition.start();
                console.log("Reconocimiento de voz local iniciado.");
            } catch (recStartErr) {
                console.error("Error al iniciar reconocimiento local:", recStartErr);
            }
            
            // Actualizar interfaz
            micIndicator.className = "w-2 h-2 rounded-full bg-red-500 animate-pulse";
            micText.innerText = "Detener Transcripción";
            liveTranscriptionStatus.classList.remove("hidden");
            liveTranscriptionStatus.innerText = "Escuchando voz local...";

            recognition.onresult = (event) => {
                const resultIndex = event.resultIndex;
                const transcript = event.results[resultIndex][0].transcript;
                const isFinal = event.results[resultIndex].isFinal;

                if (isFinal && transcript.trim() !== "") {
                    console.log("Voz local detectada:", transcript);
                    if (wsSocket && wsSocket.readyState === WebSocket.OPEN) {
                        wsSocket.send(`[${signerName}]: ${transcript}`);
                        liveTranscriptionStatus.innerText = "Voz enviada ✓";
                        setTimeout(() => {
                            if (isTranscribingLocal) liveTranscriptionStatus.innerText = "Escuchando voz local...";
                        }, 2000);
                    }
                }
            };

            recognition.onend = () => {
                if (isTranscribingLocal) {
                    try {
                        recognition.start(); // Reconectar SpeechRecognition local
                    } catch (e) {
                        console.error("Error al reiniciar reconocimiento local:", e);
                    }
                }
            };

            recognition.onerror = (e) => {
                console.error("Error en Web Speech API local:", e.error);
                
                if (e.error === 'not-allowed') {
                    let advice = "Permiso al micrófono denegado.";
                    if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') {
                        advice += " NOTA: La Web Speech API local requiere una conexión HTTPS. Active 'Closed Captions' en la videollamada de Jitsi Meet para transcribir bajo HTTP.";
                    } else {
                        advice += " Conceda permisos de micrófono a la página.";
                    }
                    if (window.showToast) window.showToast(advice, "warning");
                    stopTranscriptionFlow();
                } else if (e.error === 'audio-capture') {
                    const advice = "Micrófono ocupado por Jitsi Meet u otra pestaña. Utilice Closed Captions de Jitsi Meet para transcribir sin interferencias.";
                    if (window.showToast) window.showToast(advice, "warning");
                    stopTranscriptionFlow();
                } else if (e.error !== 'no-speech' && e.error !== 'aborted') {
                    if (window.showToast) window.showToast("Error de voz local: " + e.error, "error");
                }
            };
            
        } catch (err) {
            console.error("Error en motor local de voz:", err);
            isTranscribingLocal = false;
        }
    }

    async function startSessionAudioRecording() {
        sessionAudioChunks = [];
        let mixStream = null;
        let micStream = null;
        let displayStream = null;
        
        const recordFullSession = confirm(
            "¿Desea grabar la videollamada completa (Micrófono + Voz de otros participantes)?\n\n" +
            "Para esto se le solicitará compartir la pestaña de la reunión. " +
            "Asegúrese de marcar la casilla 'Compartir audio de la pestaña' (Share tab audio) en el diálogo.\n\n" +
            "Si selecciona Cancelar, se grabará únicamente su micrófono local."
        );
        
        try {
            // Siempre necesitamos el micrófono
            micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (micErr) {
            console.error("Error obteniendo micrófono:", micErr);
            if (window.showToast) window.showToast("No se pudo acceder al micrófono para la grabación.", "error");
            return;
        }
        
        if (recordFullSession) {
            try {
                // Solicitar la pestaña con audio
                displayStream = await navigator.mediaDevices.getDisplayMedia({
                    video: true,
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true
                    }
                });
                
                // Detener la pista de video de inmediato para no consumir CPU ni ancho de banda
                displayStream.getVideoTracks().forEach(track => track.stop());
                
                const displayAudioTracks = displayStream.getAudioTracks();
                if (displayAudioTracks.length > 0) {
                    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    const destination = audioContext.createMediaStreamDestination();
                    
                    const micSource = audioContext.createMediaStreamSource(micStream);
                    micSource.connect(destination);
                    
                    const displayAudioStream = new MediaStream(displayAudioTracks);
                    const displaySource = audioContext.createMediaStreamSource(displayAudioStream);
                    displaySource.connect(destination);
                    
                    mixStream = destination.stream;
                    // Guardamos la referencia de los streams originales para apagarlos luego
                    sessionAudioStream = {
                        stream: mixStream,
                        tracksToStop: [...micStream.getTracks(), ...displayStream.getTracks(), ...mixStream.getTracks()]
                    };
                    if (window.showToast) window.showToast("Grabación de reunión completa iniciada con éxito.", "success");
                } else {
                    displayStream.getTracks().forEach(track => track.stop());
                    mixStream = micStream;
                    sessionAudioStream = {
                        stream: mixStream,
                        tracksToStop: micStream.getTracks()
                    };
                    if (window.showToast) window.showToast("No se detectó audio de pestaña. Grabando sólo micrófono.", "warning");
                }
            } catch (err) {
                console.warn("Cancelado o no soportado getDisplayMedia. Fallback a micrófono solo.", err);
                mixStream = micStream;
                sessionAudioStream = {
                    stream: mixStream,
                    tracksToStop: micStream.getTracks()
                };
                if (window.showToast) window.showToast("Grabación iniciada: Sólo micrófono local.", "info");
            }
        } else {
            mixStream = micStream;
            sessionAudioStream = {
                stream: mixStream,
                tracksToStop: micStream.getTracks()
            };
            if (window.showToast) window.showToast("Grabación iniciada: Sólo micrófono local.", "info");
        }
        
        try {
            // Intentar inicializar MediaRecorder
            let options = { mimeType: 'audio/webm;codecs=opus' };
            if (!MediaRecorder.isTypeSupported(options.mimeType)) {
                options = { mimeType: 'audio/webm' };
                if (!MediaRecorder.isTypeSupported(options.mimeType)) {
                    options = { mimeType: 'audio/ogg' };
                    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
                        options = {}; // Usar el formato del navegador por defecto
                    }
                }
            }
            
            sessionMediaRecorder = new MediaRecorder(sessionAudioStream.stream, options);
            sessionMediaRecorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) {
                    sessionAudioChunks.push(e.data);
                }
            };
            
            sessionMediaRecorder.onstop = () => {
                console.log("Grabación de audio de la sesión detenida.");
            };
            
            sessionMediaRecorder.start(1000); // Guardar en chunks cada 1 segundo
            isRecordingSessionAudio = true;
            
            // Actualizar UI
            micIndicator.className = "w-2 h-2 rounded-full bg-red-500 animate-pulse";
            micText.innerText = "Detener Grabación";
            if (liveTranscriptionStatus) {
                liveTranscriptionStatus.classList.remove("hidden");
                liveTranscriptionStatus.innerText = "Grabando audio de sesión...";
            }
        } catch (recErr) {
            console.error("Error al iniciar MediaRecorder:", recErr);
            if (window.showToast) window.showToast("Error al inicializar el grabador de audio.", "error");
            stopSessionAudioRecording();
        }
    }
    
    function stopSessionAudioRecording() {
        isRecordingSessionAudio = false;
        if (sessionMediaRecorder && sessionMediaRecorder.state !== "inactive") {
            try {
                sessionMediaRecorder.stop();
            } catch (e) {}
        }
        
        if (sessionAudioStream && sessionAudioStream.tracksToStop) {
            sessionAudioStream.tracksToStop.forEach(track => {
                try { track.stop(); } catch(e) {}
            });
        }
        sessionAudioStream = null;
        
        // Actualizar UI
        micIndicator.className = "w-2 h-2 rounded-full bg-gray-500";
        micText.innerText = "Iniciar Grabación";
        if (liveTranscriptionStatus) {
            liveTranscriptionStatus.classList.add("hidden");
        }
    }

    btnToggleMic.addEventListener("click", () => {
        if (isRecordingSessionAudio) {
            stopSessionAudioRecording();
        } else {
            startSessionAudioRecording();
        }
    });

    // 7. Redactar Acta IA (Llamada al Endpoint + Fallback Manual)
    const btnGenerateActa = document.getElementById("btn-generate-acta");
    const actaManualModal = document.getElementById("acta-manual-modal");
    const btnCloseActaModal = document.getElementById("btn-close-acta-modal");
    const btnCancelActaModal = document.getElementById("btn-cancel-acta-modal");
    const btnSubmitActaManual = document.getElementById("btn-submit-acta-manual");
    const actaManualText = document.getElementById("acta-manual-text");

    function openActaManualModal() {
        if (actaManualModal) {
            actaManualModal.classList.remove("hidden");
            actaManualModal.classList.add("flex");
            if (actaManualText) actaManualText.focus();
        }
    }

    function closeActaManualModal() {
        if (actaManualModal) {
            actaManualModal.classList.add("hidden");
            actaManualModal.classList.remove("flex");
        }
    }

    if (btnCloseActaModal) btnCloseActaModal.addEventListener("click", closeActaManualModal);
    if (btnCancelActaModal) btnCancelActaModal.addEventListener("click", closeActaManualModal);

    async function executeGenerateActa(transcriptionData) {
        // 1. Si está grabando audio de la sesión, detenerlo para consolidar
        if (isRecordingSessionAudio) {
            stopSessionAudioRecording();
        }

        btnGenerateActa.disabled = true;
        if (btnSubmitActaManual) btnSubmitActaManual.disabled = true;

        let response;
        let isAudioUpload = false;

        try {
            // Verificar si hay audio grabado
            if (sessionAudioChunks && sessionAudioChunks.length > 0) {
                isAudioUpload = true;
                const audioBlob = new Blob(sessionAudioChunks, { type: 'audio/webm' });
                sessionAudioChunks = []; // Limpiar chunks una vez consumidos
                
                if (window.showLoader) window.showLoader("Subiendo audio al motor legal IA...");
                
                // Temporizador Premium de progreso de 4 estados
                let progressState = 1;
                const progressInterval = setInterval(() => {
                    if (!window.showLoader) return;
                    progressState++;
                    if (progressState === 2) {
                        window.showLoader("Transcribiendo y diarizando diálogos con Gemini Pro...");
                    } else if (progressState === 3) {
                        window.showLoader("Estructurando Acta de Conciliación con IA...");
                    } else if (progressState >= 4) {
                        window.showLoader("Generando archivo y guardando constancia local...");
                        clearInterval(progressInterval);
                    }
                }, 5000);

                const formData = new FormData();
                formData.append("audio_file", audioBlob, "meeting_audio.webm");

                try {
                    response = await fetch(`/api/meetings/process-audio/${roomName}`, {
                        method: "POST",
                        body: formData
                    });
                } finally {
                    clearInterval(progressInterval);
                }
            } else if (transcriptionData && transcriptionData.trim() !== "") {
                // Fallback manual (texto JSON al endpoint antiguo)
                if (window.showLoader) window.showLoader("Redactando acta con resumen manual...");
                response = await fetch(`/api/meetings/generate-minutes/${roomName}`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        transcription: transcriptionData
                    })
                });
            } else {
                // No hay audio ni texto
                throw new Error("No hay transcripción disponible");
            }

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.detail || "Error procesando el acta con la IA.");
            }

            if (data.success) {
                const toastMsg = isAudioUpload 
                    ? "Acta de Conciliación autogenerada y registrada de forma exitosa."
                    : "Acta generada y sellada en IPFS de forma exitosa.";
                
                if (window.showToast) window.showToast(toastMsg, "success");
                closeActaManualModal();
                
                // Recargar el visor del documento con el acta de Markdown
                const option = document.createElement("option");
                option.value = data.filename;
                option.text = data.filename;
                pdfSelector.add(option, 0);
                pdfSelector.value = data.filename;
                
                // Actualizar iframe
                pdfViewer.src = `/output/${data.filename}`;
                if (pdfNameDisplay) pdfNameDisplay.innerText = data.filename;
                
                // Forzar visor visible
                togglePdfMaximize(true);
            }
        } catch (err) {
            console.error(err);
            
            // Interceptamos si no hay audio o la transcripción está vacía
            const isTranscriptionEmptyError = err.message.includes("No hay transcripción disponible") || 
                                              err.message.includes("Redis vacío") || 
                                              err.message.includes("transcripción disponible") || 
                                              err.message.includes("vacía");
            
            if (isTranscriptionEmptyError && !transcriptionData) {
                if (window.showToast) window.showToast("No se detectó audio grabado. Ingrese un resumen de los acuerdos manualmente.", "warning");
                openActaManualModal();
            } else {
                if (window.showToast) window.showToast("Error: " + err.message, "error");
                else alert("Error generando acta: " + err.message);
            }
        } finally {
            if (window.hideLoader) window.hideLoader();
            btnGenerateActa.disabled = false;
            if (btnSubmitActaManual) btnSubmitActaManual.disabled = false;
        }
    }

    btnGenerateActa.addEventListener("click", async () => {
        if (!confirm("¿Desea cerrar el debate legal y estructurar el Acta de Conciliación con la IA basada en la transcripción en caliente?")) {
            return;
        }
        await executeGenerateActa("");
    });

    if (btnSubmitActaManual) {
        btnSubmitActaManual.addEventListener("click", async () => {
            const summary = actaManualText.value.trim();
            if (!summary) {
                if (window.showToast) window.showToast("Por favor escriba un breve resumen de los acuerdos para la IA.", "error");
                return;
            }
            await executeGenerateActa(summary);
        });
    }

    // 8. Modal de Firma Caligráfica (HTML5 Canvas + Touch)
    const btnSignPdf = document.getElementById("btn-sign-pdf");
    const sigModal = document.getElementById("signature-modal");
    const btnCloseSigModal = document.getElementById("btn-close-sig-modal");
    const btnCancelSig = document.getElementById("btn-cancel-meet-sig");
    const btnConfirmSig = document.getElementById("btn-confirm-meet-sig");
    const btnClearSig = document.getElementById("btn-clear-meet-sig");

    const sigCanvas = document.getElementById("meet-sig-canvas");
    const sigCtx = sigCanvas.getContext("2d");

    // Elementos Biométricos de Consentimiento en la Videollamada
    const consentCheck = document.getElementById("consent-check");
    const biometricsCheck = document.getElementById("biometrics-check");
    const videoRecordPanel = document.getElementById("video-record-panel");
    const webcamPreview = document.getElementById("webcam-preview");
    const recordingOverlay = document.getElementById("recording-overlay");
    const startRecordBtn = document.getElementById("start-record-btn");
    const recordingTimer = document.getElementById("recording-timer");
    const declarationToRead = document.getElementById("declaration-to-read");
    const canvasOverlay = document.getElementById("canvas-overlay");
    const overlayText = document.getElementById("overlay-text");
    const meetResultMsg = document.getElementById("meet-result-message");
    
    let isDrawing = false;
    let lastX = 0;
    let lastY = 0;
    let sigColor = "#6366f1"; // Indigo por defecto
    let hasDrawn = false;

    let mediaStream = null;
    let mediaRecorder = null;
    let recordedChunks = [];
    let videoBlob = null;
    let isVideoRecorded = false;
    let declarationTextVal = "";

    // Cargar la declaración legal inyectada
    async function fetchDeclarationText() {
        try {
            const name = window.SIGNER_NAME || "Invitado";
            const doc = window.DOCUMENT_FILENAME || "Contrato";
            const response = await fetch(`/api/meetings/declaration-text?signer_name=${encodeURIComponent(name)}&document_name=${encodeURIComponent(doc)}`);
            const data = await response.json();
            declarationTextVal = data.text;
            if (declarationToRead) {
                declarationToRead.innerText = `"${declarationTextVal}"`;
            }
        } catch (error) {
            console.error("Error cargando declaración legal:", error);
            declarationTextVal = `Yo, ${window.SIGNER_NAME || "Firmante"}, acepto de forma voluntaria firmar este contrato y apruebo este registro de video.`;
            if (declarationToRead) {
                declarationToRead.innerText = `"${declarationTextVal}"`;
            }
        }
    }

    // Encender la cámara web
    async function startWebcam() {
        try {
            if (mediaStream) {
                stopWebcam();
            }
            mediaStream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 480, facingMode: "user" },
                audio: true
            });
            if (webcamPreview) {
                webcamPreview.srcObject = mediaStream;
            }
            if (startRecordBtn) {
                startRecordBtn.disabled = false;
                startRecordBtn.innerHTML = `
                    <span class="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
                    Iniciar Grabación de Consentimiento
                `;
            }
        } catch (error) {
            console.error("Error accediendo a la webcam:", error);
            if (window.showToast) window.showToast("Se requiere acceso a la cámara y micrófono para la video-firma.", "error");
            else alert("Error: Se requiere acceso a la cámara y micrófono para la video-firma.");
        }
    }

    // Apagar la cámara web
    function stopWebcam() {
        if (mediaStream) {
            mediaStream.getTracks().forEach(track => track.stop());
            mediaStream = null;
        }
        if (webcamPreview) {
            webcamPreview.srcObject = null;
        }
    }

    // Detección dinámica de tipos MIME soportados para compatibilidad móvil (iOS / Android)
    function getSupportedMimeType() {
        const types = [
            "video/webm;codecs=vp9,opus",
            "video/webm;codecs=vp8,opus",
            "video/webm",
            "video/mp4;codecs=avc1",
            "video/mp4",
            "video/quicktime"
        ];
        for (const type of types) {
            if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type)) {
                return type;
            }
        }
        return "";
    }

    // Flujo de grabación de video (12 segundos)
    function startRecordingFlow() {
        if (!mediaStream) return;
        
        recordedChunks = [];
        const mimeType = getSupportedMimeType();
        const options = mimeType ? { mimeType } : {};
        
        try {
            mediaRecorder = new MediaRecorder(mediaStream, options);
        } catch (e) {
            console.warn("Fallo al instanciar MediaRecorder con opciones, usando fallback por defecto:", e);
            mediaRecorder = new MediaRecorder(mediaStream);
        }

        mediaRecorder.ondataavailable = (event) => {
            if (event.data && event.data.size > 0) {
                recordedChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = () => {
            videoBlob = new Blob(recordedChunks, { type: mediaRecorder.mimeType || "video/webm" });
            isVideoRecorded = true;
            stopWebcam();
            
            if (startRecordBtn) {
                startRecordBtn.className = "w-full py-1.5 bg-green-600 text-white text-[10px] font-bold rounded-lg flex items-center justify-center gap-1.5";
                startRecordBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                    </svg>
                    Video Grabado Exitosamente ✓
                `;
                startRecordBtn.disabled = true;
            }
            
            // Habilitar Canvas ocultando el overlay
            if (canvasOverlay) {
                canvasOverlay.classList.add("hidden");
                canvasOverlay.classList.remove("flex", "flex-col");
            }
            sigCanvas.style.pointerEvents = "auto";
            if (hasDrawn) {
                enableSubmitButton();
            }
        };

        // Iniciar grabación
        mediaRecorder.start();
        if (recordingOverlay) recordingOverlay.classList.remove("hidden");
        if (startRecordBtn) startRecordBtn.disabled = true;
        
        let timeLeft = 12;
        if (recordingTimer) {
            recordingTimer.classList.remove("hidden");
            recordingTimer.innerText = `${timeLeft}s`;
        }
        
        const timerInterval = setInterval(() => {
            timeLeft--;
            if (recordingTimer) recordingTimer.innerText = `${timeLeft}s`;
            if (timeLeft <= 0) {
                clearInterval(timerInterval);
                if (mediaRecorder && mediaRecorder.state !== "inactive") {
                    mediaRecorder.stop();
                }
                if (recordingOverlay) recordingOverlay.classList.add("hidden");
                if (recordingTimer) recordingTimer.classList.add("hidden");
            }
        }, 1000);
    }

    if (startRecordBtn) {
        startRecordBtn.addEventListener("click", startRecordingFlow);
    }

    // Controlar activación del lienzo según el consentimiento
    function updateConsentState() {
        const consented = consentCheck && biometricsCheck && consentCheck.checked && biometricsCheck.checked;
        if (consented) {
            if (videoRecordPanel) videoRecordPanel.classList.remove("hidden");
            fetchDeclarationText();
            startWebcam();
            
            if (isVideoRecorded) {
                if (canvasOverlay) {
                    canvasOverlay.classList.add("hidden");
                    canvasOverlay.classList.remove("flex", "flex-col");
                }
                sigCanvas.style.pointerEvents = "auto";
                if (hasDrawn) {
                    enableSubmitButton();
                }
            } else {
                if (canvasOverlay) {
                    canvasOverlay.classList.remove("hidden");
                    canvasOverlay.classList.add("flex", "flex-col");
                }
                sigCanvas.style.pointerEvents = "none";
                if (overlayText) overlayText.innerText = "Debe grabar su video de declaración legal en viva voz para desbloquear la firma.";
                disableSubmitButton();
            }
        } else {
            if (videoRecordPanel) videoRecordPanel.classList.add("hidden");
            stopWebcam();
            if (canvasOverlay) {
                canvasOverlay.classList.remove("hidden");
                canvasOverlay.classList.add("flex", "flex-col");
            }
            sigCanvas.style.pointerEvents = "none";
            if (overlayText) overlayText.innerText = "Marque las casillas de consentimiento legal de arriba para habilitar el lienzo de firma.";
            disableSubmitButton();
        }
    }

    if (consentCheck && biometricsCheck) {
        consentCheck.addEventListener("change", updateConsentState);
        biometricsCheck.addEventListener("change", updateConsentState);
    }

    function enableSubmitButton() {
        btnConfirmSig.disabled = false;
        btnConfirmSig.className = "px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-xl shadow-lg shadow-indigo-600/20 transition-all cursor-pointer";
    }

    function disableSubmitButton() {
        btnConfirmSig.disabled = true;
        btnConfirmSig.className = "px-4 py-2 bg-indigo-600/40 text-gray-400 border border-white/5 text-xs font-bold rounded-xl transition-all cursor-not-allowed";
    }

    // Redimensionar Canvas del modal de forma adaptativa y defensiva
    function resizeSigCanvas() {
        const parent = sigCanvas.parentElement;
        let width = sigCanvas.offsetWidth || (parent ? parent.clientWidth : 0);
        let height = sigCanvas.offsetHeight || (parent ? parent.clientHeight : 0);
        
        // Si las dimensiones son 0 (por ejemplo, al estar el modal inicialmente oculto), aplicamos fallbacks coherentes
        if (!width || width === 0) {
            width = (parent && parent.offsetWidth && parent.offsetWidth > 0) ? parent.offsetWidth : 460;
        }
        if (!height || height === 0) {
            height = window.innerWidth < 640 ? 128 : 160; // h-32 (128px) en móviles, h-40 (160px) en PC
        }
        
        sigCanvas.width = width;
        sigCanvas.height = height;
        
        // Estilo del pincel
        sigCtx.strokeStyle = sigColor;
        sigCtx.lineWidth = 3.5;
        sigCtx.lineCap = "round";
        sigCtx.lineJoin = "round";
    }

    // Dibujo
    function getMouseCoords(e) {
        const rect = sigCanvas.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;
        return {
            x: clientX - rect.left,
            y: clientY - rect.top
        };
    }

    function startDraw(e) {
        if (consentCheck && (!consentCheck.checked || !biometricsCheck.checked || !isVideoRecorded)) return;
        isDrawing = true;
        const coords = getMouseCoords(e);
        lastX = coords.x;
        lastY = coords.y;
    }

    function draw(e) {
        if (!isDrawing) return;
        e.preventDefault();
        
        const coords = getMouseCoords(e);
        
        // Forzar estilos del pincel antes de trazar para evitar reseteos por redimensionamiento en Tailwind
        sigCtx.lineWidth = 3.5;
        sigCtx.lineCap = "round";
        sigCtx.lineJoin = "round";
        sigCtx.strokeStyle = sigColor;

        sigCtx.beginPath();
        sigCtx.moveTo(lastX, lastY);
        sigCtx.lineTo(coords.x, coords.y);
        sigCtx.stroke();
        
        lastX = coords.x;
        lastY = coords.y;
        hasDrawn = true;
        
        if (isVideoRecorded) {
            enableSubmitButton();
        }
    }

    function stopDraw() {
        isDrawing = false;
    }

    // Asignar eventos de dibujo al Canvas
    sigCanvas.addEventListener("mousedown", startDraw);
    sigCanvas.addEventListener("mousemove", draw);
    sigCanvas.addEventListener("mouseup", stopDraw);
    sigCanvas.addEventListener("mouseout", stopDraw);

    sigCanvas.addEventListener("touchstart", (e) => {
        startDraw(e);
        if (e.touches.length === 1) e.preventDefault();
    }, { passive: false });
    sigCanvas.addEventListener("touchmove", draw, { passive: false });
    sigCanvas.addEventListener("touchend", stopDraw);

    // Botones del Modal
    btnSignPdf.addEventListener("click", () => {
        if (!window.SIGNER_TOKEN) {
            alert("No se ha detectado ningún flujo o token de firma activo para tu usuario en este documento. Es posible que el contrato ya haya sido firmado completamente.");
            return;
        }

        sigModal.classList.remove("hidden");
        sigModal.classList.add("flex");
        hasDrawn = false;
        
        // Resetear consentimiento y webcam
        if (consentCheck) consentCheck.checked = false;
        if (biometricsCheck) biometricsCheck.checked = false;
        isVideoRecorded = false;
        videoBlob = null;
        if (startRecordBtn) {
            startRecordBtn.className = "w-full py-1.5 bg-gradient-to-r from-red-600 to-pink-600 hover:from-red-500 hover:to-pink-500 text-white text-[10px] font-bold rounded-lg shadow-md transition-all flex items-center justify-center gap-1.5 cursor-pointer";
            startRecordBtn.innerHTML = `Iniciar Grabación (12s)`;
            startRecordBtn.disabled = false;
        }
        if (meetResultMsg) meetResultMsg.innerText = "";
        updateConsentState();
        
        // Retrasar resize para que tome el ancho completo del elemento flex visible
        setTimeout(resizeSigCanvas, 100);
    });

    function closeSigModalFlow() {
        sigModal.classList.remove("flex");
        sigModal.classList.add("hidden");
        sigCtx.clearRect(0, 0, sigCanvas.width, sigCanvas.height);
        hasDrawn = false;
        stopWebcam();
    }

    btnCloseSigModal.addEventListener("click", closeSigModalFlow);
    btnCancelSig.addEventListener("click", closeSigModalFlow);
    
    btnClearSig.addEventListener("click", () => {
        sigCtx.clearRect(0, 0, sigCanvas.width, sigCanvas.height);
        hasDrawn = false;
        if (isVideoRecorded) {
            enableSubmitButton();
        }
    });

    // Alternar colores de tinta
    const inkButtons = document.querySelectorAll(".meet-ink-btn");
    inkButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            inkButtons.forEach(b => b.classList.remove("ring-2", "ring-indigo-400"));
            btn.classList.add("ring-2", "ring-indigo-400");
            sigColor = btn.dataset.color;
            sigCtx.strokeStyle = sigColor;
        });
    });

    // Confirmar e Inyectar Firma en PDF
    btnConfirmSig.addEventListener("click", async () => {
        if (!hasDrawn) {
            alert("Por favor dibuje su firma caligráfica antes de confirmar.");
            return;
        }
        if (!consentCheck.checked || !biometricsCheck.checked) {
            alert("Debe aceptar los términos de consentimiento legal.");
            return;
        }
        if (!isVideoRecorded || !videoBlob) {
            alert("Debe grabar su video de consentimiento en voz alta primero.");
            return;
        }

        const activeFile = pdfSelector.value;
        if (!activeFile || !activeFile.endsWith(".pdf")) {
            alert("No hay ningún PDF cargado activo para poder estampar la firma.");
            return;
        }

        const sigBase64 = sigCanvas.toDataURL("image/png");
        
        // Bloquear UI
        btnConfirmSig.disabled = true;
        btnConfirmSig.innerText = "Subiendo...";
        if (window.showLoader) window.showLoader("Subiendo grabación de consentimiento y estampando firma...");
        if (meetResultMsg) {
            meetResultMsg.className = "text-[11px] text-center font-medium mt-1 text-indigo-400 animate-pulse";
            meetResultMsg.innerText = "Subiendo video evidencia a IPFS...";
        }

        try {
            const token = window.SIGNER_TOKEN;
            
            // 1. Convertir videoBlob a Base64 asíncronamente con Promesa
            const getBase64 = (blob) => new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.readAsDataURL(blob);
                reader.onload = () => resolve(reader.result);
                reader.onerror = error => reject(error);
            });
            
            const videoBase64 = await getBase64(videoBlob);
            
            // Subir el video de evidencia al endpoint mediante JSON
            const videoResponse = await fetch(`/api/meetings/upload-evidence/${token}`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    video_base64: videoBase64,
                    declaration_read: declarationTextVal
                })
            });

            let videoResult;
            const responseText = await videoResponse.text();
            try {
                videoResult = JSON.parse(responseText);
            } catch (e) {
                throw new Error(`Error en el servidor (${videoResponse.status}): ${responseText || "Respuesta vacía"}`);
            }

            if (!videoResponse.ok) {
                throw new Error(videoResult?.detail || "Error al subir video evidencia legal.");
            }

            // 2. Proceder a estampar la firma en el PDF
            if (meetResultMsg) {
                meetResultMsg.innerText = "Inyectando firma y consolidando PDF...";
            }
            const authToken = localStorage.getItem("access_token");
            const headers = {
                "Content-Type": "application/json"
            };
            if (authToken) {
                headers["Authorization"] = `Bearer ${authToken}`;
            }

            const response = await fetch("/api/meetings/stamp-live-signature", {
                method: "POST",
                headers: headers,
                body: JSON.stringify({
                    document_filename: activeFile,
                    signature_base64: sigBase64,
                    signer_name: signerName,
                    signer_email: window.SIGNER_EMAIL || null,
                    room_name: window.ROOM_NAME || null
                })
            });

            if (!response.ok) {
                let errMsg = "Error estampando firma en el documento.";
                try {
                    const errData = await response.json();
                    errMsg = errData.detail || errMsg;
                } catch(e) {
                    const text = await response.text();
                    errMsg = text || response.statusText || errMsg;
                }
                throw new Error(errMsg);
            }

            const data = await response.json();

            if (data.success) {
                if (window.showToast) window.showToast("Firma inyectada y video evidencia anclado en IPFS con éxito.", "success");
                
                // Recargar iframe del PDF
                pdfViewer.src = `/output/${activeFile}?t=${new Date().getTime()}`;
                closeSigModalFlow();
            }
        } catch (err) {
            console.error(err);
            if (meetResultMsg) {
                meetResultMsg.className = "text-[11px] text-center font-bold mt-1 text-red-500";
                meetResultMsg.innerText = "Error: " + err.message;
            }
            if (window.showToast) window.showToast("Error: " + err.message, "error");
            else alert("Error estampando firma: " + err.message);
            btnConfirmSig.disabled = false;
            btnConfirmSig.innerText = "Confirmar y Estampar Firma";
        } finally {
            if (window.hideLoader) window.hideLoader();
        }
    });
});
