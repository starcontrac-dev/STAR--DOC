---
name: consulta_expedientes
description: Consulta expedientes judiciales en portales oficiales colombianos con navegador headless (Playwright).
compatibility: Requiere playwright + playwright-stealth + chromium
ui_icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />'
ui_color: '#8b5cf6'
short_description: Expedientes judiciales en tiempo real
examples:
  - "Estado del proceso 11001-31-03-027-2024-00123-00"
  - "Procesos judiciales de Juan Pérez"
  - "Sentencia T-760 de 2008"
  - "Buscar proceso en SAMAI del Consejo de Estado"
metadata:
  version: "1.0"
  category: "Consulta Judicial"
  permissions: []
  required_tools: ["buscar_expediente_judicial"]
---

# Protocolo de Consulta de Expedientes Judiciales

## Descripción
Este skill permite consultar expedientes judiciales en los portales oficiales de Colombia
utilizando un navegador headless (Playwright) para renderizar las SPAs con JavaScript.

## Uso
Cuando el usuario pregunte por el estado de un proceso judicial, usa la herramienta
`buscar_expediente_judicial`.

## Portales Soportados
1. **Rama Judicial** (consultaprocesos.ramajudicial.gov.co) - Búsqueda por radicación y nombre
2. **SAMAI** (samai.consejodeestado.gov.co) - Procesos contencioso-administrativos
3. **Corte Constitucional** (corteconstitucional.gov.co/relatoria/) - Sentencias de constitucionalidad

## Instrucciones para el Agente
1. Si el usuario proporciona un número de radicación (formato XX-XXXX-XX-XXX-XXXX-XXXXX-XX), 
   usa `numero_radicacion` directamente.
2. Si el usuario dice un nombre o razón social, usa `nombre_parte`.
3. Si menciona una sentencia de la Corte Constitucional (T-XXX/YYYY, C-XXX/YYYY, SU-XXX/YYYY), 
   usa `sentencia` con portal `corte_constitucional`.
4. Para procesos del Consejo de Estado, usa portal `samai`.
5. Si no proporciona suficiente información, **pide el número de radicación**.
