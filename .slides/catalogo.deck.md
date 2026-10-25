---
deck: Catálogo de productos CIPSA — diseño, puertas y números
audience: Dirección y negocio. Ya conocen y usan las apps que consumen el catálogo; no conocen su mecanismo. Necesitan salir sabiendo por qué lo publicado es confiable y qué decidir sobre las fases siguientes.
register: read
structure: apertura y cierre en tinta (portada y statement final) con la evidencia central sobre papel
motif: chip de fuente — la etiqueta ERP/KARDEX/SKU_BX/S1 que marca de dónde sale cada dato, repetida donde se nombra un dato
---

## Slide 1
layout: title
Brief: Presenta el sujeto y la promesa del deck. Forma: portada en tinta, abre el sándwich oscuro; una portada no necesita argumento, necesita nombre. La mirada va al título. Referencia: portada del manual CIPSA-OrderX.
Canvas: ink
Title: Catálogo de productos CIPSA
Subtitle: Diseño, puertas y números: por qué las apps venden datos correctos
Notes: Versión del catálogo: 3553 SKUs, octubre 2026.

## Slide 2
layout: composed
Title: Todas las apps leen el mismo archivo
Brief: Terreno común: nombrar las apps que el público ya reconoce y el único archivo que las alimenta. Forma: icon-list porque son hermanos sin jerarquía — un inventario, no un argumento. La mirada va de los iconos al título. Referencia: señalética de aeropuerto, un destino con muchas puertas.
Block: icon-list
money | App de pedidos
data | Stock y almacén
cost | Precios y auditoría
growth | Reportes gerenciales
Notes: Un solo JSON publicado por master-data alimenta las apps: mismo precio y misma familia en cada app.

## Slide 3
layout: composed
Title: Sin reglas, el mismo producto tiene dos precios
Brief: El riesgo en su consecuencia real: una respuesta distinta por app es un error que llega al cliente. Forma: comparison que resuelve — el contraste es el argumento y el lado bueno gana. La mirada cae en el panel marcado. Referencia: etiqueta de ingredientes contra una nota manuscrita.
Block: comparison
Sin fuente única | Dos apps responden distinto para el mismo SKU; nadie sabe cuál es el correcto
!Con catálogo único | Una sola respuesta por SKU, y lo que no cuadra se frena antes de publicar
Notes: Las reglas hacen previsible al archivo. Las próximas láminas muestran cómo se aplican.

## Slide 4
layout: composed
Title: Cada dato sale de una fuente con oficio
Brief: La arquitectura completa en un vistazo: cuatro fuentes con oficios, un catálogo, un API, las apps. Forma: freeform porque es un diagrama de flujo — no hay primitiva nombrada para zonas con oficio y flechas. La mirada va de izquierda a derecha hasta el catálogo, el único bloque en acento. Referencia: plano de planta con zonas de trabajo.
Block: freeform
panel accent at cols 1-3 rows 3-4
text body ink at cols 3-6 rows 3-4 | ERP: precio, peso, EAN
arrow ink at cols 6-7 rows 3-4
panel accent at cols 1-3 rows 5-6
text body ink at cols 3-6 rows 5-6 | KARDEX: jerarquía y UM
arrow ink at cols 6-7 rows 5-6
panel accent at cols 1-3 rows 7-8
text body ink at cols 3-6 rows 7-8 | SKU_BX: guía y cajas
arrow ink at cols 6-7 rows 7-8
panel accent at cols 1-3 rows 9-10
text body ink at cols 3-6 rows 9-10 | S1: stock y compromiso
arrow ink at cols 6-7 rows 9-10
panel accent at cols 7-10 rows 3-10
text h1 paper at cols 7-10 rows 5-7 | Catálogo: 3553 SKUs con reglas
arrow ink at cols 11-12 rows 6-7
panel paper outline ink at cols 11-12 rows 4-7
text body ink at cols 11-12 rows 4-7 | API de stock · Apps CIPSA
Notes: Cada fuente manda solo en lo suyo: si un dato está mal, se corrige en su fuente y el JSON se regenera completo en cada corrida. El catálogo se regenera completo en cada corrida.

## Slide 5
layout: composed
Title: Nada entra al catálogo sin una razón
Brief: La regla de inclusión como contrato público: exactamente cuatro puertas de entrada. Forma: card-grid de cuatro hermanas — son condiciones de igual peso, no una lista. La mirada recorre las tarjetas y cierra en la cuarta. Referencia: checklist de embarque.
Block: card-grid
En la guía | SKU_BX: lo que se vende y se cura a mano
Con stock | al menos 1 unidad física en almacén
Con compromiso | pedidos pendientes de despacho
!Vigente con precio | alta en el ERP; lo descontinuado no entra por esta vía
Notes: La regla está publicada en el metadata del propio JSON: cualquier consumidor puede verificar por qué un SKU está ahí, sin leer código.

