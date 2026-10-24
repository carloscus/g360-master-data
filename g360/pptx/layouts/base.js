/**
 * Layouts reutilizables para slides G360 (formato 16:9 widescreen).
 * Componentes portados y alineados al manual de ventas-pulse:
 * portada con banda, encabezado de seccion con regla, tarjetas suaves,
 * marco de captura tipo telefono con encaje proporcional, flujo numerado,
 * limites con barra ambar, checklist con checks y KPIs.
 *
 * Cada layout recibe (slide, data, theme) y retorna el slide modificado.
 */
import fs from 'fs';
import { getImageSize } from '../scripts/image-size.js';

function baseTextOpts(theme) {
  return { fontFace: theme.typo?.font || 'Inter' };
}

/**
 * Bloque de texto multi-parrafo.
 * paragraphs: [{ text, size, bold, color, align, spaceAfter }]
 */
export function textBlock(slide, { x, y, w, h = 0.5, paragraphs }, theme) {
  const opts = baseTextOpts(theme);
  const runs = paragraphs.map((p, i) => ({
    text: p.text,
    options: {
      fontSize: p.size ?? theme.typo.sizes.body,
      bold: p.bold ?? false,
      color: p.color ?? theme.colors.text,
      align: p.align ?? 'left',
      paraSpaceAfter: p.spaceAfter ?? 6,
      breakLine: true,
      ...opts,
    },
  }));
  slide.addText(runs, { x, y, w, h, ...opts });
  return slide;
}

/**
 * Encabezado de seccion + footer con paginado (estilo ventas-pulse).
 */
export function addSectionHeader(slide, title, theme, pageNum = null, total = null) {
  const { colors, typo, spacing } = theme;
  slide.addText(title, {
    x: spacing.marginX, y: spacing.sectionTitleY,
    w: spacing.contentWidth, h: 0.5,
    fontSize: typo.sizes.sectionTitle, bold: true,
    color: colors.accentDark, ...baseTextOpts(theme),
  });
  slide.addShape('rect', {
    x: spacing.marginX, y: spacing.sectionRuleY,
    w: spacing.contentWidth, h: 0.035,
    fill: { color: colors.accent }, line: { type: 'none' },
  });
  if (pageNum !== null) addFooter(slide, theme, pageNum, total);
  return slide;
}

/**
 * Footer "powered by G360 · n/total".
 */
export function addFooter(slide, theme, slideNum, totalSlides) {
  const { colors, typo, spacing } = theme;
  slide.addText(`powered by G360 · ${slideNum}/${totalSlides}`, {
    x: spacing.page.width - 3.2, y: spacing.footerY,
    w: 3.0, h: 0.28,
    fontSize: typo.sizes.footer, color: colors.textMuted,
    align: 'right', ...baseTextOpts(theme),
  });
  return slide;
}

/**
 * Tarjeta suave con titulo y cuerpo (componente tarjeta de ventas-pulse).
 */
export function card(slide, { x, y, w, h, title, body = [], titleColor = null }, theme) {
  const { colors, typo } = theme;
  slide.addShape('roundRect', {
    x, y, w, h, rectRadius: theme.spacing.radius,
    fill: { color: colors.accentSoft },
    line: { color: colors.accent, width: 1 },
  });
  const runs = [
    {
      text: title,
      options: {
        fontSize: typo.sizes.cardTitle, bold: true,
        color: titleColor ?? colors.accentDark,
        paraSpaceAfter: 3, breakLine: true,
      },
    },
    ...body.map((line) => ({
      text: line,
      options: {
        fontSize: typo.sizes.cardBody,
        color: colors.text,
        paraSpaceAfter: 2, breakLine: true,
      },
    })),
  ];
  slide.addText(runs, {
    x: x + 0.15, y: y + 0.08, w: w - 0.3, h: h - 0.16,
    valign: 'top', ...baseTextOpts(theme),
  });
  return slide;
}

/**
 * Marco de captura estilo telefono. Coloca la imagen con encaje
 * proporcional (contain, nunca distorsiona); si no existe el archivo,
 * dibuja un placeholder punteado con la instruccion de captura.
 */
