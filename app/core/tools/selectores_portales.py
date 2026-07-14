"""
Selectores CSS desacoplados para portales judiciales colombianos.

Los selectores se mantienen en este archivo separado para facilitar
su actualización sin modificar la lógica de scraping.

Actualizar con: playwright codegen <URL_del_portal>
"""

# Selectores organizados por portal
SELECTORES = {
    "rama_judicial": {
        "url_radicacion": "https://consultaprocesos.ramajudicial.gov.co/Procesos/NumeroRadicacion",
        "url_nombre": "https://consultaprocesos.ramajudicial.gov.co/Procesos/NombreRazonSocial",
        "input_radicacion": "input[placeholder*='23 dígitos'], input[type='text']",
        "input_nombre": "input[placeholder*='Nombre'], .v-text-field input",
        "btn_buscar": "button.success, .v-btn.success, button:has-text('CONSULTAR')",
        "tabla_resultados": "table, .v-data-table",
        "fila_proceso": "tr:not(:first-child), .v-data-table__wrapper tr",
        "no_results": ".no-results, .text-center",
    },
    "samai": {
        "url": "https://samai.consejodeestado.gov.co/Vistas/Casos/procesos.aspx",
        "input_radicado": "input#txtRadicado",
        "btn_buscar": "input#btnBuscar, button[type='submit']",
        "tabla_resultados": "table#grvResultado, table.table",
    },
    "corte_constitucional": {
        "url": "https://www.corteconstitucional.gov.co/relatoria/",
        "input_busqueda": "input#txtBusqueda, input[type='search'], input[type='text']",
        "btn_buscar": "button#btnBuscar, input[type='submit']",
        "resultados": ".resultado, .list-group, table",
    },
    "publicaciones_procesales": {
        "url": "https://publicacionesprocesales.ramajudicial.gov.co/",
        "input_radicado": "input#radicado, input[type='text']",
        "btn_buscar": "button[type='submit'], .btn-primary",
        "resultados": ".resultados, table",
    },
    "siugj": {
        "url": "https://siugj.ramajudicial.gov.co/principalPortal/consultarProceso.php",
        "input_radicado": "input#radicado, input[name='radicado']",
        "btn_buscar": "button[type='submit'], input[type='submit']",
        "tabla_resultados": "table",
    }
}

