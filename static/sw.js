const CACHE_NAME = 'star-doc-v1';
const OFFLINE_URL = '/offline';

const CORE_ASSETS = [
  OFFLINE_URL,
  '/static/favicon.ico',
  '/static/manifest.json',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png'
];

const EXTERNAL_ASSETS = [
  'https://cdn.jsdelivr.net/npm/daisyui@4.12.10/dist/full.min.css',
  'https://cdn.tailwindcss.com',
  'https://unpkg.com/htmx.org@2.0.2',
  'https://unpkg.com/htmx-ext-json-enc@2.0.1/json-enc.js',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
  'https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;700&family=Space+Grotesk:wght@300;400;600&family=Merriweather:ital,wght@0,300;0,400;0,700;1,300&display=swap'
];

// Activos que se deben precargar y validar
const PRECACHE_ASSETS = [...CORE_ASSETS, ...EXTERNAL_ASSETS];

// Instalar Service Worker y precargar activos de forma robusta
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      console.log('[Service Worker] Precaching recursos estáticos locales');
      // 1. Precargar recursos críticos locales (si fallan, falla la instalación)
      await cache.addAll(CORE_ASSETS);
      
      // 2. Precargar recursos externos de forma tolerante a fallos (CORS-safe)
      console.log('[Service Worker] Precaching recursos externos con tolerancia a fallos');
      const cachePromises = EXTERNAL_ASSETS.map(async (url) => {
        try {
          // Recursos que requieren omitir validación de origen CORS usando modo opaco (no-cors)
          const useNoCors = url.includes('tailwindcss.com') || url.includes('fonts.googleapis.com');
          const request = new Request(url, useNoCors ? { mode: 'no-cors' } : {});
          const response = await fetch(request);
          await cache.put(request, response);
        } catch (error) {
          console.warn(`[Service Worker] Omitiendo precarga del CDN externo fallido: ${url}`, error);
        }
      });
      
      await Promise.all(cachePromises);
    }).then(() => self.skipWaiting())
  );
});

// Activar y limpiar cachés antiguas
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('[Service Worker] Limpiando caché antigua:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Interceptar peticiones y aplicar la estrategia adecuada
self.addEventListener('fetch', (event) => {
  const request = event.request;

  // Solo manejar peticiones GET
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // 1. Omitir solicitudes de rangos de bytes (videos y archivos grandes en iOS/Safari)
  if (request.headers.has('range')) return;

  // 2. Manejo de llamadas API dinámicas estando offline (retorna un JSON controlado)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request).catch(() => {
        return new Response(
          JSON.stringify({
            offline: true,
            success: false,
            detail: "Modo offline activo. Algunas funciones requieren conexión a internet."
          }),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 503
          }
        );
      })
    );
    return;
  }

  // Estrategia para navegación (solicitudes HTML de páginas enteras)
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Guardar una copia de la página navegada con éxito por si queda offline después
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            // Guardar solo páginas de la app (evitar guardar peticiones externas)
            if (url.origin === self.location.origin && !url.pathname.startsWith('/auth/')) {
              cache.put(request, responseClone);
            }
          });
          return response;
        })
        .catch(() => {
          // Si falla la red, intentar devolver de caché la página solicitada
          return caches.match(request).then((cachedResponse) => {
            if (cachedResponse) {
              return cachedResponse;
            }
            // Si no está en caché, devolver el fallback offline general
            return caches.match(OFFLINE_URL);
          });
        })
    );
    return;
  }

  // Estrategia para activos estáticos (CSS, JS, Fuentes, Imágenes)
  const isStaticAsset = 
    PRECACHE_ASSETS.includes(url.pathname) || 
    PRECACHE_ASSETS.includes(request.url) ||
    url.pathname.startsWith('/static/') ||
    url.hostname.includes('cdn.jsdelivr.net') ||
    url.hostname.includes('unpkg.com') ||
    url.hostname.includes('fonts.gstatic.com') ||
    url.hostname.includes('fonts.googleapis.com');

  if (isStaticAsset) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        if (cachedResponse) {
          // Devolver el recurso en caché de inmediato
          // Pero hacer un fetch en background para actualizar la caché (Stale While Revalidate)
          fetch(request).then((networkResponse) => {
            if (networkResponse.status === 200) {
              caches.open(CACHE_NAME).then((cache) => {
                cache.put(request, networkResponse);
              });
            }
          }).catch(() => {/* Silenciar errores de red offline */});
          return cachedResponse;
        }

        // Si no está en caché, buscarlo en la red
        return fetch(request).then((networkResponse) => {
          if (networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return networkResponse;
        });
      })
    );
  }
});

// --- 6. BACKGROUND SYNC DE FIRMAS OFFLINE ---
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-signatures') {
    event.waitUntil(syncOfflineSignaturesSW());
  }
});

async function syncOfflineSignaturesSW() {
  console.log('[Service Worker] Iniciando sincronización en segundo plano de firmas...');
  return new Promise((resolve, reject) => {
    // Abrir IndexedDB desde el Service Worker (compartiendo la versión 2 creada en el frontend)
    const dbRequest = indexedDB.open('stardoc_local_cache', 2);
    
    dbRequest.onerror = () => {
      console.error('[Service Worker] Error abriendo IndexedDB:', dbRequest.error);
      reject(dbRequest.error);
    };
    
    dbRequest.onsuccess = () => {
      const db = dbRequest.result;
      if (!db.objectStoreNames.contains('offline_signatures')) {
        resolve();
        return;
      }
      
      const tx = db.transaction('offline_signatures', 'readonly');
      const store = tx.objectStore('offline_signatures');
      const getAllRequest = store.getAll();
      
      getAllRequest.onerror = () => {
        reject(getAllRequest.error);
      };
      
      getAllRequest.onsuccess = async () => {
        const signatures = getAllRequest.result || [];
        if (signatures.length === 0) {
          resolve();
          return;
        }
        
        console.log(`[Service Worker] Encontradas ${signatures.length} firmas para procesar.`);
        
        for (const item of signatures) {
          const { token, data } = item;
          try {
            // 1. Subir video evidencia si existe
            if (data.videoData) {
              const videoRes = await fetch(`/api/meetings/upload-evidence/${token}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data.videoData)
              });
              if (!videoRes.ok) throw new Error('Fallo al subir video evidencia');
            }
            
            // 2. Enviar firma
            if (data.signatureData) {
              const signRes = await fetch(`/sign/${token}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data.signatureData)
              });
              if (!signRes.ok) throw new Error('Fallo al enviar firma');
            }
            
            // Eliminar de IndexedDB nativamente al completarse con éxito
            const deleteTx = db.transaction('offline_signatures', 'readwrite');
            const deleteStore = deleteTx.objectStore('offline_signatures');
            deleteStore.delete(token);
            console.log(`[Service Worker] Sincronización exitosa en background para token: ${token}`);
          } catch (err) {
            console.error(`[Service Worker] Error en sincronización para token ${token}:`, err);
          }
        }
        resolve();
      };
    };
  });
}

