/**
 * Control lógico para el widget del chat flotante IA.
 */

// Elementos
const chatWindow = document.getElementById('ai-chat-window');
const chatToggleBtn = document.getElementById('chat-toggle-btn');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const chatForm = document.getElementById('chat-form');

// Historial del chat local
let chatHistory = [];

/**
 * Muestra u oculta la ventana del chat.
 */
function toggleChat() {
    if (chatWindow.classList.contains('hidden')) {
        // Abrir
        chatWindow.classList.remove('hidden');
        // Pequeño timeout para permitir que el display:block se aplique antes de animar opacidad y escala
        setTimeout(() => {
            chatWindow.classList.remove('scale-95', 'opacity-0');
            chatWindow.classList.add('scale-100', 'opacity-100');
            chatInput.focus();
            scrollToBottom();
        }, 10);
        
        // Cambiar el icono del boton flotante
        const icons = chatToggleBtn.querySelectorAll('i');
        icons[0].classList.add('hidden'); // Ocultar globo
        icons[1].classList.remove('hidden'); // Mostrar X
        chatToggleBtn.classList.add('bg-black/60', 'from-black', 'to-gray-800');
        chatToggleBtn.classList.remove('bg-gradient-to-r', 'from-cyan-500', 'to-blue-600');
    } else {
        // Cerrar
        chatWindow.classList.remove('scale-100', 'opacity-100');
        chatWindow.classList.add('scale-95', 'opacity-0');
        
        setTimeout(() => {
            chatWindow.classList.add('hidden');
        }, 300); // Tiempo que dura la transición CSS

        // Restaurar icono del boton flotante
        const icons = chatToggleBtn.querySelectorAll('i');
        icons[0].classList.remove('hidden'); 
        icons[1].classList.add('hidden');
        chatToggleBtn.classList.remove('bg-black/60', 'from-black', 'to-gray-800');
        chatToggleBtn.classList.add('bg-gradient-to-r', 'from-cyan-500', 'to-blue-600');
    }
}

/**
 * Scroll automático hasta abajo.
 */
function scrollToBottom() {
    if(chatMessages) {
        chatMessages.scrollTo({
            top: chatMessages.scrollHeight,
            behavior: 'smooth'
        });
    }
}

/**
 * Funciones de TTS
 */
let currentAudio = null;
let isPlaying = false;

async function playTTS(text, btnElement) {
    if (isPlaying && currentAudio) {
        currentAudio.pause();
        isPlaying = false;
        resetTTSButtons();
        return;
    }

    try {
        if (!text || text.trim() === "") {
            console.warn("TTS: No hay texto para reproducir");
            return;
        }

        // Mostrar estado de carga
        const icon = btnElement.querySelector('i');
        icon.className = 'bi bi-hourglass-split animate-spin';

        // Asegurar que el audio anterior quede detenido
        if (currentAudio) {
             currentAudio.pause();
        }

        // Usamos POST o GET a `/api/tts/speak`.
        // Dependiendo de tu implementación previa en 'Fixing EdgeTTS',
        // GET directo o POST para obtener la URL. Asumo que `/api/tts/speak?text=xxx&voice=es-MX-JorgeNeural` retorna audio.
        // Si tu config era por POST y retorna un json con un ID, el flujo puede variar. Asumiré que espera un GET, como un source mp3 o wav para navegador.
        // Adaptación: enviaremos a la misma url ya funcional de TextToSpeech.
        
        const voice = "es-MX-JorgeNeural"; 
        // Lógica típica para LUKA-GUI/Star-Doc:
        const response = await fetch(`/api/tts/speak`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text: text, voice: voice, rate: "+20%"})
        });

        if (!response.ok) throw new Error("Fallo en regeneración de TTS");
        
        // Asumiendo que devuelve un blob directo del audio (wav/mp3)
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        
        currentAudio = new Audio(url);
        currentAudio.onplay = () => {
             isPlaying = true;
             resetTTSButtons();
             icon.className = 'bi bi-stop-circle-fill text-cyan-400'; // Indicador de que está sonando este
        };
        currentAudio.onended = () => {
             isPlaying = false;
             icon.className = 'bi bi-volume-up-fill';
             URL.revokeObjectURL(url);
        };
        currentAudio.onerror = () => {
             isPlaying = false;
             icon.className = 'bi bi-volume-up-fill';
             console.error("Error reproduciendo TTS");
        };

        currentAudio.play();

    } catch (e) {
        console.error("Error al obtener TTS:", e);
        const icon = btnElement.querySelector('i');
        icon.className = 'bi bi-exclamation-triangle-fill text-red-500';
    }
}

