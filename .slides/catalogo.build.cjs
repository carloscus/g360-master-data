/*
 * catalogo.build.cjs - compone el deck "Catálogo de productos CIPSA"
 * desde .slides/catalogo.deck.md bajo los tokens de .slides/tokens.cjs.
 *
 * Reglas del contrato: todo texto vive en el bloque C (contenido = datos);
 * todo color/tamaño/tipografía sale de T.*; cada caja de texto lleva su
 * stamp (slides-lead una por slide, slides-field lo demás, deco-* lo
 * dibujado); las notas viajan verbatim.
 *
 *   node catalogo.build.cjs --tokens .slides/tokens.cjs --out .slides/catalogo.pptx
 */

const argv = process.argv.slice(2);

function arg(name) {
  const i = argv.indexOf(name);
  return i >= 0 && i + 1 < argv.length ? argv[i + 1] : null;
}

const tokensPath = arg("--tokens");
const outPath = arg("--out");

if (!tokensPath || !outPath) {
  console.error("usage: node catalogo.build.cjs --tokens <tokens.cjs> --out <deck.pptx>");
  process.exit(2);
}

const T = require(require("path").resolve(tokensPath));
const pptxgen = T.loadPptxgen();

// Todo el contenido del deck en un solo bloque de datos.
const C = JSON.parse(`{
  "s1": {
    "title": "Catálogo de productos CIPSA",
    "subtitle": "Diseño, puertas y números: por qué las apps venden datos correctos",
    "notes": "Versión del catálogo: 3553 SKUs, octubre 2026."
  },
  "s2": {
    "title": "Todas las apps leen el mismo archivo",
    "app1": "App de pedidos",
    "app2": "Stock y almacén",
    "app3": "Precios y auditoría",
    "app4": "Reportes gerenciales",
    "file": "output/catalogo_productos.json  ·  3553 SKUs",
    "notes": "Un solo JSON publicado por master-data alimenta las apps: mismo precio y misma familia en cada app."
  },
  "s3": {
    "title": "Sin reglas, el mismo producto tiene dos precios",
    "leftHeader": "Sin fuente única",
    "left": "Dos apps responden distinto para el mismo SKU; nadie sabe cuál es el correcto",
    "rightHeader": "Con catálogo único",
    "right": "Una sola respuesta por SKU, y lo que no cuadra se frena antes de publicar",
    "conflict": "conflicto",
    "notes": "Las reglas hacen previsible al archivo. Las próximas láminas muestran cómo se aplican."
  },
  "s4": {
    "title": "Cada dato sale de una fuente con oficio",
    "erp": "ERP",
    "erpDetail": "precio, peso, EAN",
    "kardex": "KARDEX",
    "kardexDetail": "jerarquía y UM",
    "skuBx": "SKU_BX",
    "skuBxDet": "guía y cajas",
    "s1": "S1",
    "s1Detail": "stock y compromiso",
    "catalogo": "Catálogo",
    "catalogoSub": "3553 SKUs con reglas",
    "api": "API de stock",
    "apps": "Apps CIPSA",
    "notes": "Cada fuente manda solo en lo suyo: si un dato está mal, se corrige en su fuente y el JSON se regenera completo en cada corrida. El catálogo se regenera completo en cada corrida."
  },
  "s5": {
    "title": "Nada entra al catálogo sin una razón",
    "c1src": "SKU_BX",
    "c1label": "En la guía",
    "c1body": "Lo que se vende y se cura a mano",
    "c2src": "S1",
    "c2label": "Con stock",
    "c2body": "Al menos 1 unidad física en almacén",
    "c3src": "S1",
    "c3label": "Con compromiso",
    "c3body": "Pedidos pendientes de despacho",
    "c4src": "ERP",
    "c4label": "Vigente con precio",
    "c4body": "Alta en el ERP; lo descontinuado no entra por esta vía",
    "notes": "La regla está publicada en el metadata del propio JSON: cualquier consumidor puede verificar por qué un SKU está ahí, sin leer código."
  },
  "s6": {
    "title": "Cinco puertas frenan una publicación errónea",
    "st1": "Paso 0: contratos",
    "d1": "Cada fuente se lee por nombre de columna; fuente rota, no se genera",
    "st2": "Generación",
    "d2": "Reglas de inclusión, SKUs exactos, sin adivinar",
    "st3": "Taxonomía cruzada",
    "d3": "master-data y stock-api clasifican igual cada línea",
    "st4": "212 pruebas",
    "d4": "Regresión automática antes de cualquier subida",
    "st5": "Upload",
    "d5": "Solo si todo quedó en verde",
    "notes": "Los gates no son revisión manual: frenan solos. Si el universo de stock cae 15% contra la corrida anterior, la subida no sale."
  },
  "s7": {
    "title": "3553 productos publicados y verificados",
    "v1": "2265",
    "l1": "SKUs con stock o compromiso",
    "v2": "99.8%",
    "l2": "Jerarquía con código de 2 chars",
    "v3": "0",
    "l3": "Líneas con categorías mixtas",
    "v4": "212",
    "l4": "Pruebas automáticas en verde",
    "notes": "Cobertura del universo de stock incluida; los SKUs sin código de jerarquía quedan vacíos y contados, nunca inventados."
  },
  "s8": {
    "title": "Parecido no es igual: 03077 y 03077D",
    "leftChip": "ERP",
    "leftCode": "03077",
    "leftSub": "línea 78 · ARCHIVO",
    "left": "Fólder con precio S/ 4.17: se publica y se cotiza",
    "rightChip": "S1",
    "rightCode": "03077D",
    "rightSub": "línea 98 · SIN EMBALAJE",
    "right": ["Misma cara visual, sin precio:", "publicado como lo que es,", "marcado por_activar, no cotiza"],
    "notes": "El sistema nunca fusiona por parecido ni sugiere similares: o el código existe o el campo queda vacío. 016763 y 16763 son dos artículos distintos."
  },
  "s9": {
    "title": "Todo lo que se publicó queda registrado",
    "h1": "Registro",
    "h2": "Ejemplo",
    "h3": "Cuándo",
    "r1a": "Huella sha256 por fuente",
    "r1b": "PRODUCTOS.xls 2dbbbf8b",
    "r1c": "cada corrida",
    "r2a": "Exclusiones con motivo",
    "r2b": "6538 filas en línea de proceso",
    "r2c": "cada corrida",
    "r3a": "Universo vs corrida anterior",
    "r3b": "caída ≥15% frena la subida",
    "r3c": "antes de subir",
    "r4a": "Backup del JSON anterior",
    "r4b": ".bak con fecha por corrida",
    "r4c": "cada corrida",
    "r5a": "Auditoría KARDEX vs ERP",
    "r5b": "11 divergencias visibles",
    "r5c": "paso 0",
    "notes": "Si alguien pregunta por qué un SKU no está, la respuesta está en el JSON: exclusiones con motivo, cobertura publicada y faltantes en cero."
  },
  "s10": {
    "title": "Lo que sigue: medidas de caja y precios",
    "t1": "Hoy",
    "e1": "3553 SKUs en producción, 8 almacenes, subida verificada",
    "t2": "Medidas de caja",
    "e2": "Cargar LARGO × ANCHO × ALTO en SKU_BX: el generador ya calcula m³",
    "t3": "Precios",
    "e3": "plantilla_precios.xlsx entra con descuentos y precios fijos",
    "notes": "El pipeline de m³ ya está escrito y probado; solo faltan las medidas físicas en el archivo de la guía. La plantilla de precios ya se lee como informativa."
  },
  "s11": {
    "statement": ["Una fuente, cinco puertas:", "lo que cambia, se frena antes de publicar."],
    "notes": "El catálogo no se audita con fe: cada corrida deja números, exclusiones y prueba en verde. Con una sola fuente, la decisión de negocio se apoya en datos que coinciden en todas las apps."
  }
}`);

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";

