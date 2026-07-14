/**
 * pwa-controller.js
 * Controlador modular para la PWA de STAR-DOC.
 * Implementa:
 * 1. Custom Install Prompt (Banner de instalación in-app y botón en Sidebar).
 * 2. Badging API (Insignias de notificación en el icono de la app).
 * 3. Live Network Status Toast (Notificación en vivo de conexión).
 * 4. LocalDatabase (Capa de abstracción para IndexedDB nativo).
 */

/**
 * Detecta si la aplicación se está ejecutando como una PWA instalada (en modo standalone).
 * @returns {boolean}
 */
window.isPwaStandalone = function() {
  return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
};

// --- 1. CAPA DE ALMACENAMIENTO INDEXEDDB NATIVO ---
class LocalDatabase {
  constructor() {
    this.dbName = 'stardoc_local_cache';
    this.dbVersion = 2;
    this.db = null;
  }

  async init() {
    return new Promise((resolve, reject) => {
      if (!window.indexedDB) {
        console.warn('[PWA DB] IndexedDB no está soportado en este navegador.');
        resolve(null);
        return;
      }
      const request = indexedDB.open(this.dbName, this.dbVersion);
      
      request.onerror = () => {
        console.error('[PWA DB] Error abriendo IndexedDB:', request.error);
        reject(request.error);
      };
      
      request.onsuccess = () => {
        this.db = request.result;
        console.log('[PWA DB] Base de datos local inicializada con éxito.');
        resolve(this.db);
      };
      
      request.onupgradeneeded = (e) => {
        const db = e.target.result;
        // Almacenar borradores temporales de formularios
        if (!db.objectStoreNames.contains('drafts')) {
          db.createObjectStore('drafts', { keyPath: 'id' });
        }
        // Almacenar historial del chat
        if (!db.objectStoreNames.contains('chat_history')) {
          db.createObjectStore('chat_history', { keyPath: 'threadId' });
        }
        // Almacenar firmas sin conexión para sincronización posterior
        if (!db.objectStoreNames.contains('offline_signatures')) {
          db.createObjectStore('offline_signatures', { keyPath: 'token' });
        }
      };
    });
  }

  async saveOfflineSignature(token, data) {
    if (!this.db) await this.init();
    if (!this.db) return null;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('offline_signatures', 'readwrite');
      const store = tx.objectStore('offline_signatures');
      const request = store.put({ token, data, updatedAt: new Date().toISOString() });
      
      request.onsuccess = () => resolve(true);
      request.onerror = () => reject(request.error);
    });
  }

  async getOfflineSignatures() {
    if (!this.db) await this.init();
    if (!this.db) return [];
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('offline_signatures', 'readonly');
      const store = tx.objectStore('offline_signatures');
      const request = store.getAll();
      
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  }

  async deleteOfflineSignature(token) {
    if (!this.db) await this.init();
    if (!this.db) return null;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('offline_signatures', 'readwrite');
      const store = tx.objectStore('offline_signatures');
      const request = store.delete(token);
      
      request.onsuccess = () => resolve(true);
      request.onerror = () => reject(request.error);
    });
  }

  async saveDraft(id, data) {
    if (!this.db) await this.init();
    if (!this.db) return null;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('drafts', 'readwrite');
      const store = tx.objectStore('drafts');
      const request = store.put({ id, data, updatedAt: new Date().toISOString() });
      
      request.onsuccess = () => resolve(true);
      request.onerror = () => reject(request.error);
    });
  }

  async getDraft(id) {
    if (!this.db) await this.init();
    if (!this.db) return null;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('drafts', 'readonly');
      const store = tx.objectStore('drafts');
      const request = store.get(id);
      
      request.onsuccess = () => resolve(request.result ? request.result.data : null);
      request.onerror = () => reject(request.error);
    });
  }

  async getDrafts() {
    if (!this.db) await this.init();
    if (!this.db) return [];
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction('drafts', 'readonly');
      const store = tx.objectStore('drafts');
      const request = store.getAll();
      
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  }
}

// Instanciar base de datos global
window.localDb = new LocalDatabase();
window.localDb.init().catch(err => console.error('[PWA DB] Error en la inicialización:', err));