function resetTTSButtons() {
    document.querySelectorAll('.tts-play-btn i').forEach(el => {
        if (!el.classList.contains('bi-exclamation-triangle-fill')) {
             el.className = 'bi bi-volume-up-fill';
        }
    });
}

/**
 * Inserta parámetros adicionales en la petición HTMX (Historial de chat)
 */
function handleConfigRequest(event) {
    if (!event.detail.parameters) {
        event.detail.parameters = {};
    }
    // Convertimos la historia local en JSON string y la agregamos al form data de htmx
    event.detail.parameters['history'] = JSON.stringify(chatHistory);
}

/**
 * Inyecta el mensaje del usuario en el DOM apenas envíe, antes de que el backend responda.
 */
function handleBeforeRequest(event) {
    const message = chatInput.value.trim();
    if (!message) {
        event.preventDefault(); // Evitar envío vacío
        return;
    }

    // Bloquear input mientras enviamos
    const submitBtn = document.getElementById('chat-submit-btn');
    chatInput.disabled = true;
    submitBtn.disabled = true;

    // Inyectar visualmente
    const userMessageHTML = `
    <div class="chat chat-end animate-fade-in-up">
        <div class="chat-header text-[10px] font-medium text-gray-500 mb-1 mr-1 uppercase tracking-wider">
            Tú
        </div>
        <div class="chat-bubble bg-gradient-to-b from-cyan-600/40 to-cyan-700/30 text-white backdrop-blur-md shadow-lg border border-cyan-500/30 text-sm px-4 py-2.5 rounded-2xl rounded-tr-none max-w-[85%]">
            ${message.replace(/\n/g, '<br>')}
        </div>
    </div>
    `;

    chatMessages.insertAdjacentHTML('beforeend', userMessageHTML);
    
    // Guardar en history local
    chatHistory.push({ role: "user", parts: [{ text: message }] });

    // Limpiar input y ajustar altura resizable si aplica
    chatInput.value = '';
    scrollToBottom();
}

/**
 * Restaurar input y parsear la historia tras recibir de HTMX
 */
function handleAfterRequest(event) {
    const submitBtn = document.getElementById('chat-submit-btn');
    chatInput.disabled = false;
    submitBtn.disabled = false;
    chatInput.focus();

    if (event.detail.successful) {
        // Procesar sugerencias inteligentes (chips)
        processLatestSuggestions();
        
        // Hacemos scroll
        setTimeout(scrollToBottom, 50);
    } else {
        // Error de red o 500
        chatMessages.insertAdjacentHTML('beforeend', `
            <div class="text-center text-red-400 text-xs my-2">Hubo un problema de conexión.</div>
        `);
    }
}

/**
 * Procesa el bloque |||Suggestions: [...]||| del último mensaje
 */