const W = T.slide.w;
const H = T.slide.h;
const MX = T.margins.x;
const MT = T.margins.top;
const MB = H - T.margins.bottom;
const CW = W - 2 * MX;
const ROUNDED = T.shape.corner === "rounded";
// Marca del deck en el token de acento (colour_roles): nada fuera de tokens.
const MARK = T.colours.accent;

function text(slide, body, opts) {
  slide.addText(body, Object.assign({ margin: 0 }, opts));
}

function mark(slide, kind, opts) {
  slide.addShape(kind, Object.assign({}, opts));
}

function panel(slide, opts) {
  const o = Object.assign({}, opts);
  if (ROUNDED) {
    o.rectRadius = 0.1;
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, o);
  } else {
    slide.addShape(pres.shapes.RECTANGLE, o);
  }
}

// Gris sobre papel que sigue siendo de marca: ink adelgazado.
function tint(colour, transparency) {
  return { color: colour, transparency: transparency };
}

function chip(slide, label, x, y, w, opts) {
  opts = opts || {};
  const dark = opts.dark !== false;
  panel(slide, {
    x: x, y: y, w: w, h: 0.4,
    fill: dark ? { color: T.colours.accent } : { color: T.colours.paper },
    line: dark ? { color: T.colours.accent } : { color: T.colours.accent, width: 1.25 },
    objectName: "deco-chip-" + label,
  });
  text(slide, label, {
    x: x, y: y, w: w, h: 0.4,
    fontFace: T.fonts.heading, fontSize: T.scale.caption, bold: true,
    color: dark ? T.colours.paper : T.colours.accent,
    align: "center", valign: "middle",
    objectName: "deco-chip-label-" + label,
  });
}