// --- 2. API DE INSIGNIAS (BADGING API) ---
window.updatePwaBadge = async function(count) {
  if ('setAppBadge' in navigator) {
    try {
      const num = parseInt(count, 10);
      if (!isNaN(num) && num > 0) {
        await navigator.setAppBadge(num);
        console.log(`[PWA Badge] Actualizado con éxito a: ${num}`);
      } else {
        await navigator.clearAppBadge();
        console.log('[PWA Badge] Limpiado con éxito.');
      }
    } catch (error) {
      console.error('[PWA Badge] Error al actualizar la insignia del icono:', error);
    }
  }
};


// --- 3. NOTIFICADOR DE RED EN VIVO (TOAST INTERACTIVO) ---
function showNetworkToast(status) {
  const toast = document.getElementById('pwa-network-toast');
  const alertEl = document.getElementById('pwa-network-alert');
  const msgEl = document.getElementById('pwa-network-message');
  
  if (!toast || !alertEl || !msgEl) return;
  
  toast.classList.remove('hidden');
  
  if (status === 'online') {
    alertEl.className = 'alert shadow-2xl backdrop-blur-md border alert-success bg-emerald-950/80 border-emerald-500/30 text-emerald-200';
    msgEl.innerHTML = '<i class="bi bi-wifi text-base mr-1"></i> Conexión restablecida. Sincronizando datos...';
    
    // Ocultar automáticamente en 3 segundos
    setTimeout(() => {
      toast.classList.add('hidden');
    }, 3000);
  } else {
    alertEl.className = 'alert shadow-2xl backdrop-blur-md border alert-warning bg-amber-950/80 border-amber-500/30 text-amber-200';
    msgEl.innerHTML = '<i class="bi bi-wifi-off text-base mr-1"></i> Sin conexión. Navegando en modo local (caché).';
  }
}

window.addEventListener('online', () => showNetworkToast('online'));
window.addEventListener('offline', () => showNetworkToast('offline'));

// Mostrar estado inicial si se carga sin conexión
window.addEventListener('DOMContentLoaded', () => {
  if (!navigator.onLine) {
    showNetworkToast('offline');
  }
});


