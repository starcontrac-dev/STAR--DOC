<p align="center">
  <img src="static/icons/icon-512x512.png" alt="STAR-DOC Logo" width="180" />
</p>

<h1 align="center">⚡ STAR-DOC</h1>

<p align="center">
  <strong>Sistema de Inteligencia Artificial Legal de Grado Empresarial</strong><br/>
  <em>Automatización de documentos jurídicos · IA Generativa · IPFS · Firma Digital · Web3</em>
</p>

<p align="center">
  <a href="#-instalación-rápida"><img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"/></a>
  <a href="#-tecnologías"><img src="https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/></a>
  <a href="#-tecnologías"><img src="https://img.shields.io/badge/PostgreSQL-15+-336791?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"/></a>
  <a href="#-tecnologías"><img src="https://img.shields.io/badge/Gemini_AI--4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Gemini AI"/></a>
  <a href="#-tecnologías"><img src="https://img.shields.io/badge/IPFS-Web3-65C2CB?style=for-the-badge&logo=ipfs&logoColor=white" alt="IPFS"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="MIT License"/></a>
</p>

<p align="center">
  <a href="#-características-principales">Características</a> •
  <a href="#-arquitectura">Arquitectura</a> •
  <a href="#-instalación-rápida">Instalación</a> •
  <a href="#-configuración-de-apis">APIs</a> •
  <a href="#-uso">Uso</a> •
  <a href="#-contribuir">Contribuir</a>
</p>

---

## 🌟 ¿Qué es STAR-DOC?

**STAR-DOC** es una plataforma **full-stack de inteligencia legal** que combina **IA Generativa (Gemini )**, **almacenamiento inmutable en IPFS**, **firma digital con OTP**, y **automatización masiva de documentos** para transformar la práctica jurídica.

> 🧠 Imagina un abogado asistido por IA que puede: redactar contratos en segundos, buscar jurisprudencia actualizada en tiempo real, cifrar y certificar documentos en blockchain descentralizado, y gestionar una agenda completa de citas — todo desde una sola plataforma.

---

## 🚀 Características Principales

### 🤖 Motor de IA Legal (Gemini )
- **Chat Legal Inteligente** con streaming SSE en tiempo real
- **Cascada de Modelos**: `gemini-2.5-flash` → `gemini-2.5-pro` → `gemini-2.5-flash-lite` (fallback automático)
- **Rotación de API Keys** con balanceo de carga para alta disponibilidad
- **Herramientas de IA (Function Calling)**:
  - 🔍 Buscador de Jurisprudencia en tiempo real (Brave Search + Scraping de Altas Cortes)
  - 📄 Generador Automático de Documentos con plantillas Jinja2
  - 📊 Analizador de Contratos y Riesgos Legales
  - ⚖️ Calculadora de Liquidaciones Laborales
  - 📁 Buscador de Expedientes IPFS

### 📄 Automatización de Documentos
- **Generación Unitaria y Masiva (Batch)** de documentos legales
- **20+ Plantillas Legales** incluidas (contratos, tutelas, derechos de petición, etc.)
- **Motor de Plantillas Dual**: `.docx` (python-docx) y `.md` (Markdown)
- **Editor en línea** con preview en tiempo real
- **Comparación de versiones** (diff visual)

### 🔐 Firma Digital con OTP
- Firma electrónica con **verificación por código OTP** vía email
- **Certificados de Firma** con hash SHA-256 y sellado temporal
- **Trazabilidad completa** de firmantes, IPs y timestamps
- Soporte para **múltiples firmantes** en un mismo documento

### 🌐 IPFS & Web3 (Inmutabilidad Documental)
- **Almacenamiento en IPFS** vía nodo Kubo local + Pinata Cloud
- **Cifrado AES-256-GCM** para documentos confidenciales
- **Expedientes Merkle DAG** con hash SHA-256 individual por documento
- **IPNS (Versionado)** con direcciones criptográficas mutables
- **Cadena de Custodia** inmutable con bitácora de accesos
- **Auditoría de Integridad** criptográfica masiva

### 📹 Videoconferencias Legales
- **Jitsi Meet integrado** para reuniones con clientes
- **Grabación y transcripción** de audiencias
- **Procesamiento de audio con IA** (resumen automático de reuniones)

### 📅 Agenda Inteligente
- **Google Calendar integrado** para gestión de citas
- **Scheduler automático** con APScheduler
- **Notificaciones por email** (confirmación, recordatorios, alertas)
- **Widget de disponibilidad** para clientes