# ============================================================================
# SELECTORES PARA RELATORÍAS DE JURISPRUDENCIA
# Portales oficiales donde se buscan sentencias, autos y normativa colombiana.
# ============================================================================
SELECTORES_JURISPRUDENCIA = {
    # ── Corte Constitucional (Angular SPA) ──────────────────────────────
    # URL: https://www.corteconstitucional.gov.co/relatoria/buscador-jurisprudencia
    # Selectores confirmados por inspección directa del DOM (Angular).
    "constitucional": {
        "url": "https://www.corteconstitucional.gov.co/relatoria/buscador-jurisprudencia",
        "input_busqueda": "input#textoBuscador",
        "select_categoria": "select#selectBuscador",
        # Opciones del select: 0=Texto completo, 1=Temas, 2=Resuelve, 3=Normas, 4=Número sentencia
        "categorias": {
            "texto_completo": "0",
            "temas": "1",
            "resuelve": "2",
            "normas_demandadas": "3",
            "numero_sentencia": "4",
        },
        "input_fecha_inicio": "input#datePicker1",
        "input_fecha_fin": "input#datePicker2",
        "btn_buscar": "button[type='submit'].btn-corte, button:has-text('Buscar')",
        "btn_limpiar": "button:has-text('Limpiar')",
        # Contenedores de resultados (Angular renderiza dinámicamente)
        "contenedor_resultados": ".resultados, .list-group, .card, .resultado-item, app-resultado",
        "item_resultado": ".list-group-item, .card, .resultado-item, [class*='result']",
        "paginacion": ".pagination, nav[aria-label*='paginación'], .page-link",
        "sin_resultados": ".alert-warning, .no-results, :has-text('No se encontraron')",
        "wait_for": "input#textoBuscador",  # Selector para confirmar que la SPA cargó
    },

    # ── Corte Suprema de Justicia (JSF/PrimeFaces) ─────────────────────
    # URL: https://consultajurisprudencial.ramajudicial.gov.co/WebRelatoria/csj/index.xhtml
    "suprema": {
        "url": "https://consultajurisprudencial.ramajudicial.gov.co/WebRelatoria/csj/index.xhtml",
        "input_busqueda": "input[id$='txtBuscar'], input[type='text'][class*='ui-inputtext']",
        "btn_buscar": "button[id$='btnBuscar'], .ui-button:has-text('Buscar'), button:has-text('Buscar')",
        # Filtros PrimeFaces (IDs dinámicos con prefijo de formulario)
        "select_sala": "select[id$='cmbSala'], div[id$='cmbSala'] select",
        "input_fecha_desde": "input[id$='txtFechaDesde'], input[id$='calFechaDesde_input']",
        "input_fecha_hasta": "input[id$='txtFechaHasta'], input[id$='calFechaHasta_input']",
        "contenedor_resultados": ".ui-datatable, table[role='grid'], .ui-datatable-tablewrapper",
        "fila_resultado": ".ui-datatable tbody tr, .ui-datatable-data tr",
        "link_sentencia": "a[href*='detalle'], .ui-commandlink",
        "paginacion": ".ui-paginator, .ui-paginator-pages",
        "sin_resultados": ".ui-messages, .ui-message-error, :has-text('No se encontraron')",
        "wait_for": "input[id$='txtBuscar'], input[type='text']",
    },

    # ── Consejo de Estado (JSF/PrimeFaces) ──────────────────────────────
    # URL: https://servicios.consejodeestado.gov.co/WebRelatoria/ce/index.xhtml
    "consejo_estado": {
        "url": "https://servicios.consejodeestado.gov.co/WebRelatoria/ce/index.xhtml",
        "input_busqueda": "input[id$='txtBuscar'], input[type='text'][class*='ui-inputtext']",
        "btn_buscar": "button[id$='btnBuscar'], .ui-button:has-text('Buscar'), button:has-text('Buscar')",
        "select_seccion": "select[id$='cmbSeccion'], div[id$='cmbSeccion'] select",
        "input_fecha_desde": "input[id$='txtFechaDesde'], input[id$='calFechaDesde_input']",
        "input_fecha_hasta": "input[id$='txtFechaHasta'], input[id$='calFechaHasta_input']",
        "contenedor_resultados": ".ui-datatable, table[role='grid'], .ui-datatable-tablewrapper",
        "fila_resultado": ".ui-datatable tbody tr, .ui-datatable-data tr",
        "link_sentencia": "a[href*='detalle'], .ui-commandlink",
        "paginacion": ".ui-paginator, .ui-paginator-pages",
        "sin_resultados": ".ui-messages, .ui-message-error, :has-text('No se encontraron')",
        "wait_for": "input[id$='txtBuscar'], input[type='text']",
    },

    # ── SISJUR - Alcaldía de Bogotá ─────────────────────────────────────
    # URL: https://www.alcaldiabogota.gov.co/sisjur/index.jsp
    "sisjur": {
        "url": "https://www.alcaldiabogota.gov.co/sisjur/index.jsp",
        "url_busqueda": "https://www.alcaldiabogota.gov.co/sisjur/normas/Norma1.jsp",
        "input_busqueda": "input[name='query'], input#query, input[type='text']",
        "btn_buscar": "input[type='submit'], button[type='submit'], input[value='Buscar']",
        "contenedor_resultados": "table, .resultados, .list-group, #resultados",
        "link_norma": "a[href*='Norma1.jsp'], a[href*='normas']",
        "sin_resultados": ".alert, :has-text('No se encontraron')",
        "wait_for": "input[name='query'], input[type='text']",
    },

    # ── Secretaría del Senado - Leyes colombianas ───────────────────────
    # URL: http://www.secretariasenado.gov.co/senado/basedoc/arbol/
    "senado_leyes": {
        "url": "http://www.secretariasenado.gov.co/senado/basedoc/arbol/9205.html",
        "url_busqueda": "http://www.secretariasenado.gov.co/senado/basedoc/busqueda_avanzada.html",
        "input_busqueda": "input[name='txtBuscar'], input#txtBuscar, input[type='text']",
        "btn_buscar": "input[type='submit'], button[type='submit'], input[value='Buscar']",
        "contenedor_resultados": "table, .resultados, #resultados, .list-group",
        "link_ley": "a[href*='ley_'], a[href*='decreto_'], a[href*='basedoc']",
        "sin_resultados": ".alert, :has-text('No se encontraron')",
        "wait_for": "input[type='text']",
    },
}