export function phoneShot(slide, { x, y, w, h, imagePath, label }, theme) {
  const { colors, typo } = theme;
  // Marco exterior
  slide.addShape('roundRect', {
    x: x - 0.07, y: y - 0.07, w: w + 0.14, h: h + 0.14,
    rectRadius: theme.spacing.radius,
    fill: { color: colors.text },
    line: { color: colors.accentDark, width: 1.75 },
  });
  const exists = imagePath && fs.existsSync(imagePath);
  if (exists) {
    const dim = getImageSize(imagePath);
    let dw = w, dh = h;
    if (dim && dim.width && dim.height) {
      const ir = dim.width / dim.height;
      const fr = w / h;
      if (ir > fr) { dh = w / ir; } else { dw = h * ir; }
    }
    slide.addImage({
      path: imagePath,
      x: x + (w - dw) / 2,
      y: y + (h - dh) / 2,
      w: dw, h: dh,
    });
  } else {
    slide.addShape('roundRect', {
      x, y, w, h, rectRadius: theme.spacing.radius,
      fill: { color: colors.surface },
      line: { color: colors.accent, width: 1, dashType: 'dash' },
    });
    slide.addText(
      [
        { text: 'CAPTURA PENDIENTE', options: { fontSize: typo.sizes.cardBody, bold: true, color: colors.textMuted, paraSpaceAfter: 4, breakLine: true } },
        { text: label || 'Screenshot de la app', options: { fontSize: typo.sizes.cardBody, color: colors.text, paraSpaceAfter: 4, breakLine: true } },
        ...(imagePath
          ? [{ text: `Guardar como: ${imagePath.split(/[\\/]/).slice(-2).join('/')}`, options: { fontSize: 8, color: colors.textMuted, breakLine: true } }]
          : []),
      ],
      { x: x + 0.12, y, w: w - 0.24, h, align: 'center', valign: 'middle', ...baseTextOpts(theme) },
    );
  }
  return slide;
}

/**
 * Slide de feature: descripcion + bullets.
 */
export function featureSlide(slide, data, theme) {
  const { colors, typo, spacing } = theme;
  slide.addText(data.title || 'Funcionalidad', {
    x: spacing.marginX, y: 1.05, w: spacing.contentWidth, h: 0.6,
    fontSize: 15, bold: true, color: colors.text, ...baseTextOpts(theme),
  });
  if (data.description) {
    slide.addText(data.description, {
      x: spacing.marginX, y: 1.65, w: spacing.contentWidth, h: 1.1,
      fontSize: typo.sizes.body, color: colors.text, valign: 'top', ...baseTextOpts(theme),
    });
  }
  if (Array.isArray(data.bullets) && data.bullets.length > 0) {
    const runs = data.bullets.map((b) => ({
      text: b,
      options: {
        bullet: { code: '2022', indent: 12 },
        fontSize: typo.sizes.bodySmall, color: colors.text,
        paraSpaceAfter: 5, breakLine: true,
      },
    }));
    slide.addText(runs, {
      x: spacing.marginX, y: 2.8, w: spacing.contentWidth, h: 3.5,
      valign: 'top', ...baseTextOpts(theme),
    });
  }
  return slide;
}

/**
 * Flujo de trabajo: pasos con circulo numerado + titulo y descripcion en linea.
 */
export function workflowSlide(slide, data, theme) {
  const { colors, typo, spacing } = theme;
  const steps = data.steps || [];
  const usableH = spacing.footerY - spacing.contentTopY - 0.15;
  const rowH = Math.min(1.0, steps.length > 0 ? usableH / steps.length : 1.0);
  let y = spacing.contentTopY;
  steps.forEach((step, i) => {
    slide.addShape('ellipse', {
      x: spacing.marginX, y: y + 0.03, w: 0.44, h: 0.44,
      fill: { color: colors.accent }, line: { type: 'none' },
    });
    slide.addText(String(i + 1), {
      x: spacing.marginX, y: y + 0.03, w: 0.44, h: 0.44,
      fontSize: typo.sizes.stepNumber, bold: true, color: colors.onAccent,
      align: 'center', valign: 'middle', ...baseTextOpts(theme),
    });
    slide.addText(
      [
        { text: `${step.title || ''}  `, options: { fontSize: typo.sizes.stepTitle, bold: true, color: colors.accentDark, breakLine: false } },
        { text: step.desc || '', options: { fontSize: typo.sizes.stepBody, color: colors.text, breakLine: true } },
      ],
      { x: spacing.marginX + 0.65, y, w: data.textWidth ?? spacing.contentWidth - 0.65, h: rowH, valign: 'middle', ...baseTextOpts(theme) },
    );
    y += rowH;
  });
  return slide;
}

/**
 * Limites conocidos: items con barra ambar (advertencias).
 * items: [{ title, desc }]
 */
