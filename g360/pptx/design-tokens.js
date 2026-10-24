/**
 * Design tokens del sistema de presentaciones G360.
 *
 * Fuente unica de verdad: las paletas, tipografia y espaciados se definen aqui
 * y son consumidos por themes/ y layouts/.
 *
 * Los pasos de ACENTO salen de las familias de acento (misma fuente que las
 * apps web, Python, Go y Rust). Los neutros son propios del medio: una
 * presentacion se imprime sobre blanco, no sobre el fondo oscuro de la app.
 *
 * Principios:
 *  - Formato 16:9 widescreen (13.333 x 7.5 in), tipo deck corporativo.
 *  - Un acento principal + un oscuro para titulos + tintes suaves para superficies.
 *  - Ambar reservado para advertencias/limites; rojo solo para errores.
 *  - Texto principal casi-negro, secundario gris slate.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const families = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', 'config', 'accent-families.json'), 'utf8')
).families;

/**
 * Convierte un color al formato de pptxgenjs (sin #, mayusculas).
 * @param {string} value - Color
 * @returns {string}
 */
function hex(value) {
  return String(value).replace('#', '').toUpperCase();
}

/**
 * Mezcla un color con blanco para obtener un tinte solido (slides no usan rgba).
 * @param {string} value - Color base
 * @param {number} [ratio=0.12] - Proporcion del color
 * @returns {string} Hex sin #
 */
function tint(value, ratio = 0.12) {
  const source = String(value).replace('#', '');
  const channels = [0, 2, 4].map((index) => parseInt(source.slice(index, index + 2), 16));
  return channels
    .map((channel) => Math.round(255 * (1 - ratio) + channel * ratio))
    .map((channel) => channel.toString(16).padStart(2, '0'))
    .join('')
    .toUpperCase();
}

/**
 * Pasos de acento de una familia, en formato deck.
 * @param {string} familyName - Familia de acento
 * @returns {Object} accent, accentDark, accentBright, accentSoft, onAccent
 */
function accentSteps(familyName) {
  const family = families[familyName];
  if (!family) {
    throw new Error(`Familia de acento desconocida para el deck: "${familyName}"`);
  }
  return {
    accent: hex(family.accent),
    accentDark: hex(family.accentStrong),
    accentBright: hex(family.accentBright),
    accentSoft: tint(family.accent),
    onAccent: hex(family.onAccent),
  };
}

/** Semanticos de deck: el medio es claro, asi que van las variantes claras. */
const DECK_SEMANTICS = {
  warning: 'B45309',
  warningSoft: 'FDF3E3',
  info: '0369A1',
  violet: '7C3AED',
  success: '15803D',
  danger: 'DC2626',
};

/** Paletas de marca disponibles */
export const PALETTES = {
  /** G360 — esmeralda tech sobre slate neutro */
  g360: {
    ...accentSteps('emerald'),
    text: '0F172A',
    textMuted: '64748B',
    bg: 'FFFFFF',
    surface: 'F3F5F9',
    border: 'E3E8F0',
    ...DECK_SEMANTICS,
    coverTitle: hex(families.emerald.accentStrong),
  },

  /** CIPSA — verde corporativo (familia cipsa, la misma que usan sus apps) */
  cipsa: {
    ...accentSteps('cipsa'),
    text: '1F2937',
    textMuted: '64748B',
    bg: 'FFFFFF',
    surface: 'F8FAF9',
    border: 'C8E6D8',
    ...DECK_SEMANTICS,
    coverTitle: hex(families.cipsa.accentStrong),
  },

  /** Corporate — azul marino neutral para apps sin marca definida */
  corporate: {
    ...accentSteps('navy'),
    text: '0F172A',
    textMuted: '64748B',
    bg: 'FFFFFF',
    surface: 'F4F6FB',
    border: 'D6DEF0',
    ...DECK_SEMANTICS,
    coverTitle: hex(families.navy.accentStrong),
  },
};

/** Tipografia: pila de fuentes y escala de puntos */
export const TYPO = {
  font: 'Inter',
  fallback: 'Arial',
  sizes: {
    coverTitle: 44,
    coverSubtitle: 16,
    coverMeta: 12,
    sectionTitle: 21,
    cardTitle: 12,
    cardBody: 9.5,
    body: 11.5,
    bodySmall: 10,
    caption: 9.5,
    footer: 8,
    kpiValue: 28,
    kpiLabel: 11,
    stepNumber: 12,
    stepTitle: 11.5,
    stepBody: 10.5,
  },
};

/** Espaciados y metricas del lienzo 16:9 */
export const SPACING = {
  page: { width: 13.333, height: 7.5 },
  marginX: 0.6,
  get contentWidth() {
    return this.page.width - this.marginX * 2;
  },
  sectionTitleY: 0.3,
  sectionRuleY: 0.85,
  contentTopY: 1.1,
  footerY: 7.12,
  cardGap: 0.2,
  radius: 0.06,
};

/** Layout por defecto registrado en pptxgenjs */
export const DEFAULT_LAYOUT = 'LAYOUT_16x9_G360';

/**
 * Resuelve una paleta por nombre con fallback seguro.
 * @param {string} name — 'g360' | 'cipsa' | 'corporate'
 * @returns {object} paleta
 */
export function resolvePalette(name) {
  return PALETTES[name] || PALETTES.g360;
}
