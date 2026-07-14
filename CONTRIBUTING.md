# 🤝 Guía de Contribución — STAR-DOC

¡Gracias por tu interés en contribuir a **STAR-DOC**! Este documento describe las pautas para contribuir al proyecto.

## 📋 Código de Conducta

Al participar en este proyecto, te comprometes a mantener un ambiente respetuoso, inclusivo y profesional. No se tolerará ningún tipo de acoso, discriminación o comportamiento abusivo.

## 🚀 ¿Cómo Contribuir?

### 1. Reportar Bugs
- Usa la sección de [Issues](../../issues) con la etiqueta `bug`.
- Incluye: descripción clara, pasos para reproducir, comportamiento esperado vs. real, y capturas de pantalla si aplica.

### 2. Sugerir Funcionalidades
- Abre un [Issue](../../issues) con la etiqueta `enhancement`.
- Describe el problema que resuelve y la solución propuesta.

### 3. Contribuir con Código

#### Setup del Entorno
```bash
# 1. Fork del repositorio
# 2. Clonar tu fork
git clone https://github.com/tu-usuario/STAR--DOC.git
cd STAR--DOC

# 3. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 4. Instalar dependencias
pip install -r requirements.txt

# 5. Configurar variables de entorno
cp .env.example .env
# Edita .env con tus credenciales

# 6. Ejecutar la aplicación
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Flujo de Trabajo
1. Crea una rama descriptiva: `git checkout -b feature/nombre-de-la-feature`
2. Realiza tus cambios siguiendo las convenciones del proyecto.
3. Asegúrate de que el código funcione correctamente.
4. Haz commit con mensajes descriptivos en español:
   ```
   git commit -m "feat: agregar validación de campos en formulario de tutela"
   ```
5. Push a tu fork: `git push origin feature/nombre-de-la-feature`
6. Abre un Pull Request describiendo los cambios.

## 📝 Convenciones de Código

- **Lenguaje**: Python 3.11+ con type hints.
- **Framework**: FastAPI con SQLModel.
- **Documentación**: Comentarios y docstrings en **español**.
- **Estilo**: PEP 8 para Python, camelCase para JavaScript.
- **Commits**: Prefijos semánticos (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`).

## 🔒 Seguridad

- **NUNCA** incluyas credenciales, API keys o datos sensibles en el código.
- Usa variables de entorno (`.env`) para toda configuración sensible.
- Si encuentras una vulnerabilidad, consulta [SECURITY.md](SECURITY.md).

## 📄 Licencia

Al contribuir, aceptas que tu contribución será licenciada bajo la [Licencia MIT](LICENSE) del proyecto.

---

*¡Toda contribución, por pequeña que sea, hace la diferencia! 🌟*