## Slide 6
layout: composed
Title: Cinco puertas frenan una publicación errónea
Brief: El proceso de publicación y qué frena cada etapa. Forma: process secuencial — el orden ES el mensaje: nada sube sin pasar todo. La mirada sigue las flechas de izquierda a derecha. Referencia: secuencia de arranque de cohete.
Block: process
Paso 0: contratos | Cada fuente se lee por nombre de columna; fuente rota, no se genera
Generación | Reglas de inclusión, SKUs exactos, sin adivinar
Taxonomía cruzada | master-data y stock-api clasifican igual cada línea
212 pruebas | Regresión automática antes de cualquier subida
Upload | Solo si todo quedó en verde
Notes: Los gates no son revisión manual: frenan solos. Si el universo de stock cae 15% contra la corrida anterior, la subida no sale.

## Slide 7
layout: composed
Title: 3553 productos publicados y verificados
Brief: Los números que sostienen la confianza. Forma: stat-row porque cada cifra es autónoma y se lee de un vistazo — cuatro números, cuatro pruebas distintas. La mirada salta de mayor a menor. Referencia: panel de control de sala de máquinas.
Block: stat-row
2265 | SKUs con stock o compromiso
99.8% | Jerarquía con código de 2 chars
0 | Líneas con categorías mixtas
212 | Pruebas automáticas en verde
Notes: Cobertura del universo de stock incluida; los SKUs sin código de jerarquía quedan vacíos y contados, nunca inventados.

## Slide 8
layout: composed
Title: Parecido no es igual: 03077 y 03077D
Brief: El caso concreto que prueba la regla de SKU exacto. Forma: comparison de dos fichas vecinas — el contraste es toda la historia y el lado que resuelve gana. La mirada va de un código al otro. Referencia: dos sets de fichas con códigos casi idénticos.
Block: comparison
03077 · línea 78 ARCHIVO | Fólder con precio S/ 4.17: se publica y se cotiza
!03077D · línea 98 SIN EMBALAJE | Misma cara visual, sin precio: publicado como lo que es, marcado por_activar, no cotiza
Notes: El sistema nunca fusiona por parecido ni sugiere similares: o el código existe o el campo queda vacío. 016763 y 16763 son dos artículos distintos.

## Slide 9
layout: composed
Title: Todo lo que se publicó queda registrado
Brief: La trazabilidad como respaldo del auditor. Forma: table de valores exactos — el lector quiere mirar qué se guarda y encontrarlo, no una forma. La mirada va directo a la fila marcada. Referencia: bitácora de vuelo.
Block: table
Registro | Ejemplo | Cuándo
Huella sha256 por fuente | PRODUCTOS.xls 2dbbbf8b | cada corrida
Exclusiones con motivo | 6538 filas en línea de proceso | cada corrida
!Universo vs corrida anterior | caída ≥15% frena la subida | antes de subir
Backup del JSON anterior | .bak con fecha por corrida | cada corrida
Auditoría KARDEX vs ERP | 11 divergencias visibles | paso 0
Notes: Si alguien pregunta por qué un SKU no está, la respuesta está en el JSON: exclusiones con motivo, cobertura publicada y faltantes en cero.

## Slide 10
layout: composed
Title: Lo que sigue: medidas de caja y precios
Brief: El rol de la audiencia: qué falta para completar la cadena. Forma: timeline de tres hitos porque es una secuencia con futuro, no una lista de deseos. La mirada queda en el hito marcado, el único que depende de una decisión. Referencia: hoja de ruta de obras.
Block: timeline
Hoy | 3553 SKUs en producción, 8 almacenes, subida verificada
!Medidas de caja | Cargar LARGO × ANCHO × ALTO en SKU_BX: el generador ya calcula m³
Precios | plantilla_precios.xlsx entra con descuentos y precios fijos
Notes: El pipeline de m³ ya está escrito y probado; solo faltan las medidas físicas en el archivo de la guía. La plantilla de precios ya se lee como informativa.

## Slide 11
layout: statement
Brief: La frase que se lleva el lector, bookend de la portada. Forma: statement en tinta, cierra el sándwich — una sola idea, sin adornos. La mirada va a la línea entera. Referencia: última página de un informe anual.
Canvas: ink
Statement: Una fuente, cinco puertas: lo que cambia, se frena antes de publicar.
Notes: El catálogo no se audita con fe: cada corrida deja números, exclusiones y prueba en verde. Con una sola fuente, la decisión de negocio se apoya en datos que coinciden en todas las apps.