// ------------------------------------------------------------ 1. portada ---
{
  const s = pres.addSlide();
  s.background = { color: T.colours.ink };

  mark(s, pres.shapes.LINE, {
    x: MX, y: 1.75, w: 1.7, h: 0,
    line: { color: T.colours.muted, width: 3 },
    objectName: "deco-rule-accent",
  });
  text(s, C.s1.title, {
    x: MX, y: 2.15, w: 10.6, h: 2.5,
    fontFace: T.fonts.heading, fontSize: T.scale.title, bold: true,
    color: T.colours.paper, valign: "bottom", lineSpacingMultiple: 0.98,
    objectName: "slides-lead:Title",
  });
  text(s, C.s1.subtitle, {
    x: MX, y: 4.95, w: 10.6, h: 0.9,
    fontFace: T.fonts.body, fontSize: T.scale.body,
    color: T.colours.muted, objectName: "slides-field:Subtitle",
  });
  s.addNotes(C.s1.notes);
}

// --------------------------------------------------------- 2. terreno común --
{
  const s = pres.addSlide();
  s.background = { color: T.colours.paper };

  text(s, C.s2.title, {
    x: MX, y: MT, w: 11.4, h: 1.0,
    fontFace: T.fonts.heading, fontSize: T.scale.h1, bold: true,
    color: T.colours.ink, valign: "top", objectName: "slides-lead:Title",
  });

  const apps = [C.s2.app1, C.s2.app2, C.s2.app3, C.s2.app4];
  const gap = 0.3;
  const cw = (CW - 3 * gap) / 4;
  const cy = 2.1;
  const ch = 2.9;
  apps.forEach((app, i) => {
    const cx = MX + i * (cw + gap);
    panel(s, {
      x: cx, y: cy, w: cw, h: ch,
      fill: tint(T.colours.ink, 94), line: tint(T.colours.ink, 100),
      objectName: "deco-app-card-" + (i + 1),
    });
    mark(s, pres.shapes.OVAL, {
      x: cx + 0.3, y: cy + 0.36, w: 0.18, h: 0.18,
      fill: { color: T.colours.accent }, line: { color: T.colours.accent },
      objectName: "deco-app-dot-" + (i + 1),
    });
    text(s, app, {
      x: cx + 0.62, y: cy + 0.24, w: cw - 0.9, h: 0.5,
      fontFace: T.fonts.body, fontSize: T.scale.body, bold: true,
      color: T.colours.ink, objectName: "slides-field:Body",
    });
    mark(s, pres.shapes.LINE, {
      x: cx + cw / 2, y: cy + ch, w: 0, h: 0.6,
      line: { color: T.colours.ink, width: 1.5, transparency: 70 },
      objectName: "deco-feed-line-" + (i + 1),
    });
  });

  const fw = 8.4;
  const fx = MX + (CW - fw) / 2;
  panel(s, {
    x: fx, y: 5.75, w: fw, h: 0.95,
    fill: { color: T.colours.accent }, line: { color: T.colours.accent },
    objectName: "deco-file-chip",
  });
  text(s, C.s2.file, {
    x: fx, y: 5.75, w: fw, h: 0.95,
    fontFace: T.fonts.heading, fontSize: T.scale.body, bold: true,
    color: T.colours.paper, align: "center", valign: "middle",
    objectName: "slides-field:Body",
  });
  s.addNotes(C.s2.notes);
}

