/**
 * Template Manual de App G360 — formato 16:9 widescreen, estilo ventas-pulse.
 *
 * Estructura:
 * 1.   Portada
 * 2.   ¿Qué es? (descripcion + tarjetas usuario/tecnico)
 * 3.   Módulos (tabla de modulos + capturas)
 * 4.   Flujo de trabajo (pasos numerados + capturas)
 * 5-N. Funcionalidades (una por modulo UI detectado)
 * N+1. Flujos de trabajo (modales)
 * N+2. Arquitectura
 * N+3. Buenas prácticas
 * N+4. Límites conocidos (si el proyecto define appData.limits)
 * N+5. Resumen
 */
import path from 'path';
import { createTheme } from '../themes/index.js';
import {
  coverSlide,
  addSectionHeader,
  addFooter,
  card,
  phoneShot,
  featureSlide,
  workflowSlide,
  limitsSlide,
  checklistSlide,
  kpiSlide,
  architectureSlide,
  modulesTable,
} from '../layouts/base.js';

const MAX_FEATURES = 6;

/** Descripciones genericas por clase UI conocida */
const FEATURE_DESC = {
  KpiCard: 'Indicadores clave del negocio en tiempo real, con estados de alerta y recuento por categoría.',
  Dashboard: 'Vista principal con el resumen operativo: KPIs, listados y accesos a los módulos de trabajo.',
  WarehouseCard: 'Tarjeta de almacén con existencias y estado por depósito.',
  SearchOverlay: 'Buscador flotante global: localiza registros de cualquier módulo sin salir de la vista.',
  ExportModal: 'Exportación a Excel con formato corporativo para seguimiento y auditoría.',
  SkuDetailModal: 'Detalle de SKU: existencias, movimientos y atributos relevantes.',
  TrasladosModal: 'Traslados entre almacenes con validación de stock disponible.',
  SinStockModal: 'Productos sin stock: prioriza reposición y alternativas.',
  AppSidebar: 'Barra lateral de navegación entre módulos.',
};

function featureDesc(feature) {
  if (feature.desc) return feature.desc;
  if (FEATURE_DESC[feature.name]) return FEATURE_DESC[feature.name];
  if (feature.kind === 'route') return `Página accesible desde la navegación principal (${feature.file}). Estado sincronizado con los datos del negocio.`;
  if (feature.kind === 'component') return `Componente web en ${feature.file}, integrado al flujo principal de la app.`;
  return `Módulo de interfaz ubicado en src/ui/${feature.file}, integrado al flujo principal de la aplicación.`;
}

function classify(feature) {
  if (feature.name.includes('Kpi') || feature.name.includes('Card')) return 'kpi';
  if (feature.name.includes('Modal') || feature.name.includes('Dialog')) return 'workflow';
  if (feature.name.includes('Dashboard')) return 'screenshot';
  return 'feature';
}

/**
 * Genera un manual PPTX completo para una app G360 (16:9).
 *
 * @param {object} appData — resultado de analyzeApp()
 * @param {object} options — { mode, theme, outPath }
 * @returns {Promise<string>} — ruta del archivo .pptx generado
 */
