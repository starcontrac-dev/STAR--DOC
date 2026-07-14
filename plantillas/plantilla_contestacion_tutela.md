# CONTESTACIÓN DE ACCIÓN DE TUTELA

**Señor**
**{{juzgado | upper}}**
**E. S. D.**

**Referencia:** Contestación de Acción de Tutela
**Radicado:** {{radicado}}
**Accionante:** {{nombre_accionante}}
**Accionado:** {{nombre_accionado}}

---

**{{nombre_accionado}}**, mayor de edad, identificado como se indica al pie de mi firma, actuando en calidad de representante legal / apoderado judicial de la entidad accionada, con el debido respeto me dirijo a su Despacho con el fin de pronunciarme y dar contestación formal a la Acción de Tutela de la referencia, con fundamento en los siguientes argumentos de hecho y de derecho:

## I. PRONUNCIAMIENTO SOBRE LOS HECHOS DE LA DEMANDA

Respecto de los hechos narrados por la parte accionante en su escrito de tutela, nos pronunciamos de la siguiente manera:

{% for hecho in pronunciamiento_hechos %}
* **{{hecho}}**
{% endfor %}

## II. RAZONES DE LA DEFENSA

Su Señoría, solicitamos desestimar las pretensiones de la acción de tutela con base en las siguientes consideraciones jurídicas:

{{razones_defensa}}

## III. PRUEBAS

Con el objeto de sustentar la defensa y desvirtuar la supuesta vulneración de derechos fundamentales, aportamos y solicitamos tener como pruebas los siguientes documentos:

{% for prueba in pruebas %}
* {{prueba}}
{% endfor %}

## IV. SOLICITUD AL DESPACHO (PETICIONES)

Con fundamento en los hechos y las razones de derecho expuestas en este escrito, solicito muy respetuosamente a su Despacho:

* **{{solicitud_juez}}**

## V. NOTIFICACIONES

Recibiré notificaciones en la dirección física y electrónica registrada en la plataforma STAR-DOC.

Presentado en la ciudad de **{{ciudad}}**, a los {{ fecha_actual | fecha_larga if fecha_actual else 'días correspondientes' }}.

Atentamente,

_____________________________
**{{nombre_accionado}}**
Representante Legal / Accionado