function processLatestSuggestions() {
    const bubbles = chatMessages.querySelectorAll('.chat-bubble');
    if (bubbles.length === 0) return;
    
    const lastBubble = bubbles[bubbles.length - 1];
    const rawHTML = lastBubble.innerHTML;
    
    // Buscar el patrón de sugerencias
    const match = rawHTML.match(/\|\|\|Suggestions:\s*(\[.*?\])\s*\|\|\|/);
    if (match) {
        try {
            const suggestions = JSON.parse(match[1]);
            // Limpiar el texto de la burbuja (quitar los marcadores)
            lastBubble.innerHTML = rawHTML.replace(match[0], '').trim();
            
            // Renderizar los chips
            renderSuggestions(suggestions);
        } catch (err) {
            console.error("Error parseando sugerencias:", err);
        }
    }
}

/**
 * Renderiza los botones de sugerencia bajo el chat
 */
function renderSuggestions(suggestions) {
    // Eliminar sugerencias previas si existen
    const prev = document.getElementById('chat-suggestions-container');
    if (prev) prev.remove();

    if (!suggestions) suggestions = [];

    const container = document.createElement('div');
    container.id = 'chat-suggestions-container';
    container.className = 'mt-4 mb-2 flex flex-wrap gap-2 animate-fade-in-up px-1 relative group';
    
    // Botón de cerrar sugerencias (Mejorado: siempre visible o con mejor hover)
    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '<i class="bi bi-x-circle-fill"></i>';
    closeBtn.className = 'absolute -top-3 -right-1 text-gray-500 hover:text-red-400 text-sm transition-all opacity-0 group-hover:opacity-100 cursor-pointer z-10 bg-black/50 rounded-full';
    closeBtn.onclick = () => container.remove();
    container.appendChild(closeBtn);

    // 1. Chip Especial: WhatsApp Contact (Estilo unificado)
    const waChip = document.createElement('a');
    waChip.href = 'https://wa.me/573015754092';
    waChip.target = '_blank';
    // Estilo que mezcla el glassmorphism con un toque verde sutil
    waChip.className = 'bg-green-500/10 hover:bg-green-500/20 border border-green-500/30 hover:border-green-500/60 text-[11px] text-green-400 px-3 py-1.5 rounded-full transition-all cursor-pointer shadow-sm active:scale-95 flex items-center gap-1.5 no-underline';
    waChip.innerHTML = '<i class="bi bi-whatsapp text-xs"></i> <span>Contactar ahora</span>';
    container.appendChild(waChip);

    // 2. Sugerencias Dinámicas de la IA (Limitadas a las 2 primeras)
    suggestions.slice(0, 2).forEach(text => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'bg-white/5 hover:bg-white/10 border border-white/10 hover:border-cyan-500/40 text-[11px] text-gray-300 px-3 py-1.5 rounded-full transition-all cursor-pointer shadow-sm active:scale-95';
        chip.innerText = text;
        chip.onclick = () => {
            chatInput.value = text;
            htmx.trigger(chatForm, "submit");
            container.remove();
        };
        container.appendChild(chip);
    });

    chatMessages.appendChild(container);
    scrollToBottom();
}

// Permitir Enter para submit (con Shift para salto de linea)
chatInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        // HTMX maneja form submissions, así que despachamos un evento submit en el forms
        if (chatInput.value.trim() !== '') {
            htmx.trigger(chatForm, "submit");
        }
    }
});

/**
 * ==========================================
 * Reconocimiento de Voz (Dictado)
 * ==========================================
 */
let recognition = null;
let isRecording = false;