export async function generateManualPptx(appData, options = {}) {
  const { mode = 'manual' } = options;
  const themeName = options.theme || appData.brand || 'g360';
  const theme = createTheme(themeName === 'cipsa' ? 'cipsa' : themeName);
  const { pptx, colors } = theme;
  const S = theme.spacing;

  const appName = appData.name || 'Mi Aplicación G360';
  const features = appData.features.slice(0, MAX_FEATURES);
  const hasModals = (appData.hasModals?.length || 0) > 0;
  const hasLimits = Array.isArray(appData.limits) && appData.limits.length > 0;

  const totalSlides = 4
    + features.length
    + (hasModals ? 1 : 0)
    + 3
    + (hasLimits ? 1 : 0);

  let slideNum = 0;
  const bg = { color: colors.bg };
  const newSlide = () => {
    const s = pptx.addSlide();
    s.background = bg;
    return s;
  };

  const screenshotFor = (feature) => {
    if (feature.screenshotIndex >= 0 && appData.screenshots?.[feature.screenshotIndex]) {
      return appData.screenshots[feature.screenshotIndex].path;
    }
    const shot = appData.screenshots?.find((s) =>
      s.filename.toLowerCase().includes(feature.name.toLowerCase().slice(0, 4)),
    );
    return shot?.path || null;
  };

  // ===== 1. Portada =====
  let slide = newSlide();
  coverSlide(slide, {
    appName,
    description: appData.description || 'Documentación de uso y funcionalidades',
    tagline: buildTagline(appData),
    version: appData.version,
    brand: themeName,
  }, theme);
  addFooter(slide, theme, ++slideNum, totalSlides);

  // ===== 2. ¿Qué es? =====
  slide = newSlide();
  addSectionHeader(slide, 'INTRODUCCIÓN', theme, ++slideNum, totalSlides);
  slide.addText(`¿Qué es ${appName}?`, {
    x: S.marginX, y: 1.05, w: S.contentWidth, h: 0.45,
    fontSize: 15, bold: true, color: colors.text, fontFace: theme.font,
  });
  slide.addText(appData.description || 'Aplicación construida con los estándares G360.', {
    x: S.marginX, y: 1.5, w: S.contentWidth, h: 0.85,
    fontSize: theme.typo.sizes.body, color: colors.text,
    valign: 'top', fontFace: theme.font,
  });
  card(slide, {
    x: S.marginX, y: 2.55, w: (S.contentWidth - S.cardGap) / 2, h: 2.0,
    title: 'Para el usuario',
    body: features.length > 0
      ? features.slice(0, 4).map((f) => f.display || f.name)
      : ['Acceso a los módulos principales de la app'],
  }, theme);
  card(slide, {
    x: S.marginX + (S.contentWidth - S.cardGap) / 2 + S.cardGap, y: 2.55,
    w: (S.contentWidth - S.cardGap) / 2, h: 2.0,
    title: 'Bajo el capó',
    body: buildTechBullets(appData, features),
  }, theme);
  slide.addText(buildCapabilityLine(appData), {
    x: S.marginX, y: 4.85, w: S.contentWidth, h: 1.6,
    fontSize: theme.typo.sizes.body, color: colors.textMuted, valign: 'top', fontFace: theme.font,
  });

  // ===== 3. Módulos =====
  slide = newSlide();
  addSectionHeader(slide, 'MÓDULOS', theme, ++slideNum, totalSlides);
  modulesTable(slide, {
    rows: features.map((f) => ({
      name: f.display || f.name,
      route: f.file,
      desc: featureDesc(f),
    })),
  }, theme);
  // Capturas: primero las asignadas a features, luego las libres (dashboard, reportes...)
  const shots = features.map(screenshotFor).filter(Boolean);
  const usedShotIdx = new Set(features.map((f) => f.screenshotIndex).filter((i) => i >= 0));
  const freeShots = (appData.screenshots || [])
    .filter((s, i) => !usedShotIdx.has(i))
    .map((s) => s.path);
  const allShots = [...shots, ...freeShots];
  if (allShots[0]) {
    phoneShot(slide, {
      x: S.page.width - S.marginX - 3.95, y: S.contentTopY,
      w: 1.85, h: 4.0, imagePath: allShots[0],
      label: `Captura de ${features[0].display || features[0].name}`,
    }, theme);
  }
  if (allShots[1]) {
    phoneShot(slide, {
      x: S.page.width - S.marginX - 1.9, y: S.contentTopY,
      w: 1.85, h: 4.0, imagePath: allShots[1],
      label: `Captura de ${features[1]?.display || 'módulo'}`,
    }, theme);
  }
  slide.addText('Cada módulo se detalla en las siguientes páginas.', {
    x: S.marginX, y: S.contentTopY + features.length * 1.12 + 0.1, w: S.contentWidth - 4.35, h: 0.5,
    fontSize: theme.typo.sizes.caption, color: colors.textMuted, fontFace: theme.font,
  });

  // ===== 4. Flujo de trabajo =====
  slide = newSlide();
  addSectionHeader(slide, 'FLUJO DE TRABAJO', theme, ++slideNum, totalSlides);
  workflowSlide(slide, {
    textWidth: S.contentWidth - 0.65 - 4.9,
    steps: buildWorkflowSteps(appData),
  }, theme);
  if (allShots[2]) {
    phoneShot(slide, {
      x: S.page.width - S.marginX - 4.75, y: S.contentTopY + 0.15,
      w: 2.25, h: 4.9, imagePath: allShots[2],
      label: 'Pantalla de inicio / login',
    }, theme);
  }
  if (allShots[3]) {
    phoneShot(slide, {
      x: S.page.width - S.marginX - 2.3, y: S.contentTopY + 0.15,
      w: 2.25, h: 4.9, imagePath: allShots[3],
      label: 'Vista principal en uso',
    }, theme);
  }

  // ===== 5-N. Features =====
  for (const feature of features) {
    slide = newSlide();
    addSectionHeader(slide, 'FUNCIONALIDAD', theme, ++slideNum, totalSlides);
    const kind = classify(feature);
    const shotPath = screenshotFor(feature);
    const textW = shotPath ? S.contentWidth - 5.1 : S.contentWidth;

    if (kind === 'kpi') {
      kpiSlide(slide, {
        title: feature.display || feature.name,
        kpis: [
          { label: 'Registros', value: '—', color: colors.accent },
          { label: 'Activos', value: '—', color: colors.success },
          { label: 'Alertas', value: '—', color: colors.warning },
          { label: 'Críticos', value: '—', color: colors.danger },
        ],
      }, theme);
    } else {
      featureSlide(slide, {
        title: feature.display || feature.name,
        description: featureDesc(feature),
        bullets: kind === 'workflow'
          ? ['Se abre desde el módulo principal', 'Interacción guiada paso a paso', 'Confirmación con resumen del resultado']
          : feature.kind === 'route'
            ? [
                `Ruta accesible desde la navegación principal (${feature.file})`,
                'Estado sincronizado con los datos del negocio',
                'Diseño responsive y táctil',
              ]
            : feature.kind === 'component'
              ? [
                  `Componente web en ${feature.file}`,
                  'Integrado al flujo principal de la app',
                  'Reutilizable y con estados de carga/error',
                ]
              : [
                  `Clase ${feature.name} exportada desde src/ui/${feature.file}`,
                  'Integrada al Dashboard principal',
                  'Respeta el tema claro/oscuro del sistema',
                ],
      }, theme);
      // limitar ancho del texto si hay captura
      if (shotPath) {
        slide.addText(`${feature.display || feature.name}`, {
          x: S.marginX, y: 1.05, w: textW, h: 0.6,
          fontSize: 15, bold: true, color: colors.text, fontFace: theme.font,
        });
      }
    }

    if (shotPath) {
      phoneShot(slide, {
        x: S.page.width - S.marginX - 2.6, y: 1.25,
        w: 2.55, h: 4.9, imagePath: shotPath,
        label: `Captura de ${feature.display || feature.name}`,
      }, theme);
    } else {
      phoneShot(slide, {
        x: S.page.width - S.marginX - 2.6, y: 1.25,
        w: 2.55, h: 4.9, imagePath: null,
        label: `Captura de ${feature.display || feature.name} en uso`,
      }, theme);
    }
    addFooter(slide, theme, slideNum, totalSlides);
  }

  // ===== N+1. Flujos (modales) =====
  if (hasModals) {
    slide = newSlide();
    addSectionHeader(slide, 'FLUJOS DE TRABAJO', theme, ++slideNum, totalSlides);
    workflowSlide(slide, {
      textWidth: S.contentWidth - 0.65,
      steps: appData.hasModals.slice(0, 6).map((m) => ({
        title: m.replace(/([a-z])([A-Z])/g, '$1 $2'),
        desc: 'Flujo de usuario con confirmación y resultado trazable.',
      })),
    }, theme);
    addFooter(slide, theme, slideNum, totalSlides);
  }

  // ===== N+2. Arquitectura (context-aware según framework) =====
  slide = newSlide();
  addSectionHeader(slide, 'ARQUITECTURA', theme, ++slideNum, totalSlides);
  const isWeb = appData.type === 'web';
  architectureSlide(slide, {
    layers: isWeb
      ? [
          { name: 'UI', desc: `Components y vistas (${appData.modules?.length ? appData.modules.join(', ') : 'src/components/'})`, color: colors.accent },
          { name: 'Hooks', desc: 'Custom hooks y estado local (src/hooks/)', color: colors.info },
          { name: 'Utils', desc: 'Helpers, tipos y utilidades (src/utils/)', color: colors.violet },
          { name: 'Config', desc: 'vite.config, skill.json, manifest', color: colors.success },
        ]
      : [
          { name: 'UI', desc: 'Dashboard, Cards, Modals, Overlays (src/ui/)', color: colors.accent },
          { name: 'Core', desc: 'Lógica de negocio y procesamiento (src/core/)', color: colors.info },
          { name: 'Config', desc: 'Tema, constantes y metadata (skill.json)', color: colors.violet },
          { name: 'Datos', desc: 'API ERP, catálogo y cache local', color: colors.success },
        ],
  }, theme);
  addFooter(slide, theme, slideNum, totalSlides);

  // ===== N+3. Buenas prácticas =====
  slide = newSlide();
  addSectionHeader(slide, 'BUENAS PRÁCTICAS', theme, ++slideNum, totalSlides);
  checklistSlide(slide, {
    items: [
      'Mantener la sesión activa solo mientras se usa la app',
      'Actualizar datos antes de decidir (auto-refresh o botón de recarga)',
      'Usar la exportación a Excel para seguimiento y auditoría',
      'Reportar anomalías al administrador con el registro específico',
      'Compartir el dispositivo solo con sesión cerrada',
      'Verificar conectividad si los datos aparecen desactualizados',
    ],
  }, theme);
  addFooter(slide, theme, slideNum, totalSlides);

  // ===== N+4. Límites (opcional, definidos por el proyecto) =====
  if (hasLimits) {
    slide = newSlide();
    addSectionHeader(slide, 'LÍMITES CONOCIDOS', theme, ++slideNum, totalSlides);
    limitsSlide(slide, { items: appData.limits }, theme);
    addFooter(slide, theme, slideNum, totalSlides);
  }

  // ===== Resumen =====
  slide = newSlide();
  addSectionHeader(slide, 'RESUMEN', theme, ++slideNum, totalSlides);
  checklistSlide(slide, {
    startY: 1.5,
    items: [
      `Nombre: ${appName}`,
      `Versión: ${appData.version || '1.0.0'}`,
      `Framework: ${appData.framework || 'N/A'}`,
      `Módulos UI: ${appData.features.length}`,
      appData.hasAutoRefresh ? 'Auto-refresh de datos activado' : 'Actualización manual de datos',
      appData.hasSearch ? 'Buscador global disponible' : null,
      appData.hasExport ? 'Exportación a Excel disponible' : null,
      hasModals ? `${appData.hasModals.length} flujos con modales de trabajo` : null,
    ].filter(Boolean).map((t) => ({ text: t, checked: true })),
  }, theme);
  slide.addText('Documentación completa: README.md · powered by G360', {
    x: S.marginX, y: 6.6, w: S.contentWidth, h: 0.4,
    fontSize: theme.typo.sizes.bodySmall, color: colors.textMuted,
    align: 'center', fontFace: theme.font,
  });

  // Save — por defecto dentro del repo de la app (cada PPTX es propio de su repo)
  const slug = appName.toLowerCase().replace(/\s+/g, '-');
  const defaultDir = options.targetDir || process.cwd();
  const outPath = options.outPath
    || path.join(defaultDir, mode === 'demo' ? `${slug}-demo.pptx` : `${slug}-manual.pptx`);
  await pptx.writeFile({ fileName: outPath });
  return outPath;
}