// ------------------------------------------------------------- 3. el riesgo --
{
  const s = pres.addSlide();
  s.background = { color: T.colours.paper };

  text(s, C.s3.title, {
    x: MX, y: MT, w: 11.4, h: 1.0,
    fontFace: T.fonts.heading, fontSize: T.scale.h1, bold: true,
    color: T.colours.ink, valign: "top", objectName: "slides-lead:Title",
  });

  const gap = 0.55;
  const pw = (CW - gap) / 2;
  const py = 2.0;
  const ph = 4.5;
  const pad = 0.45;

  panel(s, {
    x: MX, y: py, w: pw, h: ph,
    fill: tint(T.colours.ink, 94), line: tint(T.colours.ink, 100),
    objectName: "deco-panel-sin-fuente",
  });
  mark(s, pres.shapes.OVAL, {
    x: MX + pad, y: py + 0.52, w: 0.18, h: 0.18,
    fill: { color: MARK }, line: { color: MARK },
    objectName: "deco-conflict-dot",
  });
  text(s, C.s3.conflict, {
    x: MX + pad + 0.3, y: py + 0.4, w: pw - 2 * pad, h: 0.45,
    fontFace: T.fonts.body, fontSize: T.scale.caption, bold: true,
    color: MARK, objectName: "deco-conflict-label",
  });
  text(s, C.s3.leftHeader, {
    x: MX + pad, y: py + 1.0, w: pw - 2 * pad, h: 0.6,
    fontFace: T.fonts.heading, fontSize: T.scale.body, bold: true,
    color: T.colours.ink, objectName: "slides-field:Left",
  });
  text(s, C.s3.left, {
    x: MX + pad, y: py + 1.8, w: pw - 2 * pad, h: 2.3,
    fontFace: T.fonts.body, fontSize: T.scale.body,
    color: T.colours.ink, valign: "top", objectName: "slides-field:Body",
  });

  const rx = MX + pw + gap;
  panel(s, {
    x: rx, y: py, w: pw, h: ph,
    fill: { color: T.colours.accent }, line: { color: T.colours.accent },
    objectName: "deco-panel-catalogo",
  });
  text(s, C.s3.rightHeader, {
    x: rx + pad, y: py + 1.0, w: pw - 2 * pad, h: 0.6,
    fontFace: T.fonts.heading, fontSize: T.scale.body, bold: true,
    color: T.colours.paper, objectName: "slides-field:Right",
  });
  text(s, C.s3.right, {
    x: rx + pad, y: py + 1.8, w: pw - 2 * pad, h: 2.3,
    fontFace: T.fonts.body, fontSize: T.scale.body,
    color: T.colours.paper, valign: "top", objectName: "slides-field:Body",
  });
  s.addNotes(C.s3.notes);
}