### 📊 Dashboard & Métricas
- Panel de control con **estadísticas de uso de IA**
- **Métricas de rendimiento** con Redis
- **Telemetría** de documentos generados, firmados y certificados

### 🔊 Text-to-Speech
- **Lectura en voz alta** de documentos y respuestas de IA
- Soporte para **múltiples voces e idiomas**
- Control de velocidad y pausa/reanudación

### 🛡️ Seguridad Empresarial
- **Autenticación JWT** con rotación de tokens
- **Rate Limiting** con SlowAPI
- **Headers de Seguridad** (HSTS, CSP, X-Frame-Options)
- **Protección SSRF** en webhooks
- **Validación estricta** con Pydantic v2
- **Circuit Breaker** para servicios externos (Redis)

### 📱 PWA (Progressive Web App)
- **Instalable** en dispositivos móviles y escritorio
- **Service Worker** para funcionamiento offline
- **Manifest.json** con iconos optimizados

---

## 🏗️ Arquitectura

```
┌──────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │  Landing Page │  │  Login/      │  │  Dashboard   │            │
│  │  (HTMX)      │  │  Register    │  │  (Alpine.js) │            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │  Chat IA     │  │  Editor de   │  │  Bóveda      │            │
│  │  (SSE Stream)│  │  Documentos  │  │  IPFS/Web3   │            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
│            │               │                │                     │
│       (EventSource)   (Fetch API)      (Fetch API)                │
└────────────┼───────────────┼────────────────┼─────────────────────┘
             │               │                │
             ▼               ▼                ▼
┌──────────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI)                              │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │                     API ROUTERS                             │   │
│  │  auth │ ai │ documents │ templates │ generation │ ipfs     │   │
│  │  signatures │ appointments │ meetings │ tts │ compliance   │   │
│  └────────────────────────────────────────────────────────────┘   │
│                              │                                    │
│                    ┌─────────┴─────────┐                          │
│                    ▼                   ▼                          │
│  ┌──────────────────────┐  ┌──────────────────────┐              │
│  │  SERVICES (Lógica)   │  │  DATABASE (SQLModel)  │              │
│  │  ai_service          │  │  PostgreSQL (asyncpg)  │              │
│  │  document_service    │  │  18 modelos de datos   │              │
│  │  signature_service   │  │  Alembic migraciones   │              │
│  │  ipfs_service        │  └──────────────────────┘              │
│  │  email_service       │                                        │
│  └──────────────────────┘                                        │
│         │              │              │                            │
│         ▼              ▼              ▼                            │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ Gemini   │  │ Google APIs  │  │ IPFS Kubo +  │               │
│  │ AI API   │  │ Drive/Cal    │  │ Pinata Cloud │               │
│  └──────────┘  └──────────────┘  └──────────────┘               │
└──────────────────────────────────────────────────────────────────┘
```

## 📁 Estructura del Proyecto