// --- 4. LÓGICA DE INSTALACIÓN PERSONALIZADA PWA ---
window.addEventListener('DOMContentLoaded', () => {
  const installBanner = document.getElementById('pwa-install-banner');
  const installBtn = document.getElementById('pwa-install-btn');
  const closeBtn = document.getElementById('pwa-close-btn');
  const sidebarInstallBtn = document.getElementById('pwa-install-sidebar-btn');
  
  // Botones opcionales de instalación de PWA
  const heroInstallBtn = document.getElementById('hero-pwa-install-btn');
  const navInstallBtn = document.getElementById('nav-pwa-install-btn');
  const ctaInstallBtn = document.getElementById('cta-pwa-install-btn');

  // Detectar si la app ya está instalada y ejecutándose en standalone
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;

  function hidePwaBanner() {
    if (installBanner) {
      installBanner.classList.remove('translate-y-0', 'opacity-100');
      installBanner.classList.add('translate-y-24', 'opacity-0');
      setTimeout(() => {
        installBanner.classList.add('hidden');
      }, 500);
    }
  }

  function showPwaUI() {
    if (isStandalone) return;
    
    // Mostrar el botón en el sidebar si existe
    if (sidebarInstallBtn) {
      sidebarInstallBtn.classList.remove('hidden');
    }

    if (sessionStorage.getItem('pwa-banner-dismissed') !== 'true') {
      if (installBanner) {
        installBanner.classList.remove('hidden');
        setTimeout(() => {
          installBanner.classList.remove('translate-y-24', 'opacity-0');
          installBanner.classList.add('translate-y-0', 'opacity-100');
        }, 100);
      }
    }
  }

  if (isStandalone) {
    console.log('[PWA] Ejecutando en modo Standalone (PWA Instalada).');
    if (installBanner) installBanner.remove();
    if (sidebarInstallBtn) sidebarInstallBtn.remove();
    if (heroInstallBtn) heroInstallBtn.remove();
    if (navInstallBtn) navInstallBtn.remove();
    if (ctaInstallBtn) ctaInstallBtn.remove();
  } else {
    // Asegurarse de que los botones estén visibles si existen en el DOM
    if (heroInstallBtn) {
      heroInstallBtn.classList.remove('hidden');
      heroInstallBtn.style.display = 'inline-flex';
    }
    if (navInstallBtn) {
      navInstallBtn.classList.remove('hidden');
      navInstallBtn.style.display = 'inline-flex';
    }
    if (ctaInstallBtn) {
      ctaInstallBtn.classList.remove('hidden');
      ctaInstallBtn.style.display = 'inline-flex';
    }
    
    // Si deferredPrompt ya está listo
    if (window.deferredPrompt) {
      showPwaUI();
    }
  }

  // O escuchar cuando ocurra el evento
  window.addEventListener('pwa-prompt-ready', () => {
    showPwaUI();
  });

  // Lógica de disparo de instalación
  const triggerPwaInstall = async (btnEl) => {
    const promptEvent = window.deferredPrompt;
    if (!promptEvent) {
      // Si no hay prompt nativo disponible, abrir modal instructivo
      if (typeof window.showManualInstallInstructions === 'function') {
        window.showManualInstallInstructions();
      }
      return;
    }
    
    const originalContent = btnEl ? btnEl.innerHTML : 'Instalar';
    if (btnEl) {
      btnEl.innerHTML = '<span class="loading loading-spinner loading-xs mr-1"></span> Instalando...';
    }
    
    try {
      promptEvent.prompt();
      const { outcome } = await promptEvent.userChoice;
      console.log(`[PWA] Respuesta del usuario a la instalación: ${outcome}`);
      window.deferredPrompt = null;
      hidePwaBanner();
      if (sidebarInstallBtn) sidebarInstallBtn.classList.add('hidden');
    } catch (err) {
      console.error('[PWA] Error al solicitar la instalación PWA:', err);
      if (typeof window.showManualInstallInstructions === 'function') {
        window.showManualInstallInstructions();
      }
    } finally {
      if (btnEl) {
        btnEl.innerHTML = originalContent;
      }
    }
  };

  // Asignar eventos de clic
  if (installBtn) installBtn.addEventListener('click', () => triggerPwaInstall(installBtn));
  if (sidebarInstallBtn) sidebarInstallBtn.addEventListener('click', () => triggerPwaInstall(sidebarInstallBtn));
  if (heroInstallBtn) heroInstallBtn.addEventListener('click', () => triggerPwaInstall(heroInstallBtn));
  if (navInstallBtn) navInstallBtn.addEventListener('click', () => triggerPwaInstall(navInstallBtn));
  if (ctaInstallBtn) ctaInstallBtn.addEventListener('click', () => triggerPwaInstall(ctaInstallBtn));

  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      sessionStorage.setItem('pwa-banner-dismissed', 'true');
      hidePwaBanner();
    });
  }

  // Escuchar cuando la aplicación se instale
  window.addEventListener('appinstalled', (evt) => {
    console.log('[PWA] STAR-DOC se instaló correctamente.');
    if (window.showToast) {
      window.showToast('¡STAR-DOC instalada con éxito!', 'success');
    }
    if (sidebarInstallBtn) sidebarInstallBtn.remove();
    if (heroInstallBtn) heroInstallBtn.remove();
    if (navInstallBtn) navInstallBtn.remove();
    if (ctaInstallBtn) ctaInstallBtn.remove();
    hidePwaBanner();
  });
});

// --- 5. FUNCIONES DE INSTALACIÓN MANUAL (FALLBACK INTERFAZ) ---
window.getMobileOperatingSystem = function() {
  const userAgent = navigator.userAgent || navigator.vendor || window.opera;
  if (/android/i.test(userAgent)) {
    return "android";
  }
  if (/iPad|iPhone|iPod/.test(userAgent) && !window.MSStream) {
    return "ios";
  }
  return "desktop";
};

