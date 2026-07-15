# Plan de Mejoras del README.md - STAR-DOC

Este plan ha sido diseñado para enriquecer la documentación del proyecto **STAR-DOC**, describiendo con rigor técnico y normativo las características principales añadidas en la suite, tales como Auditoría Legal & Compliance SARLAFT, Skills del Agente IA y Autenticación Web3.

---

## 🎯 Objetivos de la Mejora
1. **Vídeo de Demostración:** Añadir de manera visual el video de YouTube `https://www.youtube.com/watch?v=uTKZsq6LOeo&t=21s` en la sección introductoria.
2. **Auditoría Legal & SARLAFT:** Explicar el proceso de cumplimiento que cruza bases de datos nacionales (datos.gov.co: Contraloría, Procuraduría) y listas restrictivas internacionales (OFAC, ONU) bajo la normativa colombiana de SARLAFT y SAGRILAFT.
3. **Skills de IA y Comandos Slash:** Detallar los comandos clave como `/notebooklm-legal`, `/consulta-expedientes` y `/entrevistador-pro` dentro del sistema de Progressive Disclosure del `SkillManager`.
4. **Inicio de Sesión Web3:** Explicar la autenticación criptográfica mediante firma de mensajes nonce efímeros usando Redis y librerías Web3.

---

## 📋 Modificaciones Propuestas en README.md

### 1. Banner de Video de YouTube
Se integrará bajo la sección de ¿Qué es STAR-DOC? para dar un impacto visual inmediato:
```markdown
<p align="center">
  <a href="https://www.youtube.com/watch?v=uTKZsq6LOeo&t=21s" target="_blank">
    <img src="https://img.youtube.com/vi/uTKZsq6LOeo/0.jpg" alt="Video Explicativo de STAR-DOC" width="600" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);" />
  </a>
  <br/>
  <em>Haz clic para ver el video explicativo y demostración en YouTube.</em>
</p>
```

### 2. Sección: 💼 Auditoría Legal & Compliance (SARLAFT/SAGRILAFT)
Se agregará una subsección bajo "Características Principales":
- Explicar la normativa colombiana (Superfinanciera y Supersociedades).
- Indicar los cruces con APIs públicas (`datos.gov.co` de Contraloría y Procuraduría).
- Indicar la verificación en listas OFAC (SDN) y ONU.
- Explicar la toma de decisiones por el Oficial de Cumplimiento (`APROBADO`, `RIESGO_ALTO`, `BLOQUEADO`).

### 3. Sección: 🤖 Skills del Asistente IA (Slash Commands)
Detallar el uso de los 9 comandos disponibles en el chat legal:
- `/notebooklm-legal`: RAG para consulta de cuadernos de leyes e investigación sin alucinaciones.
- `/consulta-expedientes`: Crawling headless de procesos judiciales mediante Playwright.
- `/entrevistador-pro`: Recolección estructurada y validación de datos en caliente.
- Mencionar los otros comandos: `/analista-riesgos`, `/auditor-contratos`, `/jurisprudencia-pro`, `/contestador-tutelas`, `/gestor-liquidaciones` y `/generador-documentos`.

### 4. Sección: 🌐 Autenticación Web3 Descentralizada (Web3 Auth)
Describir el proceso técnico:
- Desafío nonce con expiración en Redis (DB 5).
- Firma mediante billetera EVM (MetaMask, WalletConnect).
- Validación asíncrona mediante `eth-account` en FastAPI.
- Emisión de JWT y almacenamiento en cookies seguras (HttpOnly, Secure, SameSite=Lax).

---

## 🔍 Plan de Verificación
1. **Sintaxis Markdown:** Revisar que los enlaces sean correctos y válidos.
2. **Estructura:** Asegurar que las secciones se integren de forma fluida sin romper el contenido actual del README.md.
