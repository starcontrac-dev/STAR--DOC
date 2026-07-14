/**
 * =====================================================
 * STAR-DOC :: Firma Electrónica - Canvas Signature Pad
 * =====================================================
 */
document.addEventListener("DOMContentLoaded", () => {
    const canvas = document.getElementById("signature-canvas");
    const ctx = canvas.getContext("2d");
    
    const consentCheck = document.getElementById("consent-check");
    const biometricsCheck = document.getElementById("biometrics-check");
    const submitBtn = document.getElementById("submit-btn");
    const clearBtn = document.getElementById("clear-btn");
    const canvasOverlay = document.getElementById("canvas-overlay");
    const resultMsg = document.getElementById("result-message");
    
    let isDrawing = false;
    let lastX = 0;
    let lastY = 0;
    let hasStrokes = false; // Indica si el usuario realmente dibujó algo
    
    // Variables de estilo de pincel personalizadas
    let strokeColor = "#818cf8";
    let brushWidth = 4;

    // 1. Configurar tamaño responsivo del Canvas
    function resizeCanvas() {
        // Necesitamos guardar la firma actual si el canvas cambia de tamaño en vivo
        const tempCopy = canvas.toDataURL();
        
        const rect = canvas.parentElement.getBoundingClientRect();
        canvas.width = rect.width;
        canvas.height = rect.height;
        
        // Configurar pincel
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = brushWidth;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        
        // Restaurar contenido si existía
        if (hasStrokes) {
            const img = new Image();
            img.onload = function() {
                ctx.drawImage(img, 0, 0);
            };
            img.src = tempCopy;
        }
    }
    
    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();

    // 2. Elementos DOM de Video-Firma
    const videoRecordPanel = document.getElementById("video-record-panel");
    const webcamPreview = document.getElementById("webcam-preview");
    const recordingOverlay = document.getElementById("recording-overlay");
    const startRecordBtn = document.getElementById("start-record-btn");
    const recordingTimer = document.getElementById("recording-timer");
    const declarationToRead = document.getElementById("declaration-to-read");
    const overlayText = document.getElementById("overlay-text");

    let mediaStream = null;
    let mediaRecorder = null;
    let recordedChunks = [];
    let videoBlob = null;
    let isVideoRecorded = false;
    let declarationTextVal = "";

    // Cargar texto de declaración legal
    async function fetchDeclarationText() {
        try {
            const name = window.SIGNER_NAME || "Invitado";
            const doc = window.DOCUMENT_FILENAME || "Contrato";
            const response = await fetch(`/api/meetings/declaration-text?signer_name=${encodeURIComponent(name)}&document_name=${encodeURIComponent(doc)}`);
            const data = await response.json();
            declarationTextVal = data.text;
            declarationToRead.innerText = `"${declarationTextVal}"`;
        } catch (error) {
            console.error("Error cargando declaración legal:", error);
            declarationTextVal = `Yo, ${window.SIGNER_NAME || "Firmante"}, acepto voluntariamente los términos y condiciones. Firmo de forma electrónica y consciente de sus efectos legales.`;
            declarationToRead.innerText = `"${declarationTextVal}"`;
        }
    }

    // Inicializar cámara
    async function startWebcam() {
        try {
            if (mediaStream) {
                stopWebcam();
            }
            mediaStream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 480, facingMode: "user" },
                audio: true
            });
            webcamPreview.srcObject = mediaStream;
            startRecordBtn.disabled = false;
            startRecordBtn.innerHTML = `
                <span class="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse"></span>
                Iniciar Grabación de Consentimiento
            `;
        } catch (error) {
            console.error("Error accediendo a la webcam:", error);
            if (window.showToast) showToast("Se requiere acceso a la cámara y micrófono para la video-firma.", "error");
            else alert("Error: Se requiere acceso a la cámara y micrófono para cumplir con la firma biométrica de STAR-DOC.");
        }
    }

    // Apagar cámara
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

    // Grabación local de 12 segundos
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
            
            // Éxito visual
            startRecordBtn.className = "w-full py-2.5 bg-green-600 text-white text-xs font-bold rounded-xl flex items-center justify-center gap-2";
            startRecordBtn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                </svg>
                Consentimiento en Video Grabado Exitosamente ✓
            `;
            startRecordBtn.disabled = true;
            
            // Habilitar Canvas
            canvasOverlay.style.display = "none";
            canvas.style.pointerEvents = "auto";
            if (hasStrokes) {
                enableSubmitButton();
            }
        };

        // Iniciar
        mediaRecorder.start();
        recordingOverlay.classList.remove("hidden");
        startRecordBtn.disabled = true;
        
        // Timer de 12 segundos para lectura cómoda
        let timeLeft = 12;
        recordingTimer.classList.remove("hidden");
        recordingTimer.innerText = `${timeLeft}s`;
        
        const timerInterval = setInterval(() => {
            timeLeft--;
            recordingTimer.innerText = `${timeLeft}s`;
            if (timeLeft <= 0) {
                clearInterval(timerInterval);
                mediaRecorder.stop();
                recordingOverlay.classList.add("hidden");
                recordingTimer.classList.add("hidden");
            }
        }, 1000);
    }

    startRecordBtn.addEventListener("click", startRecordingFlow);

    // Controlar activación de Canvas y Botones mediante Checks
    function updateConsentState() {
        const consented = consentCheck.checked && biometricsCheck.checked;
        if (consented) {
            videoRecordPanel.classList.remove("hidden");
            fetchDeclarationText();
            startWebcam();
            
            if (isVideoRecorded) {
                canvasOverlay.style.display = "none";
                canvas.style.pointerEvents = "auto";
                if (hasStrokes) {
                    enableSubmitButton();
                }
            } else {
                canvasOverlay.style.display = "flex";
                canvas.style.pointerEvents = "none";
                overlayText.innerText = "Debe grabar su video de declaración legal en viva voz para desbloquear la firma.";
                disableSubmitButton();
            }
        } else {
            videoRecordPanel.classList.add("hidden");
            stopWebcam();
            canvasOverlay.style.display = "flex";
            canvas.style.pointerEvents = "none";
            overlayText.innerText = "Marque las casillas de consentimiento legal de arriba para habilitar el lienzo de firma.";
            disableSubmitButton();
        }
    }
    
    consentCheck.addEventListener("change", updateConsentState);
    biometricsCheck.addEventListener("change", updateConsentState);
    updateConsentState(); // Inicializar bloqueado

    function enableSubmitButton() {
        submitBtn.disabled = false;
        submitBtn.className = "w-full py-3 bg-indigo-600 hover:bg-indigo-500 hover:scale-[1.02] active:scale-95 text-white font-bold rounded-xl transition-all shadow-lg shadow-indigo-600/30 cursor-pointer flex items-center justify-center gap-2";
    }

    function disableSubmitButton() {
        submitBtn.disabled = true;
        submitBtn.className = "w-full py-3 bg-indigo-600/40 cursor-not-allowed border border-white/5 text-gray-400 font-bold rounded-xl transition-all flex items-center justify-center gap-2";
    }

    // 3. Funciones de Dibujo (Mouse y Touch)
    
    // Obtener coordenadas relativas exactas
    function getCoords(e) {
        const rect = canvas.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;
        return {
            x: clientX - rect.left,
            y: clientY - rect.top
        };
    }

    function startDrawing(e) {
        if (!consentCheck.checked || !biometricsCheck.checked || !isVideoRecorded) return;
        isDrawing = true;
        const coords = getCoords(e);
        lastX = coords.x;
        lastY = coords.y;
    }

    function draw(e) {
        if (!isDrawing) return;
        e.preventDefault(); // Evitar scroll en móviles
        
        const coords = getCoords(e);
        
        ctx.beginPath();
        ctx.moveTo(lastX, lastY);
        ctx.lineTo(coords.x, coords.y);
        ctx.stroke();
        
        lastX = coords.x;
        lastY = coords.y;
        hasStrokes = true;
        
        if (consentCheck.checked && biometricsCheck.checked && isVideoRecorded) {
            enableSubmitButton();
        }
    }

    function stopDrawing() {
        isDrawing = false;
    }

    // Mouse Listeners
    canvas.addEventListener("mousedown", startDrawing);
    canvas.addEventListener("mousemove", draw);
    canvas.addEventListener("mouseup", stopDrawing);
    canvas.addEventListener("mouseout", stopDrawing);

    // Touch Listeners (Móviles/Tabletas)
    canvas.addEventListener("touchstart", (e) => {
        startDrawing(e);
        if (e.touches.length === 1) e.preventDefault();
    }, { passive: false });
    canvas.addEventListener("touchmove", draw, { passive: false });
    canvas.addEventListener("touchend", stopDrawing);

    // 4. Borrar Canvas
    clearBtn.addEventListener("click", () => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        hasStrokes = false;
        disableSubmitButton();
        resultMsg.innerText = "";
    });

    // 5. Enviar Firma Electrónica y Video Evidencia al Servidor
    submitBtn.addEventListener('click', async () => {
        if (!hasStrokes) {
            alert('Por favor estampe su firma antes de confirmar.');
            return;
        }
        if (!consentCheck.checked || !biometricsCheck.checked) {
            alert('Debe aceptar los términos de consentimiento legal.');
            return;
        }
        if (!isVideoRecorded || !videoBlob) {
            alert('Debe grabar su video de declaración legal en viva voz primero.');
            return;
        }

        // Obtener la firma en base64 de tipo PNG
        const signatureBase64 = canvas.toDataURL("image/png");
        
        // Bloquear interfaz durante envío
        submitBtn.disabled = true;
        submitBtn.innerText = "Subiendo video evidencia a IPFS...";
        resultMsg.className = "text-xs text-center font-medium mt-2 text-indigo-400 animate-pulse";
        resultMsg.innerText = "Anclando grabación de consentimiento en la red inmutable IPFS...";

        let publicKeyBase64 = null;
        let cryptoSignatureBase64 = null;

        try {
            const token = window.SIGN_TOKEN;
            
            // 5.1. Convertir videoBlob a Base64 asíncronamente con Promesa
            const getBase64 = (blob) => new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.readAsDataURL(blob);
                reader.onload = () => resolve(reader.result);
                reader.onerror = error => reject(error);
            });
            
            const videoBase64 = await getBase64(videoBlob);
            
            // Subir primero el video al backend mediante JSON
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

            // 5.2. Proceder a firmar el documento
            submitBtn.innerText = "Consolidando PDF y estresando firmas...";
            resultMsg.innerText = "Sellando metadatos de video IPFS en el Certificado de Cadena de Custodia...";

            // FASE 2: Firmas Criptográficas Avanzadas ECDSA
            try {
                const keyPair = await window.crypto.subtle.generateKey(
                    {
                        name: "ECDSA",
                        namedCurve: "P-256"
                    },
                    true,
                    ["sign", "verify"]
                );
                
                const encoder = new TextEncoder();
                const tokenData = encoder.encode(token);
                const signatureBuffer = await window.crypto.subtle.sign(
                    {
                        name: "ECDSA",
                        hash: { name: "SHA-256" }
                    },
                    keyPair.privateKey,
                    tokenData
                );
                
                cryptoSignatureBase64 = btoa(String.fromCharCode(...new Uint8Array(signatureBuffer)));
                const publicKeyBuffer = await window.crypto.subtle.exportKey("spki", keyPair.publicKey);
                publicKeyBase64 = btoa(String.fromCharCode(...new Uint8Array(publicKeyBuffer)));
                console.log("✅ Firma Criptográfica Avanzada ECDSA local generada exitosamente.");
            } catch (cryptoErr) {
                console.warn("⚠️ No se pudo generar firma criptográfica avanzada ECDSA localmente:", cryptoErr);
            }

            const response = await fetch(`/sign/${token}`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    signature_base64: signatureBase64,
                    consent_electronic_signature: consentCheck.checked,
                    consent_habeas_data: biometricsCheck.checked,
                    public_key: publicKeyBase64,
                    crypto_signature: cryptoSignatureBase64
                })
            });

            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || "Error interno al firmar el documento.");
            }

            if (data.success) {
                resultMsg.className = "text-xs text-center font-bold mt-2 text-green-400";
                resultMsg.innerText = "¡Firmado exitosamente! Generando certificado y anclando a IPFS...";
                
                // Mostrar pantalla de éxito
                document.body.innerHTML = `
                    <div style="font-family: sans-serif; background-color: #050505; color: #e2e8f0; display: flex; align-items: center; justify-content: center; min-height: 100vh; height: auto; margin: 0; padding: 20px; box-sizing: border-box; background-image: radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.15) 0px, transparent 50%);">
                        <div style="background-color: #0c101f; padding: 30px 20px; border-radius: 16px; border: 1px solid #10b981; text-align: center; width: 100%; max-width: 480px; box-sizing: border-box; box-shadow: 0 10px 30px rgba(16,185,129,0.15);">
                            <div style="width: 60px; height: 60px; background-color: #10b981; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px auto; box-shadow: 0 0 20px rgba(16,185,129,0.4);">
                                <svg style="width: 32px; height: 32px; color: white;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                                </svg>
                            </div>
                            <h1 style="color: white; font-size: 22px; sm:font-size: 26px; font-weight: bold; margin-bottom: 15px;">¡Firma Registrada!</h1>
                            <p style="color: #94a3b8; font-size: 13px; sm:font-size: 14px; line-height: 1.6; margin-bottom: 25px; text-align: justify; text-justify: inter-word;">
                                Has firmado el documento de manera oficial. El sistema ha consolidado las firmas, generado el Certificado de Cadena de Custodia con la referencia al video IPFS y asegurado el contrato final.
                            </p>
                            ${data.ipfs_cid ? `<p style="font-size: 10px; sm:font-size: 11px; color: #10b981; font-family: monospace; background-color: rgba(16,185,129,0.08); padding: 10px 12px; border-radius: 8px; margin-bottom: 15px; word-break: break-all; overflow-wrap: break-word; white-space: normal; border: 1px solid rgba(16, 185, 129, 0.2); width: 100%; box-sizing: border-box;">Contrato CID: ${data.ipfs_cid}</p>` : ''}
                            ${videoResult.ipfs_cid ? `<p style="font-size: 10px; sm:font-size: 11px; color: #38bdf8; font-family: monospace; background-color: rgba(56,189,248,0.08); padding: 10px 12px; border-radius: 8px; margin-bottom: 15px; word-break: break-all; overflow-wrap: break-word; white-space: normal; border: 1px solid rgba(56, 189, 248, 0.2); width: 100%; box-sizing: border-box;">Video Evidencia CID: ${videoResult.ipfs_cid}</p>` : ''}
                            <p style="color: #64748b; font-size: 12px; line-height: 1.5; margin-top: 15px;">Se ha enviado una copia del documento final firmado y validado a todos los correos electrónicos de los firmantes.</p>
                        </div>
                    </div>
                `;
            } else {
                throw new Error(data.message || "Error al procesar la firma.");
            }

        } catch (error) {
            console.error("Error al someter firma electrónica:", error);
            
            // Interceptar error de red u offline para asegurar la firma localmente
            const isOffline = !navigator.onLine || error.message.includes("fetch") || error instanceof TypeError;
            if (isOffline && window.localDb) {
                try {
                    resultMsg.className = "text-xs text-center font-bold mt-2 text-amber-400 animate-pulse";
                    resultMsg.innerText = "Sin conexión estable. Asegurando firma localmente en el dispositivo...";
                    
                    // Obtener los blobs e informaciones requeridos
                    const token = window.SIGN_TOKEN;
                    const getBase64 = (blob) => new Promise((resolve, reject) => {
                        const reader = new FileReader();
                        reader.readAsDataURL(blob);
                        reader.onload = () => resolve(reader.result);
                        reader.onerror = err => reject(err);
                    });
                    
                    const videoBase64 = videoBlob ? await getBase64(videoBlob) : null;
                    
                    const offlineData = {
                        videoData: videoBase64 ? {
                            video_base64: videoBase64,
                            declaration_read: declarationTextVal
                        } : null,
                        signatureData: {
                            signature_base64: signatureBase64,
                            consent_electronic_signature: consentCheck.checked,
                            consent_habeas_data: biometricsCheck.checked,
                            public_key: publicKeyBase64,
                            crypto_signature: cryptoSignatureBase64
                        }
                    };
                    
                    await window.localDb.saveOfflineSignature(token, offlineData);
                    
                    // Mostrar pantalla de éxito offline
                    document.body.innerHTML = `
                        <div style="font-family: sans-serif; background-color: #050505; color: #e2e8f0; display: flex; align-items: center; justify-content: center; min-height: 100vh; height: auto; margin: 0; padding: 20px; box-sizing: border-box; background-image: radial-gradient(at 100% 100%, rgba(245, 158, 11, 0.15) 0px, transparent 50%);">
                            <div style="background-color: #0c101f; padding: 30px 20px; border-radius: 16px; border: 1px solid #f59e0b; text-align: center; width: 100%; max-width: 480px; box-sizing: border-box; box-shadow: 0 10px 30px rgba(245,158,11,0.15);">
                                <div style="width: 60px; height: 60px; background-color: #f59e0b; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px auto; box-shadow: 0 0 20px rgba(245,158,11,0.4);">
                                    <svg style="width: 32px; height: 32px; color: white;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                    </svg>
                                </div>
                                <h1 style="color: white; font-size: 22px; sm:font-size: 26px; font-weight: bold; margin-bottom: 15px;">Firma Guardada Localmente</h1>
                                <p style="color: #94a3b8; font-size: 13px; sm:font-size: 14px; line-height: 1.6; margin-bottom: 25px; text-align: justify; text-justify: inter-word;">
                                    ¡Te has quedado sin conexión! Star-Doc ha protegido de forma inmutable tu trazo de firma y evidencia de consentimiento en la base de datos de tu dispositivo. 
                                </p>
                                <p style="font-size: 11px; color: #f59e0b; font-family: monospace; background-color: rgba(245,158,11,0.08); padding: 10px 12px; border-radius: 8px; margin-bottom: 15px; border: 1px solid rgba(245,158,11,0.2); width: 100%; box-sizing: border-box;">
                                    Estado: Pendiente de Sincronización Automática
                                </p>
                                <p style="color: #64748b; font-size: 12px; line-height: 1.5; margin-top: 15px;">
                                    En cuanto tu dispositivo recupere conexión a internet, la firma se enviará y consolidará automáticamente con el servidor y se enviará la copia final de tu contrato. Puedes cerrar esta pestaña con tranquilidad.
                                </p>
                            </div>
                        </div>
                    `;
                    return;
                } catch (dbErr) {
                    console.error("Error al guardar firma en base de datos offline local:", dbErr);
                }
            }
            
            resultMsg.className = "text-xs text-center font-bold mt-2 text-red-500";
            resultMsg.innerText = "Error: " + error.message;
            enableSubmitButton();
        }
    });

    // Personalización del pincel (tinta y tamaño)
    const inkButtons = document.querySelectorAll(".ink-color-btn");
    inkButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            inkButtons.forEach(b => b.classList.remove("ring-2", "ring-indigo-400"));
            btn.classList.add("ring-2", "ring-indigo-400");
            strokeColor = btn.dataset.color;
            ctx.strokeStyle = strokeColor;
        });
    });
    // Activar botón de tinta por defecto al inicio
    document.querySelector('.ink-color-btn[data-color="#818cf8"]')?.classList.add("ring-2", "ring-indigo-400");

    const brushSizeSelect = document.getElementById("brush-size");
    if (brushSizeSelect) {
        brushSizeSelect.addEventListener("change", (e) => {
            brushWidth = parseInt(e.target.value);
            ctx.lineWidth = brushWidth;
        });
    }
});