function toggleMic() {
    // Validación de seguridad ESTRICTA para dispositivos móviles
    // Chrome en Android y Safari en iOS bloquean silenciosamente el micrófono si no es HTTPS o localhost.
    const isSecureContext = window.isSecureContext || window.location.protocol === 'https:' || window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    
    if (!isSecureContext) {
        (window.showToast ? showToast("⚠️ Por seguridad, tu celular bloquea el micrófono porque la conexión no es segura (HTTP).\n\nPara probar en el celular usa HTTPS o un túnel como ngrok.", 'warning') : alert("⚠️ Por seguridad, tu celular bloquea el micrófono porque la conexión no es segura (HTTP).\n\nPara probar en el celular usa HTTPS o un túnel como ngrok."));
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        (window.showToast ? showToast("Lo sentimos, tu navegador móvil no soporta el reconocimiento de voz de Google/Apple.", 'warning') : alert("Lo sentimos, tu navegador móvil no soporta el reconocimiento de voz de Google/Apple."));
        return;
    }

    // Si ya está grabando, detenemos
    if (isRecording) {
        if (recognition) recognition.stop();
        return;
    }

    // Inicializar SIEMPRE bajo demanda
    try {
        if (!recognition) {
            recognition = new SpeechRecognition();
            recognition.lang = 'es-CO'; // Español Colombia
            recognition.interimResults = true; // Resultados en tiempo real
            recognition.maxAlternatives = 1;
            
            let baseText = '';

            recognition.onstart = () => {
                isRecording = true;
                baseText = chatInput.value; 
                updateMicUI();
            };
            
            recognition.onresult = (event) => {
                let interimTranscript = '';
                let finalTranscript = '';

                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript;
                    if (event.results[i].isFinal) {
                        finalTranscript += transcript;
                    } else {
                        interimTranscript += transcript;
                    }
                }
                
                // Actualizamos el textarea visualmente
                const separator = baseText && !baseText.endsWith(' ') ? ' ' : '';
                chatInput.value = baseText + separator + finalTranscript + interimTranscript;
                
                if (finalTranscript) {
                    baseText += separator + finalTranscript;
                }
            };
            
            recognition.onspeechend = () => {
                recognition.stop();
            };
            
            recognition.onend = () => {
                isRecording = false;
                updateMicUI();
                chatInput.focus();
            };
            
            recognition.onerror = (event) => {
                isRecording = false;
                updateMicUI();
                
                // Mostramos el error exacto en pantalla para el celular
                if (event.error === 'not-allowed') {
                    (window.showToast ? showToast("Permiso de micrófono denegado. Dale permiso al navegador.", 'warning') : alert("Permiso de micrófono denegado. Dale permiso al navegador."));
                } else if (event.error === 'network') {
                    (window.showToast ? showToast("Error de red: La API de voz de tu celular necesita internet o falló internamente.", 'warning') : alert("Error de red: La API de voz de tu celular necesita internet o falló internamente."));
                } else if (event.error !== 'no-speech') {
                    (window.showToast ? showToast("Error del micrófono: " + event.error, 'warning') : alert("Error del micrófono: " + event.error));
                }
            };
        }
        
        recognition.start();
    } catch (e) {
        (window.showToast ? showToast("Error al intentar abrir el micrófono: " + e.message, 'warning') : alert("Error al intentar abrir el micrófono: " + e.message));
        recognition = null; // Reiniciamos para que el siguiente clic lo construya de nuevo
        isRecording = false;
        updateMicUI();
    }
}

function updateMicUI() {
    const micIcon = document.getElementById('chat-mic-icon');
    const micBtn = document.getElementById('chat-mic-btn');
    if (!micIcon || !micBtn) return;
    
    if (isRecording) {
        // Estilo activo (grabando)
        micIcon.classList.replace('bi-mic-fill', 'bi-mic-mute-fill');
        micIcon.classList.add('text-red-500', 'animate-pulse');
        micIcon.classList.remove('text-cyan-400');
        micBtn.classList.add('border-red-500/50', 'bg-red-500/10');
        micBtn.classList.remove('bg-white/5', 'border-white/20');
        chatInput.placeholder = "Escuchando...";
    } else {
        // Estilo inactivo
        micIcon.classList.replace('bi-mic-mute-fill', 'bi-mic-fill');
        micIcon.classList.remove('text-red-500', 'animate-pulse');
        micBtn.classList.remove('border-red-500/50', 'bg-red-500/10');
        micBtn.classList.add('bg-white/5', 'border-white/20');
        chatInput.placeholder = "Escribe tu mensaje...";
    }
}