window.selectPwaTab = function(os) {
  // Ocultar contenidos
  document.getElementById('pwa-content-ios').classList.add('hidden');
  document.getElementById('pwa-content-android').classList.add('hidden');
  document.getElementById('pwa-content-desktop').classList.add('hidden');
  
  // Limpiar estilos de botones de pestañas
  const tabs = ['ios', 'android', 'desktop'];
  tabs.forEach(t => {
    const btn = document.getElementById(`tab-pwa-${t}`);
    if (btn) {
      btn.classList.remove(
        'bg-primary/20', 'text-primary', 'border-primary/30', 
        'bg-accent/20', 'text-accent', 'border-accent/30', 
        'bg-secondary/20', 'text-secondary', 'border-secondary/30',
        'bg-white/5', 'border-white/10'
      );
      btn.classList.add('text-gray-400', 'hover:text-white');
    }
  });

  // Mostrar contenido correspondiente
  const activeContent = document.getElementById(`pwa-content-${os}`);
  if (activeContent) activeContent.classList.remove('hidden');

  // Activar botón con el color respectivo
  const activeBtn = document.getElementById(`tab-pwa-${os}`);
  if (activeBtn) {
    activeBtn.classList.remove('text-gray-400', 'hover:text-white');
    if (os === 'ios') {
      activeBtn.classList.add('bg-primary/20', 'text-primary', 'border', 'border-primary/30');
    } else if (os === 'android') {
      activeBtn.classList.add('bg-accent/20', 'text-accent', 'border', 'border-accent/30');
    } else {
      activeBtn.classList.add('bg-secondary/20', 'text-secondary', 'border', 'border-secondary/30');
    }
  }
};

window.showManualInstallInstructions = function() {
  const modal = document.getElementById('pwa-instructions-modal');
  if (modal) {
    modal.showModal();
    const detectedOs = window.getMobileOperatingSystem();
    window.selectPwaTab(detectedOs);
  }
};

// --- 6. SINCRONIZADOR DE FIRMAS OFFLINE (BACKGROUND & FOREGROUND SYNC) ---
window.syncOfflineSignatures = async function() {
  if (!navigator.onLine) return;
  try {
    const signatures = await window.localDb.getOfflineSignatures();
    if (signatures.length === 0) return;

    console.log(`[PWA Sync] Detectadas ${signatures.length} firmas offline pendientes de sincronización.`);

    for (const item of signatures) {
      const { token, data } = item;
      try {
        console.log(`[PWA Sync] Sincronizando firma offline para el token: ${token}`);

        // 1. Subir video evidencia si existe
        if (data.videoData) {
          const videoRes = await fetch(`/api/meetings/upload-evidence/${token}`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json"
            },
            body: JSON.stringify(data.videoData)
          });
          if (!videoRes.ok) {
            const errText = await videoRes.text();
            throw new Error(`Fallo al subir video evidencia: ${errText}`);
          }
        }

        // 2. Enviar firma
        if (data.signatureData) {
          const signRes = await fetch(`/sign/${token}`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json"
            },
            body: JSON.stringify(data.signatureData)
          });
          if (!signRes.ok) {
            const errText = await signRes.text();
            throw new Error(`Fallo al enviar firma: ${errText}`);
          }
        }

        // Eliminar de base de datos local al sincronizar con éxito
        await window.localDb.deleteOfflineSignature(token);
        console.log(`[PWA Sync] Firma offline sincronizada correctamente para el token: ${token}`);

        // Intentar lanzar notificación toast si la función global existe
        if (window.showToast) {
          window.showToast("Tu firma guardada sin conexión se ha sincronizado con éxito.", "success");
        } else {
          console.log("[PWA Sync] Firma sincronizada con éxito (notificación toast omitida).");
        }
      } catch (err) {
        console.error(`[PWA Sync] Error sincronizando firma para token ${token}:`, err);
      }
    }
  } catch (error) {
    console.error('[PWA Sync] Error general en proceso de sincronización:', error);
  }
};

// Sincronizar inmediatamente al volver a estar online
window.addEventListener('online', () => {
  window.syncOfflineSignatures();
});

// Sincronizar al cargar la página si está online
window.addEventListener('DOMContentLoaded', () => {
  if (navigator.onLine) {
    // Retrasar ligeramente para asegurar la carga completa de dependencias UI
    setTimeout(() => {
      window.syncOfflineSignatures();
    }, 1500);
  }
});

// Registrar sincronización en segundo plano mediante Service Worker si está soportado (Chromium)
if ('serviceWorker' in navigator && 'SyncManager' in window) {
  navigator.serviceWorker.ready.then((reg) => {
    window.addEventListener('online', () => {
      reg.sync.register('sync-signatures')
        .then(() => console.log('[PWA Sync] Registro de Background Sync exitoso.'))
        .catch((err) => console.warn('[PWA Sync] No se pudo registrar Background Sync:', err));
    });
  });
}