function buildTagline(appData) {
  const bits = [];
  if (appData.framework) bits.push(appData.framework);
  if (appData.features.length) bits.push(`${appData.features.length} módulos UI`);
  if (appData.hasModals?.length) bits.push(`${appData.hasModals.length} flujos de trabajo`);
  if (appData.type === 'web' && appData.hasPwa) bits.push('PWA instalable');
  return bits.join('  ·  ');
}

function buildTechBullets(appData, features) {
  const bullets = [];
  if (appData.framework) bullets.push(`Framework: ${appData.framework}`);
  bullets.push(`${appData.features.length} módulos UI detectados`);
  if (appData.hasModals?.length) bullets.push(`${appData.hasModals.length} modales de trabajo en src/ui/modals/`);
  if (appData.hasExport) bullets.push('Exportación a Excel integrada');
  if (appData.hasAutoRefresh) bullets.push('Auto-refresh de datos (~15 min)');
  if (appData.hasSupabase) bullets.push('Datos en tiempo real vía Supabase');
  if (appData.hasPwa) bullets.push('PWA instalable con cache offline');
  if (appData.hasCharts) bullets.push('Visualización de datos con gráficos');
  if (appData.hasSearch) bullets.push('Búsqueda global con overlay flotante');
  bullets.push('Metadata y eventos declarados en skill.json');
  return bullets.slice(0, 6);
}

