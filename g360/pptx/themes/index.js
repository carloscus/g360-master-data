/**
 * Fabrica de temas G360 para pptxgenjs.
 * Consumen design-tokens.js (fuente unica de verdad de paletas/estilos).
 */
import PptxGenJS from 'pptxgenjs';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import {
  PALETTES,
  TYPO,
  SPACING,
  DEFAULT_LAYOUT,
  resolvePalette,
} from '../design-tokens.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Layout 16:9 registrado por las fabricas de tema */
export function registerLayouts(pptx) {
  pptx.defineLayout({
    name: DEFAULT_LAYOUT,
    width: SPACING.page.width,
    height: SPACING.page.height,
  });
  pptx.layout = DEFAULT_LAYOUT;
}

/**
 * Crea un tema completo para pptxgenjs.
 * @param {string} name — 'g360' | 'cipsa' | 'corporate'
 */
export function createTheme(name = 'g360') {
  const colors = resolvePalette(name);
  const pptx = new PptxGenJS();
  registerLayouts(pptx);

  pptx.author = 'g360-cli';
  pptx.company = name === 'cipsa' ? 'CIPSA' : 'G360';
  pptx.subject = 'Manual de aplicacion generado por g360-cli';

  return {
    pptx,
    colors,
    typo: TYPO,
    spacing: SPACING,
    layout: DEFAULT_LAYOUT,
    font: TYPO.font,
    fallbackFont: TYPO.fallback,
    name,
    /**
     * Logo de marca (PNG) si existe; null si no.
     */
    logo() {
      const candidates = name === 'cipsa'
        ? [
            path.join(process.cwd(), 'assets', 'images', 'Logo_cipsa_solid.png'),
            path.join(__dirname, '..', 'brand', 'cipsa', 'logotypes', 'Logo_cipsa_solid.png'),
          ]
        : [
            path.join(process.cwd(), 'assets', 'images', 'logo-g360-dark.png'),
            path.join(__dirname, '..', 'brand', 'g360', 'logotypes', 'logo-g360-dark.png'),
          ];
      for (const p of candidates) {
        if (fs.existsSync(p)) return { path: p, w: 1.5, h: 0.5 };
      }
      return null;
    },
  };
}

/** Compat: tema G360 (esmeralda) */
export function createG360Theme() {
  return createTheme('g360');
}

/** Compat: tema CIPSA (verde corporativo) */
export function createCipsaTheme() {
  return createTheme('cipsa');
}

/** Compat: tema Corporate (azul marino) */
export function createCorporateTheme() {
  return createTheme('corporate');
}

export { PALETTES };