// ------------------------------------------------------- 4. arquitectura ----
{
  const s = pres.addSlide();
  s.background = { color: T.colours.paper };

  text(s, C.s4.title, {
    x: MX, y: MT, w: 11.4, h: 1.0,
    fontFace: T.fonts.heading, fontSize: T.scale.h1, bold: true,
    color: T.colours.ink, valign: "top", objectName: "slides-lead:Title",
  });

  // Izquierda: los cuatro chips de fuente con su oficio.
  const rows = [
    { label: C.s4.erp, detail: C.s4.erpDetail, w: 1.0 },
    { label: C.s4.kardex, detail: C.s4.kardexDetail, w: 1.55 },
    { label: C.s4.skuBx, detail: C.s4.skuBxDet, w: 1.6 },
    { label: C.s4.s1, detail: C.s4.s1Detail, w: 0.95 },
  ];
  const srcY = [1.9, 3.15, 4.4, 5.65];
  rows.forEach((r, i) => {
    chip(s, r.label, MX, srcY[i], r.w);
    text(s, r.detail, {
      x: MX + r.w + 0.25, y: srcY[i] - 0.02, w: 3.0, h: 0.5,
      fontFace: T.fonts.body, fontSize: T.scale.caption,
      color: T.colours.ink, valign: "middle",
      objectName: "slides-field:Body",
    });
    mark(s, pres.shapes.LINE, {
      x: 5.05, y: srcY[i] + 0.2, w: 0.55, h: 0,
      line: { color: T.colours.ink, width: 1.75, transparency: 55, endArrowType: "triangle" },
      objectName: "deco-arrow-src-" + (i + 1),
    });
  });

  // Centro: el catálogo, el único bloque en acento.
  panel(s, {
    x: 5.8, y: 1.9, w: 3.4, h: 4.7,
    fill: { color: T.colours.accent }, line: { color: T.colours.accent },
    objectName: "deco-catalogo",
  });
  text(s, [
    { text: C.s4.catalogo, options: { fontSize: T.scale.body, bold: true, breakLine: true } },
    { text: C.s4.catalogoSub, options: { fontSize: T.scale.caption } },
  ], {
    x: 5.9, y: 3.4, w: 3.2, h: 1.4,
    fontFace: T.fonts.heading,
    color: T.colours.paper, align: "center", valign: "middle",
    objectName: "slides-field:Body",
  });

  mark(s, pres.shapes.LINE, {
    x: 9.35, y: 4.25, w: 0.55, h: 0,
    line: { color: T.colours.ink, width: 1.75, transparency: 55, endArrowType: "triangle" },
    objectName: "deco-arrow-api",
  });
  panel(s, {
    x: 10.05, y: 3.0, w: 2.6, h: 2.5,
    fill: { color: T.colours.paper }, line: { color: T.colours.ink, width: 1.5 },
    objectName: "deco-salida",
  });
  text(s, [
    { text: C.s4.api, options: { fontSize: T.scale.body, bold: true, breakLine: true } },
    { text: "", options: { fontSize: T.scale.caption, breakLine: true } },
    { text: C.s4.apps, options: { fontSize: T.scale.body } },
  ], {
    x: 10.15, y: 3.0, w: 2.4, h: 2.5,
    fontFace: T.fonts.body,
    color: T.colours.ink, align: "center", valign: "middle",
    objectName: "slides-field:Body",
  });
  s.addNotes(C.s4.notes);
}

// ------------------------------------------------------ 5. regla de inclusión --
{
  const s = pres.addSlide();
  s.background = { color: T.colours.paper };

  text(s, C.s5.title, {
    x: MX, y: MT, w: 11.4, h: 1.0,
    fontFace: T.fonts.heading, fontSize: T.scale.h1, bold: true,
    color: T.colours.ink, valign: "top", objectName: "slides-lead:Title",
  });

  const cards = [
    { src: C.s5.c1src, label: C.s5.c1label, body: C.s5.c1body, hero: false },
    { src: C.s5.c2src, label: C.s5.c2label, body: C.s5.c2body, hero: false },
    { src: C.s5.c3src, label: C.s5.c3label, body: C.s5.c3body, hero: false },
    { src: C.s5.c4src, label: C.s5.c4label, body: C.s5.c4body, hero: true },
  ];
  const gapX = 0.5;
  const gapY = 0.45;
  const pw = (CW - gapX) / 2;
  const ph = 2.15;
  cards.forEach((c, i) => {
    const x = MX + (i % 2) * (pw + gapX);
    const y = 2.05 + Math.floor(i / 2) * (ph + gapY);
    panel(s, {
      x: x, y: y, w: pw, h: ph,
      fill: c.hero ? { color: T.colours.accent } : tint(T.colours.ink, 94),
      line: c.hero ? { color: T.colours.accent } : tint(T.colours.ink, 100),
      objectName: "deco-card-" + (i + 1),
    });
    chip(s, c.src, x + 0.4, y + 0.32, c.src.length > 3 ? 1.6 : 1.0, { dark: !c.hero });
    text(s, c.label, {
      x: x + 0.4, y: y + 0.85, w: pw - 0.8, h: 0.55,
      fontFace: T.fonts.heading, fontSize: T.scale.body, bold: true,
      color: c.hero ? T.colours.paper : T.colours.ink,
      objectName: "slides-field:Body",
    });
    text(s, c.body, {
      x: x + 0.4, y: y + 1.4, w: pw - 0.8, h: 0.65,
      fontFace: T.fonts.body, fontSize: T.scale.caption,
      color: c.hero ? T.colours.muted : T.colours.ink,
      objectName: "slides-field:Body",
    });
  });
  s.addNotes(C.s5.notes);
}