// Funciones del Modal de Agendamiento del Widget (JS Nativo)
function openWidgetScheduleModal() {
    const modal = document.getElementById('widget-schedule-modal');
    if (modal) {
        modal.classList.remove('hidden');
        const inner = modal.querySelector('div');
        setTimeout(() => {
            modal.classList.remove('opacity-0');
            modal.classList.add('opacity-100');
            if (inner) {
                inner.classList.remove('scale-95', 'opacity-0');
                inner.classList.add('scale-100', 'opacity-100');
            }
        }, 10);
    }
}

function closeWidgetScheduleModal() {
    const modal = document.getElementById('widget-schedule-modal');
    if (modal) {
        const inner = modal.querySelector('div');
        modal.classList.remove('opacity-100');
        modal.classList.add('opacity-0');
        if (inner) {
            inner.classList.remove('scale-100', 'opacity-100');
            inner.classList.add('scale-95', 'opacity-0');
        }
        setTimeout(() => {
            modal.classList.add('hidden');
        }, 300);
    }
}

async function submitWidgetSchedule(btnEl) {
    const name = document.getElementById('w-sched-name').value.trim();
    const email = document.getElementById('w-sched-email').value.trim();
    const phone = document.getElementById('w-sched-phone').value.trim();
    const apptType = document.getElementById('w-sched-type').value;
    const reason = document.getElementById('w-sched-reason').value.trim();
    const date = document.getElementById('w-sched-date').value;
    const time = document.getElementById('w-sched-time').value;

    if (!name || !email || !phone || !reason || !date || !time) {
        if (window.showToast) showToast('Por favor, rellene todos los campos para agendar la cita.', 'warning');
        else alert('Por favor, rellene todos los campos para agendar la cita.');
        return;
    }

    const spinner = document.getElementById('w-sched-spinner');
    const btnText = document.getElementById('w-sched-btn-text');

    // Deshabilitar botón y mostrar spinner
    btnEl.disabled = true;
    if (spinner) spinner.classList.remove('hidden');
    if (btnText) btnText.innerText = 'AGENDANDO...';

    try {
        const payload = {
            client_name: name,
            client_phone: phone,
            client_email: email,
            appointment_type: apptType,
            reason: reason,
            appointment_date: date,
            appointment_time: time
        };

        const response = await fetch('/api/appointments/schedule', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Error en el servidor al agendar la cita.');
        }

        const resData = await response.json();
        
        let successMsg = '¡Cita de asesoría agendada con éxito!';
        if (resData.meeting_link) {
            successMsg += ' Se generó tu sala de Google Meet. Revisa tu correo.';
        } else {
            successMsg += ' Revisa tu correo para más detalles.';
        }

        if (window.showToast) showToast(successMsg, 'success');
        else alert(successMsg);

        // Limpiar formulario y cerrar modal
        document.getElementById('w-sched-name').value = '';
        document.getElementById('w-sched-email').value = '';
        document.getElementById('w-sched-phone').value = '';
        document.getElementById('w-sched-reason').value = '';
        document.getElementById('w-sched-date').value = '';
        document.getElementById('w-sched-time').value = '';
        
        closeWidgetScheduleModal();

    } catch (err) {
        console.error(err);
        if (window.showToast) showToast('Error al agendar la cita: ' + err.message, 'error');
        else alert('Error al agendar la cita: ' + err.message);
    } finally {
        btnEl.disabled = false;
        if (spinner) spinner.classList.add('hidden');
        if (btnText) btnText.innerText = 'CONFIRMAR CITA';
    }
}

// Exponer funciones en el scope global para asegurar disponibilidad
window.openWidgetScheduleModal = openWidgetScheduleModal;
window.closeWidgetScheduleModal = closeWidgetScheduleModal;
window.submitWidgetSchedule = submitWidgetSchedule;