export function limitsSlide(slide, data, theme) {
  const { colors, typo, spacing } = theme;
  const items = data.items || [];
  const cols = 2;
  const colW = (spacing.contentWidth - spacing.cardGap) / cols;
  const rowH = 1.75;
  items.forEach((item, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const x = spacing.marginX + col * (colW + spacing.cardGap);
    const y = spacing.contentTopY + row * rowH;
    slide.addShape('rect', {
      x, y: y + 0.05, w: 0.07, h: rowH - 0.25,
      fill: { color: colors.warning }, line: { type: 'none' },
    });
    slide.addText(
      [
        { text: item.title, options: { fontSize: 11.5, bold: true, color: colors.warning, paraSpaceAfter: 3, breakLine: true } },
        { text: item.desc, options: { fontSize: typo.sizes.bodySmall, color: colors.text, breakLine: true } },
      ],
      { x: x + 0.25, y, w: colW - 0.25, h: rowH - 0.1, valign: 'top', ...baseTextOpts(theme) },
    );
  });
  return slide;
}

/**
 * Checklist con checks verdes (buenas practicas / resumen).
 */
export function checklistSlide(slide, data, theme) {
  const { colors, typo, spacing } = theme;
  const items = data.items || [];
  const startY = data.startY ?? spacing.contentTopY;
  const rowH = data.rowH ?? 0.56;
  items.forEach((item, i) => {
    const y = startY + i * rowH;
    const checked = item.checked !== false;
    const runs = [
      {
        text: checked ? '✓  ' : '○  ',
        options: { fontSize: typo.sizes.body + 0.5, bold: true, color: checked ? colors.accent : colors.textMuted, breakLine: false },
      },
      {
        text: typeof item === 'string' ? item : item.text || '',
        options: { fontSize: typo.sizes.body + 0.5, color: colors.text, breakLine: true },
      },
    ];
    slide.addText(runs, {
      x: 1.0, y, w: spacing.contentWidth - 0.4, h: rowH, valign: 'middle', ...baseTextOpts(theme),
    });
  });
  return slide;
}

/**
 * Tabla de modulos: filas alternadas con nombre, ruta y descripcion.
 * rows: [{ name, route, desc }]
 */
export function modulesTable(slide, { rows, y = null, w = null }, theme) {
  const { colors, typo, spacing } = theme;
  const width = w ?? spacing.contentWidth - 4.35; // deja sitio a capturas laterales
  let yy = y ?? spacing.contentTopY;
  const rowH = 0.98;
  rows.forEach((row, i) => {
    slide.addShape('roundRect', {
      x: spacing.marginX, y: yy, w: width, h: rowH, rectRadius: theme.spacing.radius,
      fill: { color: i % 2 === 0 ? colors.accentSoft : colors.bg },
      line: { color: colors.accent, width: 0.75 },
    });
    slide.addText(row.name, {
      x: spacing.marginX + 0.2, y: yy + 0.1, w: 1.55, h: 0.4,
      fontSize: 12.5, bold: true, color: colors.accentDark, ...baseTextOpts(theme),
    });
    if (row.route) {
      slide.addText(row.route, {
        x: spacing.marginX + 1.75, y: yy + 0.13, w: 1.8, h: 0.4,
        fontSize: typo.sizes.cardBody, color: colors.textMuted, ...baseTextOpts(theme),
      });
    }
    slide.addText(row.desc, {
      x: spacing.marginX + 3.6, y: yy + 0.09, w: width - 3.8, h: rowH - 0.13,
      fontSize: typo.sizes.cardBody, color: colors.text, valign: 'top', ...baseTextOpts(theme),
    });
    yy += rowH + 0.14;
  });
  return yy;
}

/**
 * KPI cards (dashboard).
 * kpis: [{ label, value, sub, color }]
 */
export function kpiSlide(slide, data, theme) {
  const { colors, typo, spacing } = theme;
  const kpis = data.kpis || [];
  const cols = Math.min(kpis.length, 4) || 1;
  const colW = (spacing.contentWidth - spacing.cardGap * (cols - 1)) / cols;
  kpis.forEach((kpi, i) => {
    const x = spacing.marginX + i * (colW + spacing.cardGap);
    const color = kpi.color || colors.accent;
    slide.addShape('roundRect', {
      x, y: 1.2, w: colW, h: 2.5, rectRadius: theme.spacing.radius,
      fill: { color: colors.surface }, line: { color, width: 1 },
    });
    slide.addText(kpi.value || '—', {
      x, y: 1.35, w: colW, h: 0.9,
      fontSize: typo.sizes.kpiValue, bold: true, color,
      align: 'center', fontFace: 'JetBrains Mono, Consolas, monospace',
    });
    slide.addText(kpi.label || '', {
      x, y: 2.3, w: colW, h: 0.35,
      fontSize: typo.sizes.kpiLabel, color: colors.textMuted, align: 'center', ...baseTextOpts(theme),
    });
    if (kpi.sub) {
      slide.addText(kpi.sub, {
        x, y: 2.65, w: colW, h: 0.3,
        fontSize: 10, color: colors.textMuted, align: 'center', ...baseTextOpts(theme),
      });
    }
  });
  return slide;
}