// -------------------------------------------------------------- 6. puertas --
{
  const s = pres.addSlide();
  s.background = { color: T.colours.paper };

  text(s, C.s6.title, {
    x: MX, y: MT, w: 11.4, h: 1.0,
    fontFace: T.fonts.heading, fontSize: T.scale.h1, bold: true,
    color: T.colours.ink, valign: "top", objectName: "slides-lead:Title",
  });

  const steps = [
    { label: C.s6.st1, detail: C.s6.d1, gate: false },
    { label: C.s6.st2, detail: C.s6.d2, gate: false },
    { label: C.s6.st3, detail: C.s6.d3, gate: false },
    { label: C.s6.st4, detail: C.s6.d4, gate: false },
    { label: C.s6.st5, detail: C.s6.d5, gate: true },
  ];
  const gap = 0.3;
  const bw = (CW - 4 * gap) / 5;
  const by = 2.3;
  const bh = 3.6;
  steps.forEach((st, i) => {
    const bx = MX + i * (bw + gap);
    panel(s, {
      x: bx, y: by, w: bw, h: bh,
      fill: st.gate ? { color: T.colours.paper } : tint(T.colours.ink, 94),
      line: st.gate ? { color: MARK, width: 2.25 } : tint(T.colours.ink, 100),
      objectName: "deco-step-" + (i + 1),
    });
    // Número y etiqueta en UNA caja (rich text): el cap de elementos.
    text(s, [
      { text: "0" + (i + 1), options: { fontSize: T.scale.caption, bold: true, color: MARK, breakLine: true } },
      { text: st.label, options: { fontSize: T.scale.body, bold: true, breakLine: true } },
      { text: st.detail, options: { fontSize: T.scale.caption } },
    ], {
      x: bx + 0.28, y: by + 0.26, w: bw - 0.56, h: bh - 0.52,
      fontFace: T.fonts.heading, color: T.colours.ink, valign: "top",
      objectName: "slides-field:Body",
    });
    if (i < 4) {
      mark(s, pres.shapes.LINE, {
        x: bx + bw + 0.04, y: by + bh / 2, w: gap - 0.08, h: 0,
        line: { color: T.colours.ink, width: 1.75, transparency: 55, endArrowType: "triangle" },
        objectName: "deco-arrow-step-" + (i + 1),
      });
    }
  });
  s.addNotes(C.s6.notes);
}

// ------------------------------------------------------------- 7. números ---
{
  const s = pres.addSlide();
  s.background = { color: T.colours.paper };

  text(s, C.s7.title, {
    x: MX, y: MT, w: 11.4, h: 1.0,
    fontFace: T.fonts.heading, fontSize: T.scale.h1, bold: true,
    color: T.colours.ink, valign: "top", objectName: "slides-field:Title",
  });

  const stats = [
    { v: C.s7.v1, l: C.s7.l1, hero: true },
    { v: C.s7.v2, l: C.s7.l2, hero: false },
    { v: C.s7.v3, l: C.s7.l3, hero: false },
    { v: C.s7.v4, l: C.s7.l4, hero: false },
  ];
  const colw = CW / 4;
  stats.forEach((st, i) => {
    const x = MX + i * colw;
    if (i > 0) {
      mark(s, pres.shapes.LINE, {
        x: x, y: 2.6, w: 0, h: 2.4,
        line: { color: T.colours.ink, width: 1, transparency: 85 },
        objectName: "deco-stat-rule-" + i,
      });
    }
    text(s, st.v, {
      x: x + 0.3, y: 2.7, w: colw - 0.5, h: 1.3,
      fontFace: T.fonts.heading, fontSize: st.hero ? T.scale.title : T.scale.h1,
      bold: true, color: st.hero ? T.colours.accent : T.colours.ink,
      valign: "middle",
      objectName: i === 0 ? "slides-lead" : "slides-field:Body",
    });
    text(s, st.l, {
      x: x + 0.3, y: 4.1, w: colw - 0.6, h: 1.2,
      fontFace: T.fonts.body, fontSize: T.scale.caption,
      color: T.colours.ink, valign: "top",
      objectName: "slides-field:Body",
    });
  });
  s.addNotes(C.s7.notes);
}