```
STAR--DOC/
├── app/                          # 🐍 Backend Principal
│   ├── main.py                   # Entry point FastAPI
│   ├── database.py               # Configuración SQLModel + asyncpg
│   ├── auth.py                   # Autenticación JWT + Web3
│   ├── scheduler.py              # APScheduler (tareas programadas)
│   ├── api/
│   │   ├── routers/              # 18 routers de la API
│   │   │   ├── ai.py             # Motor de IA (proxy Gemini + tools)
│   │   │   ├── auth.py           # Login/Register/OAuth/Web3
│   │   │   ├── documents.py      # CRUD de documentos
│   │   │   ├── generation.py     # Generación unitaria y batch
│   │   │   ├── ipfs/             # Módulo IPFS completo
│   │   │   ├── signatures.py     # Firma digital OTP
│   │   │   ├── meetings.py       # Videoconferencias Jitsi
│   │   │   └── ...               # +11 routers más
│   │   └── tools/                # Sistema de herramientas IA
│   │       ├── dispatcher.py     # Despachador de function calls
│   │       ├── handlers/         # 10 handlers especializados
│   │       └── schemas.py        # Schemas de herramientas
│   ├── ai/                       # Prompts y schemas de IA
│   ├── core/                     # Núcleo de la aplicación
│   │   ├── config.py             # Configuración centralizada
│   │   ├── browser_engine.py     # Motor Playwright (scraping)
│   │   ├── redis_client.py       # Cliente Redis con circuit breaker
│   │   ├── skills/               # Skills de IA (9 especializaciones)
│   │   └── tools/                # Herramientas core (jurisprudencia, cálculos)
│   ├── models/                   # 18 modelos SQLModel
│   ├── schemas/                  # Validaciones Pydantic v2
│   ├── services/                 # 28 servicios de negocio
│   │   ├── ai_service.py         # Orquestador de IA
│   │   ├── signature_service.py  # Motor de firma digital
│   │   ├── ipfs_service.py       # Integración IPFS/Kubo
│   │   ├── scrapers/             # Scrapers de jurisprudencia
│   │   └── ...
│   └── exceptions/               # Manejo centralizado de errores
├── templates/                    # 🎨 Frontend (Jinja2)
│   ├── base.html                 # Layout base
│   ├── landing.html              # Landing page pública
│   ├── ia.html                   # Chat de IA
│   ├── index.html                # Editor de documentos
│   ├── dashboard.html            # Panel de control
│   ├── components/               # Componentes modulares
│   └── emails/                   # Templates de email HTML
├── static/                       # 📦 Assets Estáticos
│   ├── js/                       # 11 controladores JavaScript
│   │   ├── app-ia.js             # Chat IA (102KB)
│   │   ├── vault-controller.js   # Bóveda IPFS (132KB)
│   │   └── ...
│   ├── icons/                    # Iconos PWA
│   └── sw.js                     # Service Worker
├── plantillas/                   # 📋 Plantillas Legales
│   ├── contrato_arrendamiento.docx
│   ├── accion_de_tutela.docx
│   ├── derecho_peticion.docx
│   └── ... (+20 plantillas)
├── alembic/                      # 🗄️ Migraciones de BD
├── scripts/                      # 🔧 Scripts de utilidad
├── docs/                         # 📖 OpenAPI spec
├── requirements.txt              # 📦 Dependencias Python
├── .env.example                  # ⚙️ Variables de entorno
└── README.md                     # 📘 Este archivo
```

---

## ⚡ Instalación Rápida

### Prerrequisitos

| Componente | Versión | Requerido |
|-----------|---------|-----------|
| Python | 3.11+ | ✅ Sí |
| PostgreSQL | 15+ | ✅ Sí |
| Redis | 7+ | ⚠️ Recomendado |
| IPFS Kubo | 0.28+ | ⚠️ Opcional (para Web3) |
| Node.js | 18+ | ⚠️ Opcional (para Playwright) |

### 1️⃣ Clonar el Repositorio

```bash
git clone https://github.com/starcontrac-dev/STAR--DOC.git
cd STAR--DOC
```

### 2️⃣ Crear Entorno Virtual

```bash
python -m venv venv

# Linux/Mac
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3️⃣ Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 4️⃣ Configurar Variables de Entorno

```bash
cp .env.example .env
```

Edita el archivo `.env` con tus credenciales. Consulta la sección [Configuración de APIs](#-configuración-de-apis) para obtener cada clave.

### 5️⃣ Configurar Base de Datos

```bash
# Crear la base de datos en PostgreSQL
createdb star_doc

# Ejecutar migraciones
alembic upgrade head
```

### 6️⃣ Iniciar la Aplicación

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 7️⃣ ¡Listo! 🎉

Abre tu navegador en: **http://localhost:8000**

- 📖 **Documentación API**: http://localhost:8000/docs
- 📋 **Redoc**: http://localhost:8000/redoc

---

## 🔑 Configuración de APIs

### Gemini AI (Obligatorio)
La IA es el corazón de STAR-DOC. Necesitas al menos **1 API key** de Gemini:

1. Ve a [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Crea una API key gratuita
3. Agrégala en `.env`:
   ```
   GEMINI_API_KEY=AIzaSy...
   ```
> 💡 **Pro Tip**: Agrega hasta 10 claves (`GEMINI_API_KEY_2`, `_3`, ..., `_10`) para rotación automática y evitar rate limits.

### Brave Search (Recomendado)
Para búsqueda de jurisprudencia en tiempo real:

1. Regístrate en [Brave Search API](https://brave.com/search/api/)
2. Obtén tu API key gratuita (2,000 consultas/mes)
3. Agrégala en `.env`:
   ```
   BRAVE_API_KEY=BSA...
   ```

### PostgreSQL (Obligatorio)
Base de datos principal:

```bash
# Instalar PostgreSQL 15+
# Crear base de datos
createdb star_doc

# En .env:
DATABASE_URL=postgresql+asyncpg://postgres:tu_password@localhost:5432/star_doc
```

### Redis (Recomendado)
Caché, métricas y circuit breaker:

```bash
# Instalar Redis
# Linux: sudo apt install redis-server
# Mac: brew install redis
# Windows: usar Docker
docker run -d -p 6379:6379 redis

