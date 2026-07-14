# 🔒 Política de Seguridad — STAR-DOC

## Versiones Soportadas

| Versión | Soporte          |
| ------- | ---------------- |
| 1.0.x   | ✅ Activo         |
| < 1.0   | ❌ Sin soporte    |

## ⚠️ Reportar una Vulnerabilidad

Si descubres una vulnerabilidad de seguridad en STAR-DOC, por favor **NO** la publiques en un Issue público.

### Proceso de Reporte

1. **Envía un correo** a: [starcontrac@gmail.com](mailto:starcontrac@gmail.com)
2. **Incluye**:
   - Descripción detallada de la vulnerabilidad.
   - Pasos para reproducirla.
   - Impacto potencial.
   - Sugerencia de corrección (si la tienes).

### Compromiso de Respuesta

- **Acuse de recibo**: 48 horas.
- **Evaluación inicial**: 5 días hábiles.
- **Corrección y parche**: según la severidad (crítico: 72h, alto: 7 días, medio: 14 días).

### Prácticas de Seguridad del Proyecto

- 🔐 Autenticación JWT con SECRET_KEY configurable y validación en producción.
- 🛡️ Headers de seguridad (HSTS, X-Content-Type-Options, X-Frame-Options, CSP).
- 🔑 Cifrado AES-256-GCM para documentos confidenciales en IPFS.
- 🧱 Rate limiting con SlowAPI para prevenir abuso.
- 🔍 Validación estricta de entradas con Pydantic v2.
- 🌐 Protección SSRF en webhooks.
- 📊 Auditoría de acceso a documentos con trazabilidad completa.

---

*Gracias por ayudarnos a mantener STAR-DOC seguro para todos. 🙏*