// -------------------------------------------------- 8. 03077 vs 03077D -----
{
  const s = pres.addSlide();
  s.background = { color: T.colours.paper };

  text(s, C.s8.title, {
    x: MX, y: MT, w: 11.6, h: 1.0,
    fontFace: T.fonts.heading, fontSize: T.scale.h1, bold: true,
    color: T.colours.ink, valign: "top", objectName: "slides-lead:Title",
  });

  const gap = 0.55;
  const pw = (CW - gap) / 2;
  const py = 2.0;
  const ph = 4.5;
  const pad = 0.45;

  panel(s, {
    x: MX, y: py, w: pw, h: ph,
    fill: tint(T.colours.ink, 94), line: tint(T.colours.ink, 100),
    objectName: "deco-ficha-03077",
  });
  chip(s, C.s8.leftChip, MX + pad, py + 0.4, 1.0, { dark: true });
  text(s, C.s8.leftCode, {
    x: MX + pad, y: py + 1.0, w: pw - 2 * pad, h: 1.0,
    fontFace: T.fonts.heading, fontSize: T.scale.body, bold: true,
    color: T.colours.ink, valign: "middle",
    objectName: "slides-field:Left",
  });
  text(s, C.s8.leftSub, {
    x: MX + pad, y: py + 2.05, w: pw - 2 * pad, h: 0.45,
    fontFace: T.fonts.body, fontSize: T.scale.caption,
    color: T.colours.accent, objectName: "slides-field:Body",
  });
  text(s, C.s8.left, {
    x: MX + pad, y: py + 2.65, w: pw - 2 * pad, h: 1.5,
    fontFace: T.fonts.body, fontSize: T.scale.body,
    color: T.colours.ink, valign: "top", objectName: "slides-field:Body",
  });

  const rx = MX + pw + gap;
  panel(s, {
    x: rx, y: py, w: pw, h: ph,
    fill: { color: T.colours.accent }, line: { color: T.colours.accent },
    objectName: "deco-ficha-03077d",
  });
  chip(s, C.s8.rightChip, rx + pad, py + 0.4, 0.95, { dark: false });
  text(s, C.s8.rightCode, {
    x: rx + pad, y: py + 1.0, w: pw - 2 * pad, h: 1.0,
    fontFace: T.fonts.heading, fontSize: T.scale.body, bold: true,
    color: T.colours.paper, valign: "middle",
    objectName: "slides-field:Right",
  });
  text(s, C.s8.rightSub, {
    x: rx + pad, y: py + 2.05, w: pw - 2 * pad, h: 0.45,
    fontFace: T.fonts.body, fontSize: T.scale.caption,
    color: T.colours.muted, objectName: "slides-field:Body",
  });
  text(s, C.s8.right.map((t, i, a) => ({ text: t, options: { breakLine: i < a.length - 1 } })), {
    x: rx + pad, y: py + 2.65, w: pw - 2 * pad, h: 1.6,
    fontFace: T.fonts.body, fontSize: T.scale.body,
    color: T.colours.paper, valign: "top", objectName: "slides-field:Body",
  });
  s.addNotes(C.s8.notes);
}

// ----------------------------------------------------------- 9. bitácora ----
{
  const s = pres.addSlide();
  s.background = { color: T.colours.paper };

  text(s, C.s9.title, {
    x: MX, y: MT, w: 11.4, h: 1.0,
    fontFace: T.fonts.heading, fontSize: T.scale.h1, bold: true,
    color: T.colours.ink, valign: "top", objectName: "slides-lead:Title",
  });

  const c1x = MX, c1w = 4.5;
  const c2x = MX + 4.7, c2w = 4.7;
  const c3x = MX + 9.6, c3w = 2.3;
  const hy = 1.95;
  const rh = 0.86;

  panel(s, {
    x: MX, y: hy, w: CW, h: 0.6,
    fill: { color: T.colours.accent }, line: { color: T.colours.accent },
    objectName: "deco-table-head",
  });
  [
    { x: c1x + 0.2, w: c1w, t: C.s9.h1 },
    { x: c2x, w: c2w, t: C.s9.h2 },
    { x: c3x, w: c3w, t: C.s9.h3 },
  ].forEach((h, i) => {
    text(s, h.t, {
      x: h.x, y: hy, w: h.w, h: 0.6,
      fontFace: T.fonts.body, fontSize: T.scale.caption, bold: true,
      color: T.colours.paper, valign: "middle",
      objectName: "slides-field:Body",
    });
  });

  const rows = [
    [C.s9.r1a, C.s9.r1b, C.s9.r1c],
    [C.s9.r2a, C.s9.r2b, C.s9.r2c],
    [C.s9.r3a, C.s9.r3b, C.s9.r3c],
    [C.s9.r4a, C.s9.r4b, C.s9.r4c],
    [C.s9.r5a, C.s9.r5b, C.s9.r5c],
  ];
  rows.forEach((r, i) => {
    const ry = hy + 0.6 + i * rh;
    const lead = i === 2;
    if (lead) {
      panel(s, {
        x: MX, y: ry, w: CW, h: rh,
        fill: { color: T.colours.accent }, line: { color: T.colours.accent },
        objectName: "deco-row-lead",
      });
    }
    const col = lead ? T.colours.paper : T.colours.ink;
    text(s, r[0], {
      x: c1x + 0.2, y: ry, w: c1w, h: rh,
      fontFace: T.fonts.body, fontSize: T.scale.caption, bold: lead,
      color: col, valign: "middle",
      objectName: "slides-field:Body",
    });
    text(s, r[1], {
      x: c2x, y: ry, w: c2w, h: rh,
      fontFace: T.fonts.body, fontSize: T.scale.caption,
      color: col, valign: "middle",
      objectName: "slides-field:Body",
    });
    text(s, r[2], {
      x: c3x, y: ry, w: c3w, h: rh,
      fontFace: T.fonts.body, fontSize: T.scale.caption,
      color: col, valign: "middle",
      objectName: "slides-field:Body",
    });
  });
  s.addNotes(C.s9.notes);
}