# En .env:
REDIS_URL=redis://localhost:6379/0
```

### Google Calendar (Opcional)
Para gestión de citas y agenda:

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un proyecto y habilita la API de Google Calendar
3. Crea credenciales OAuth 2.0
4. Ejecuta `python scripts/auth_google_calendar.py` para obtener el refresh token

### Pinata / IPFS (Opcional)
Para almacenamiento Web3 inmutable:

1. Regístrate en [Pinata](https://app.pinata.cloud/)
2. Crea API keys en el dashboard
3. Para IPFS local, instala [Kubo](https://docs.ipfs.tech/install/command-line/)

### SMTP Email (Opcional)
Para notificaciones y firma digital:

1. Habilita [App Passwords](https://myaccount.google.com/apppasswords) en tu cuenta Gmail
2. Genera una contraseña de aplicación
3. Configúrala en `.env`

---

## 💻 Uso

### Chat de IA Legal
Accede a `/ia` para interactuar con el asistente legal. Funcionalidades:
- **Comandos Slash** (`/generar`, `/analizar`, `/buscar`)
- **Menciones de Plantillas** (`@contrato_arrendamiento`)
- **Streaming** de respuestas en tiempo real
- **Skills especializadas** (auditor de contratos, analista de riesgos, etc.)

### Generación de Documentos
Accede a `/editor` para:
- Seleccionar una plantilla legal
- Completar campos dinámicos
- Vista previa en tiempo real
- Descargar en `.docx` o enviar por email

### Bóveda IPFS
Accede al Dashboard → Infraestructura IPFS:
- Subir carpetas completas de expedientes
- Cifrar documentos confidenciales (AES-256-GCM)
- Verificar integridad criptográfica
- Consultar cadena de custodia

### API REST
Todas las funcionalidades están disponibles vía API:

```bash
# Ejemplo: Generar un documento
curl -X POST http://localhost:8000/generation/generate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"template_name": "contrato_arrendamiento", "fields": {"nombre": "Juan"}}'
```

---

## 🛠️ Tecnologías

| Categoría | Tecnología |
|-----------|-----------|
| **Backend** | FastAPI 0.111, Python 3.11+, Uvicorn |
| **Base de Datos** | PostgreSQL 15+, SQLModel, asyncpg, Alembic |
| **IA** | Google Gemini (Flash/Pro), httpx |
| **Frontend** | Jinja2, Alpine.js, HTMX, Vanilla JS |
| **Auth** | JWT (python-jose), Web3 (eth-account) |
| **Documentos** | python-docx, docxtpl, PyMuPDF, Mammoth |
| **IPFS/Web3** | Kubo HTTP API, Pinata Cloud |
| **Email** | fastapi-mail, Gmail SMTP |
| **Cache** | Redis 7+ |
| **Seguridad** | SlowAPI, Pydantic v2, Argon2 |
| **Scheduling** | APScheduler |
| **Video** | Jitsi Meet SDK |
| **PWA** | Service Worker, Web Manifest |

---

## 🗺️ Roadmap

- [x] Motor de IA con Gemini + Function Calling
- [x] Generación masiva (batch) de documentos
- [x] Firma digital con verificación OTP
- [x] Almacenamiento IPFS con cifrado AES-256
- [x] Cadena de custodia inmutable
- [x] Videoconferencias con Jitsi Meet
- [x] Text-to-Speech integrado
- [x] PWA instalable
- [ ] Integración con blockchain (Ethereum/Polygon)
- [ ] RAG avanzado con embeddings vectoriales
- [ ] Multi-idioma (EN, PT, FR)
- [ ] Marketplace de plantillas
- [ ] Plugin para Microsoft Word

---

## 🤝 Contribuir

¡Las contribuciones son bienvenidas! Consulta [CONTRIBUTING.md](CONTRIBUTING.md) para las pautas.

```bash
# Fork → Clone → Branch → Code → Push → Pull Request
git checkout -b feature/mi-feature
git commit -m "feat: agregar nueva funcionalidad"
git push origin feature/mi-feature
```

---

## 📄 Licencia

Este proyecto está bajo la [Licencia MIT](LICENSE).

---

## 📬 Contacto

- **Email**: [starcontrac@gmail.com](mailto:starcontrac@gmail.com)
- **GitHub**: [@starcontrac-dev](https://github.com/starcontrac-dev)

---

<p align="center">
  Hecho con ❤️ para la comunidad legal
  <br/>
  <strong>⭐ Si te gusta el proyecto, dale una estrella ⭐</strong>
</p>
