# RESPUESTA A DERECHO DE PETICIÓN

**Señor(a)**
**{{nombre_peticionario | upper}}**
{{ciudad_peticionario if ciudad_peticionario else 'E. S. D.'}}

**Asunto:** Respuesta a Derecho de Petición - {{asunto}}
**Entidad/Persona que Responde:** {{nombre_entidad}}

---

Cordial saludo,

Por medio de la presente, y en ejercicio del derecho fundamental consagrado en el **Artículo 23 de la Constitución Política de Colombia** y reglamentado por la **Ley 1755 de 2015**, procedemos a dar respuesta formal, de fondo, clara y precisa a la solicitud de petición radicada por usted ante nuestra oficina, bajo las siguientes consideraciones:

## I. CONSIDERACIONES Y RESPUESTA DE FONDO

En atención a su solicitud y tras el estudio del caso, le informamos de manera congruente y resolutiva lo siguiente:

{{respuesta_cuerpo}}

## II. DOCUMENTOS ANEXOS

Para su constancia y como soporte de nuestra respuesta, anexamos los siguientes documentos a esta comunicación:

{% if documentos_anexos %}
{% for anexo in documentos_anexos %}
* {{anexo}}
{% endfor %}
{% else %}
* Ninguno.
{% endif %}

Agradecemos su atención y quedamos a su entera disposición en los canales oficiales de contacto.

Atentamente,

**{{nombre_entidad}}**
Cargo / Representante Legal
{{nombre_entidad_juridica if nombre_entidad_juridica else ''}}
Presentado en la ciudad de **{{ciudad}}**, a los {{ fecha_actual | fecha_larga if fecha_actual else 'días correspondientes' }}.