// ---------------------------------------------------------- 10. lo que sigue --
{
  const s = pres.addSlide();
  s.background = { color: T.colours.paper };

  text(s, C.s10.title, {
    x: MX, y: MT, w: 11.4, h: 1.0,
    fontFace: T.fonts.heading, fontSize: T.scale.h1, bold: true,
    color: T.colours.ink, valign: "top", objectName: "slides-lead:Title",
  });

  const railY = 4.1;
  mark(s, pres.shapes.LINE, {
    x: MX + 0.4, y: railY, w: CW - 0.8, h: 0,
    line: { color: T.colours.ink, width: 2, transparency: 70 },
    objectName: "deco-timeline-rail",
  });

  const hits = [
    { x: 2.55, t: C.s10.t1, e: C.s10.e1, turn: false },
    { x: 6.667, t: C.s10.t2, e: C.s10.e2, turn: true },
    { x: 10.75, t: C.s10.t3, e: C.s10.e3, turn: false },
  ];
  hits.forEach((m, i) => {
    const r = m.turn ? 0.17 : 0.11;
    mark(s, pres.shapes.OVAL, {
      x: m.x - r, y: railY - r, w: 2 * r, h: 2 * r,
      fill: m.turn ? { color: MARK } : { color: T.colours.accent },
      line: m.turn ? { color: MARK } : { color: T.colours.accent },
      objectName: "deco-milestone-" + (i + 1),
    });
    text(s, m.t, {
      x: m.x - 1.8, y: 3.15, w: 3.6, h: 0.6,
      fontFace: T.fonts.heading, fontSize: T.scale.body, bold: true,
      color: m.turn ? MARK : T.colours.ink, align: "center",
      objectName: "slides-field:Body",
    });
    text(s, m.e, {
      x: m.x - 1.85, y: 4.55, w: 3.7, h: 1.9,
      fontFace: T.fonts.body, fontSize: T.scale.caption,
      color: T.colours.ink, align: "center", valign: "top",
      objectName: "slides-field:Body",
    });
  });
  s.addNotes(C.s10.notes);
}

// ------------------------------------------------------------- 11. cierre ---
{
  const s = pres.addSlide();
  s.background = { color: T.colours.ink };

  mark(s, pres.shapes.LINE, {
    x: MX, y: 2.45, w: 1.7, h: 0,
    line: { color: T.colours.muted, width: 3 },
    objectName: "deco-rule-accent",
  });
  text(s, C.s11.statement.map((t, i, a) => ({ text: t, options: { breakLine: i < a.length - 1 } })), {
    x: MX, y: 2.7, w: 11.4, h: 2.6,
    fontFace: T.fonts.heading, fontSize: T.scale.h1, bold: true,
    color: T.colours.paper, valign: "top", lineSpacingMultiple: 1.08,
    objectName: "slides-lead:Statement",
  });
  s.addNotes(C.s11.notes);
}

pres
  .writeFile({ fileName: outPath })
  .then(() => console.log("wrote " + outPath))
  .catch((err) => {
    console.error(err.message);
    process.exit(1);
  });
