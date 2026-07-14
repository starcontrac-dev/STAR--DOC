# ACCIÓN DE TUTELA

Señor  
**JUEZ {{juez_y_ciudad}} (REPARTO)**  
E. S. D.  

**Referencia:** Acción de Tutela para la protección de derechos fundamentales.  
**Accionante:** **{{nombre_accionante}}**  
{% if es_menor %}(En representación de **{{nombre_menor}}**){% endif %}  
**Accionado:** **{{nombre_accionado}}**  

---

{% if es_menor %}
Yo, **{{nombre_accionante}}**, mayor de edad, con domicilio en la ciudad de **{{ciudad_accionante}}**, identificado con **{{tipo_documento_accionante}}** número **{{numero_documento_accionante}}**, actuando en mi calidad de representante legal del menor de edad **{{nombre_menor}}**,
{% else %}
Yo, **{{nombre_accionante}}**, mayor de edad, con domicilio en la ciudad de **{{ciudad_accionante}}**, identificado con **{{tipo_documento_accionante}}** número **{{numero_documento_accionante}}**, actuando en nombre propio,
{% endif %}
con el debido respeto comparezco ante usted para interponer **ACCIÓN DE TUTELA** en contra de **{{nombre_accionado}}**, con el objeto de que se tutelen y protejan de forma inmediata los derechos constitucionales fundamentales que considero vulnerados, con fundamento en los siguientes hechos y consideraciones de derecho:

---

### **I. DERECHOS FUNDAMENTALES VULNERADOS**
Invoco la protección del derecho fundamental a **{{derecho_fundamental_vulnerado}}**, consagrado en el artículo **{{articulo_constitucion}}** de la Constitución Política de Colombia, así como los demás derechos fundamentales conexos que se desprendan de la presente solicitud.

### **II. HECHOS Y OMISIONES**
Sirven de fundamento a la presente Acción de Tutela los siguientes hechos de relevancia jurídica:

{{descripcion_de_los_hechos}}

*   **Fecha de ocurrencia o persistencia de los hechos:** **{{fecha_hechos|fecha_larga}}**

{% if medida_provisional %}
### **III. SOLICITUD DE MEDIDA PROVISIONAL (Art. 7 Decreto 2591/91)**
De conformidad con el artículo 7º del Decreto 2591 de 1991, de manera expresa solicito al Señor Juez decretar una medida provisional de urgencia para evitar la consumación de un perjuicio irremediable. Solicito se ordene a **{{nombre_accionado}}** proceder a realizar la siguiente actuación de carácter prioritario: **{{actuacion_medida_provisional}}**, mientras se surte el trámite y se dicta el fallo definitivo de esta acción de tutela.
{% endif %}

### **IV. PROCEDIBILIDAD Y SUBSIDIARIEDAD**
La presente acción constitucional es procedente por cumplir con los requisitos constitucionales:
*   **Legitimación en la Causa:** El accionante está legitimado por activa al ser el titular directo de los derechos fundamentales conculcados (o su representante legal en caso del menor). El accionado es un particular/entidad pública respecto del cual el accionante se encuentra en estado de subordinación o indefensión (o que presta un servicio público esencial).
*   **Inmediatez:** Se acude a la tutela dentro de un término razonable y proporcional posterior a la vulneración de los derechos fundamentales.
*   **Subsidiariedad:** El accionante no cuenta con otro mecanismo de defensa judicial ordinario idóneo y eficaz para conjurar de forma oportuna e inmediata la vulneración de los derechos aquí invocados, lo que expone al afectado a un perjuicio irremediable.

### **V. PRETENSIONES**
Con base en los hechos expuestos, solicito respetuosamente al Señor Juez proferir las siguientes órdenes:
1.  Declarar que **{{nombre_accionado}}** vulneró el derecho fundamental a **{{derecho_fundamental_vulnerado}}** de la parte accionante.
2.  Tutelar el derecho fundamental invocado y, en consecuencia, ordenar a **{{nombre_accionado}}** que en un término perentorio no mayor a cuarenta y ocho (48) horas proceda a: **{{peticion_concreta}}**.
{% if pretension_economica %}
3.  Estimación del perjuicio económico en conexidad: se tasa en la suma de **{{pretension_economica|currency_cop}}**.
{% endif %}
4.  Realizar las demás declaraciones y condenas que el Señor Juez estime conducentes para restablecer el orden constitucional vulnerado.

### **VI. PRUEBAS**
Solicito tener como pruebas documentales los siguientes soportes anexos al presente escrito:
1.  Copia del documento de identidad del accionante (y del menor de edad, si aplica).
2.  Copia de la petición o solicitud radicada ante la accionada el día **{{fecha_peticion_previa}}**.
3.  Copia de la respuesta de la accionada (si la hubiere) o constancia del silencio administrativo.
4.  Demás soportes médicos, técnicos o facturas que acreditan la vulneración del derecho: **{{descripcion_pruebas_anexas}}**.

### **VII. JURAMENTO (Art. 37 Decreto 2591/91)**
Bajo la gravedad del juramento, el cual se entiende prestado con la firma de este escrito, manifiesto que no he interpuesto otra acción de tutela ante ninguna corporación o despacho judicial por los mismos hechos y derechos aquí relatados.

### **VIII. NOTIFICACIONES**
*   La parte Accionante recibirá notificaciones en la dirección física **{{direccion_notificacion_accionante}}** de la ciudad de **{{ciudad_accionante}}**, o en la dirección de correo electrónico **{{email_accionante}}**.
*   La parte Accionada recibirá notificaciones en la dirección física **{{direccion_notificacion_accionado}}**, o en la dirección de correo electrónico registrada para notificaciones judiciales.

---

Atentamente,  

<br><br>

__________________________________________________  
**{{nombre_accionante}}**  
CC. No. **{{numero_documento_accionante}}**  
Accionante  