function buildCapabilityLine(appData) {
  const caps = [];
  if (appData.hasAutoRefresh) caps.push('datos en tiempo real');
  if (appData.hasSearch) caps.push('búsqueda global');
  if (appData.hasExport) caps.push('export a Excel');
  if (appData.hasSource1 || appData.hasSupabase) caps.push('conexión a ERP/Supabase');
  if (appData.hasPwa) caps.push('modo offline (PWA)');
  if (appData.hasCharts) caps.push('gráficos interactivos');
  return caps.length > 0
    ? `Capacidades destacadas: ${caps.join(' · ')}.`
    : 'Revisa los módulos en las siguientes páginas para conocer las capacidades de la app.';
}

function buildWorkflowSteps(appData) {
  if (appData.templates?.length >= 4) {
    return appData.templates.slice(0, 6).map((t, i) => ({
      title: `${i + 1} · ${t.display}`,
      desc: `Interacción "${t.name.replace(/^_on_/, '').replace(/_/g, ' ')}" registrada en src/app.py.`,
    }));
  }
  // Apps generadoras / configuradoras (signature, calculators, forms)
  const isGenerator = /crear|generador|creator|calculator|form|constructor/i.test(appData.name || '');
  if (isGenerator) {
    return [
      { title: '1 · Completar formulario', desc: 'Ingresa los datos requeridos (nombre, cargo, contacto, etc.).' },
      { title: '2 · Previsualizar en vivo', desc: 'Observa los cambios en tiempo real con debounce.' },
      { title: '3 · Configurar opciones', desc: 'Ajusta formato, colores, redes sociales y tamaño.' },
      { title: '4 · Seleccionar formato', desc: 'Elige entre completo, medio, corto o mínimo.' },
      { title: '5 · Copiar / descargar', desc: 'Exporta la firma al portapapeles o descarga el archivo.' },
    ];
  }
  return [
    { title: 'Ingresar', desc: 'Abre la app y autentícate si el proyecto lo requiere.' },
    { title: 'Revisar el dashboard', desc: 'El resumen principal concentra KPIs y accesos a los módulos.' },
    { title: 'Explorar módulos', desc: 'Cada módulo cubre una parte del flujo operativo del negocio.' },
    { title: 'Operar', desc: 'Registra, edita o consulta según el módulo de trabajo.' },
    { title: 'Exportar / compartir', desc: 'Genera reportes en Excel cuando el proyecto lo integre.' },
    { title: 'Cerrar sesión', desc: 'Si compartes el dispositivo, cierra tu sesión al terminar.' },
  ];
}