/**
 * Arquitectura: capas apiladas con color por rol.
 * layers: [{ name, desc, color }]
 */
export function architectureSlide(slide, data, theme) {
  const { colors, typo, spacing } = theme;
  const layers = data.layers || [];
  const layerH = 1.15;
  let y = spacing.contentTopY + 0.1;
  layers.forEach((layer, i) => {
    const color = layer.color || colors.accent;
    slide.addShape('roundRect', {
      x: spacing.marginX, y, w: spacing.contentWidth, h: layerH,
      rectRadius: theme.spacing.radius,
      fill: { color: colors.surface }, line: { color, width: 1.5 },
    });
    slide.addText(layer.name, {
      x: spacing.marginX + 0.25, y: y + 0.1, w: 2.5, h: layerH - 0.2,
      fontSize: 15, bold: true, color, valign: 'middle', ...baseTextOpts(theme),
    });
    slide.addText(layer.desc, {
      x: spacing.marginX + 3.0, y: y + 0.1, w: spacing.contentWidth - 3.2, h: layerH - 0.2,
      fontSize: typo.sizes.bodySmall, color: colors.text, valign: 'middle', ...baseTextOpts(theme),
    });
    if (i < layers.length - 1) {
      slide.addText('▼', {
        x: spacing.page.width / 2 - 0.2, y: y + layerH + 0.01, w: 0.4, h: 0.24,
        fontSize: 10, color: colors.textMuted, align: 'center', ...baseTextOpts(theme),
      });
    }
    y += layerH + 0.32;
  });
  return slide;
}

/**
 * Portada: titulo grande centrado, banda de acento, subtitulo y meta.
 */
export function coverSlide(slide, data, theme) {
  const { colors, typo, spacing } = theme;
  const W = spacing.page.width;
  slide.addText(data.appName || 'Mi App G360', {
    x: 1.0, y: 1.5, w: W - 2.0, h: 1.3,
    fontSize: typo.sizes.coverTitle, bold: true, color: colors.coverTitle,
    align: 'center', valign: 'middle', ...baseTextOpts(theme),
  });
  slide.addShape('rect', {
    x: 0, y: 3.15, w: W, h: 0.055,
    fill: { color: colors.accent }, line: { type: 'none' },
  });
  const sub = slide.addText(
    [
      { text: data.description || 'Documentacion de uso y funcionalidades', options: { fontSize: typo.sizes.coverSubtitle, color: colors.text, paraSpaceAfter: 3, breakLine: true } },
      { text: data.tagline || '', options: { fontSize: typo.sizes.coverMeta, color: colors.textMuted, breakLine: true } },
    ],
    { x: 1.5, y: 3.5, w: W - 3.0, h: 1.2, align: 'center', ...baseTextOpts(theme) },
  );
  const meta = [
    data.version ? `Manual de uso · v${data.version}` : 'Manual de uso',
    'powered by G360',
  ].filter(Boolean).join('   ·   ');
  slide.addText(meta, {
    x: 1.0, y: 5.4, w: W - 2.0, h: 0.9,
    fontSize: 13, bold: false, color: colors.textMuted,
    align: 'center', ...baseTextOpts(theme),
  });
  const logo = typeof theme.logo === 'function' ? theme.logo() : null;
  if (logo) {
    slide.addImage({ path: logo.path, x: W / 2 - logo.w / 2, y: 6.35, w: logo.w, h: logo.h });
  }
  return slide;
}

// ===== Compat: nombres anteriores usados por templates =====
export { card as tarjeta, phoneShot as screenshotFrame };

/** screenshotSlide de compat: titulo + descripcion + marco */
export function screenshotSlide(slide, data, theme) {
  const { colors, typo, spacing } = theme;
  slide.addText(data.title || 'Captura de Pantalla', {
    x: spacing.marginX, y: 1.05, w: spacing.contentWidth, h: 0.6,
    fontSize: 15, bold: true, color: colors.text, ...baseTextOpts(theme),
  });
  if (data.description) {
    slide.addText(data.description, {
      x: spacing.marginX, y: 1.65, w: spacing.contentWidth, h: 0.75,
      fontSize: typo.sizes.bodySmall, color: colors.textMuted, valign: 'top', ...baseTextOpts(theme),
    });
  }
  return phoneShot(slide, {
    x: spacing.marginX + 1.2, y: 2.4, w: spacing.contentWidth - 2.4, h: 4.3,
    imagePath: data.screenshotPath,
    label: data.title || 'Screenshot de la app',
  }, theme);
}
