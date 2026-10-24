/**
 * Analisis de app G360 — extrae features, screens y flujos de la estructura estandarizada.
 * Aprovecha las convenciones FLET-NAMING-CONVENTIONS.md para parseo deterministico.
 */
import fs from 'fs-extra';
import path from 'path';

/**
 * Clases UI conocidas → nombre legible para el usuario.
 */
const UI_CLASS_MAP = {
  'KpiCard': 'Indicadores KPI',
  'Dashboard': 'Dashboard',
  'WarehouseCard': 'Tarjeta de Almacen',
  'SearchOverlay': 'Buscador Flotante',
  'ExportModal': 'Exportar a Excel',
  'SkuDetailModal': 'Detalle de SKU',
  'TrasladosModal': 'Traslados entre Almacenes',
  'SinStockModal': 'Productos Sin Stock',
  'LineaSection': 'Seccion por Linea',
  'AppSidebar': 'Barra Lateral',
  'LoadingOverlay': 'Indicador de Carga',
  'HealthBadge': 'Estado de Salud',
};

/**
 * Patrón para detectar metodos desde src/app.py.
 */
const METHOD_PATTERN = /def\s+(_(?:setup|build|on|fetch|load|save|update|show|hide|toggle|validate|format)[_\w]*)/g;

/**
 * Patrón para detectar imports de clases UI.
 */
const IMPORT_UI_PATTERN = /from\s+src\.ui\.\w+\s+import\s+([\w,]+)/g;

/**
 * Analiza la estructura de una app G360.
 */
export async function analyzeApp(projectDir) {
  const result = {
    name: '',
    version: '',
    description: '',
    brand: 'g360',
    skill: '',
    framework: '',
    features: [],
    screens: [],
    workflows: [],
    modules: [],
    screenshots: [],
    hasSource1: false,
    hasSource2: false,
    hasExport: false,
    hasAutoRefresh: false,
    hasSearch: false,
    hasModals: [],
    templates: [],
  };

  // 1. Leer skill.json
  const skillPath = path.join(projectDir, 'skill.json');
  if (await fs.pathExists(skillPath)) {
    try {
      const skill = await fs.readJson(skillPath);
      result.name = skill.name || result.name;
      result.description = skill.description || result.description;
      // brand: campo directo o inferido del nombre del skill (cipsa-* → cipsa)
      if (skill.brand) {
        result.brand = skill.brand;
      } else if (/^cipsa/i.test(skill.skill || '')) {
        result.brand = 'cipsa';
      }
      result.skill = skill.skill || skill.name || '';
      result.framework = skill.framework || '';
      result.version = skill.version || '';
      result.events = skill.events || [];
    } catch { /* ignorar */ }
  }

  // 2. Leer manifest
  const manifestPath = path.join(projectDir, 'g360-manifest.json');
  if (await fs.pathExists(manifestPath)) {
    try {
      const manifest = await fs.readJson(manifestPath);
      result.name = manifest.name || result.name;
      result.version = manifest.version || result.version;
    } catch { /* ignorar */ }
  }

  // 3. Escanear src/ui/ para clases UI conocidas
  const uiDir = path.join(projectDir, 'src', 'ui');
  if (await fs.pathExists(uiDir)) {
    const uiFiles = await fs.readdir(uiDir);
    for (const file of uiFiles) {
      if (file === '__pycache__' || file.endsWith('.pyc')) continue;
      if (file === '__init__.py') continue;
      const filePath = path.join(uiDir, file);
      const st = await fs.stat(filePath).catch(() => null);
      if (!st || !st.isFile()) continue;
      const content = await fs.readFile(filePath, 'utf-8');
      const className = file.replace('.py', '');
      const displayName = UI_CLASS_MAP[className] || className;
      result.features.push({
        name: className,
        display: displayName,
        file,
        path: filePath,
      });
    }
  }

  // 4. Escanear modals
  const modalsDir = path.join(projectDir, 'src', 'ui', 'modals');
  if (await fs.pathExists(modalsDir)) {
    const modalFiles = await fs.readdir(modalsDir);
    for (const file of modalFiles) {
      if (file === '__pycache__' || file.endsWith('.pyc')) continue;
      if (file === '__init__.py') continue;
      const className = file.replace('.py', '');
      const displayName = UI_CLASS_MAP[className] || className;
      result.hasModals.push(className);
      result.workflows.push({
        name: className,
        display: displayName,
        steps: [`Abrir ${displayName}`, 'Interactuar con datos', 'Confirmar o cancelar'],
      });
    }
  }

  // 5. Detectar features desde src/app.py
  const appPy = path.join(projectDir, 'src', 'app.py');
  if (await fs.pathExists(appPy)) {
    const content = await fs.readFile(appPy, 'utf-8');
    
    // Detectar auto-refresh
    if (content.includes('auto_refresh') || content.includes('_auto_refresh')) {
      result.hasAutoRefresh = true;
    }
    // Detectar busqueda
    if (content.includes('search') || content.includes('SearchOverlay')) {
      result.hasSearch = true;
    }
    // Detectar source1
    if (content.includes('download_source1') || content.includes('source1')) {
      result.hasSource1 = true;
    }
    // Detectar export
    if (content.includes('export') || content.includes('excel') || content.includes('openpyxl')) {
      result.hasExport = true;
    }

    // Extraer metodos _on_* como flujos de usuario
    const methods = content.match(METHOD_PATTERN) || [];
    for (const match of methods) {
      const methodName = match.replace('def ', '').trim();
      if (methodName.startsWith('_on_')) {
        const displayName = methodName
          .replace('_on_', '')
          .replace(/_/g, ' ')
          .replace(/\b\w/g, l => l.toUpperCase());
        result.templates.push({
          type: 'interaction',
          name: methodName,
          display: displayName,
        });
      }
    }
  }

  // 6. Detección web: framework, módulos y capacidades desde package.json
  await analyzeWebApp(projectDir, result);

  // 7. Detectar Screenshots disponibles
  const screenshotsDir = path.join(projectDir, 'assets', 'screenshots');
  if (await fs.pathExists(screenshotsDir)) {
    try {
      const files = await fs.readdir(screenshotsDir);
      result.screenshots = files.filter(f => /\.(png|jpg|jpeg|webp)$/i.test(f)).map(f => ({
        filename: f,
        path: path.join(screenshotsDir, f),
      }));
    } catch { /* ignorar */ }
  }

  // 8. Descripcion y nombre amigable fallback desde README.md / package.json
  const readmeMeta = await metaFromReadme(projectDir);
  if (!result.description) {
    result.description = readmeMeta.description || (pkg?.description || '');
  }
  if (isGenericName(result.name, result.brand)) {
    // Primero intenta el H1; si el H1 es igual al slug, deriva del slug
    let friendly = '';
    if (readmeMeta.title && readmeMeta.title !== normalize(result.name)) {
      friendly = friendlyNameFromTitle(readmeMeta.title, result.name);
    }
    if (!friendly) {
      friendly = nameFromSlug(result.name);
    }
    if (friendly) result.name = friendly;
  }

  // 9. Emparejar screenshots con features (matching semantico ES/EN)
  matchScreenshots(result);

  return result;
}

/**
 * Extrae titulo (H1) y tagline (primer blockquote) del README.md.
 * Convencion G360 estandar: "# Titulo" + "> descripcion".
 */
async function metaFromReadme(projectDir) {
  const out = { title: '', description: '' };
  const readmePath = path.join(projectDir, 'README.md');
  if (!await fs.pathExists(readmePath)) return out;
  try {
    const content = await fs.readFile(readmePath, 'utf-8');
    const lines = content.split(/\r?\n/);
    let title = '';
    let tagline = '';
    for (const raw of lines) {
      const line = raw.trim();
      if (!line) continue;
      if (!title && /^#\s+/.test(line)) {
        title = line.replace(/^#\s+/, '').trim();
        continue;
      }
      if (title && !tagline && /^>\s+/.test(line)) {
        const t = line.replace(/^>\s+/, '').trim();
        if (!/^!\[|badge|shield/i.test(t) && t.length >= 15) tagline = t;
        continue;
      }
      if (title && tagline) break;
      if (title && !/^#|^>/) break;
    }
    const clean = (s) => s.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/[*`_]/g, '').trim();
    out.title = clean(title);
    out.description = clean(tagline);
  } catch { /* ignorar */ }
  return out;
}

/**
 * Nombre de display desde el H1: "StockPulse CIPSA - Stock Reporter (Lit PWA)"
 * → "StockPulse CIPSA". Si el H1 empieza con slug tecnico, se descarta esa parte.
 */
function friendlyNameFromTitle(title, fallbackName) {
  if (!title) return '';
  let parts = title.split(/\s+[-–—:|]\s+/);
  if (parts.length > 1 && /^g360-/i.test(parts[0].trim())) {
    parts = parts.slice(1);
  }
  const t = parts[0].replace(/\s*[(\[].*?[)\]]\s*/g, ' ').trim();
  return t || '';
}

/**
 * Un nombre es "generico" si es un slug tecnico (g360-*) o solo la marca
 * (ej. skill.json con name:"cipsa") — en ese caso se prefiere el titulo del README.
 */
function isGenericName(name, brand) {
  if (!name) return true;
  if (/^g360-[\w-]+$/.test(name)) return true;
  const n = normalize(name);
  return n === normalize(brand || '') || ['cipsa', 'g360'].includes(n);
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * Deriva un nombre legible a partir de un slug (strip g360-, title-case, hyphens to spaces).
 */
function nameFromSlug(slug) {
  const core = slug.replace(/^g360-/i, '').replace(/^-+|-+$/g, '');
  return core
    .replace(/-([a-z])/g, (_, c) => ' ' + c.toUpperCase())
    .replace(/\b\w/g, (l) => l.toUpperCase())
    .trim();
}

/**
 * Normaliza texto para matching: lowercase y sin acentos.
 */
function normalize(s) {
  return s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

/**
 * Empareja screenshots con features por tokens con sinonimos ES/EN.
 * Greedy: primero los pares con mejor score; cada screenshot se asigna 1 vez.
 */
function matchScreenshots(result) {
  const shots = result.screenshots.map((s) => ({
    ...s,
    tokens: normalize(s.filename.replace(/\.(png|jpe?g|webp)$/i, '')).split(/[^a-z0-9]+/).filter(Boolean),
  }));

  const candidatePairs = [];
  result.features.forEach((f, fi) => {
    const featTokens = [normalize(f.name), ...normalize(f.name).split(/[^a-z0-9]+/)]
      .filter((t) => t.length >= 3);
    shots.forEach((shot, si) => {
      let score = 0;
      for (const ft of featTokens) {
        for (const st of shot.tokens) {
          if (ft === st || st.includes(ft) || ft.includes(st)) score += 2;
        }
        // sinonimos: alerts <-> alertas, search <-> buscar, etc.
        for (const syn of SHOT_SYNONYMS[ft] || []) {
          if (shot.tokens.includes(syn)) score += 1;
        }
      }
      if (score > 0) candidatePairs.push({ fi, si, score });
    });
  });

  const usedShots = new Set();
  const usedFeats = new Set();
  candidatePairs
    .sort((a, b) => b.score - a.score)
    .forEach(({ fi, si }) => {
      if (usedShots.has(si) || usedFeats.has(fi)) return;
      result.features[fi].screenshotIndex = si;
      usedShots.add(si);
      usedFeats.add(fi);
    });
}

/**
 * Descripciones legibles para rutas web conocidas.
 */
const WEB_ROUTE_MAP = {
  dashboard: 'Vista principal: resumen operativo, KPIs y accesos a los módulos',
  hoy: 'Agenda del día: prioridades, alertas y avance',
  radar: 'Oportunidades priorizadas y ruta del día',
  netos: 'Montos netos jerárquicos por periodo',
  clientes: 'Directorio de clientes con filtros y búsqueda',
  ficha: 'Ficha de detalle por cliente con historial y precios',
  login: 'Autenticación y validación de acceso',
  reportes: 'Reportes y exportación de datos',
  stock: 'Consulta de existencias en tiempo real',
  pedidos: 'Gestión de pedidos y vigencias',
  config: 'Configuración y preferencias de la app',
};

/**
 * Componentes web: display amigable + descripcion.
 * infra: true = componente interno de la app, no es funcionalidad de usuario.
 */
const WEB_COMPONENT_MAP = {
  'app-root': { infra: true, display: 'Contenedor principal', desc: 'Contenedor principal de la aplicación' },
  'stock-header': { display: 'Encabezado de la app', desc: 'Encabezado con estado de conexión y acciones' },
  'stock-search': { display: 'Buscador de productos', desc: 'Búsqueda de productos con coincidencias en vivo' },
  'stock-alerts': { display: 'Alertas de stock', desc: 'Alertas de quiebres de stock y reposición' },
  'estado-panel': { display: 'Panel de estado', desc: 'Panel de estado por almacén/producto' },
  'pulso-form': { display: 'Formulario de registro', desc: 'Formulario de registro de datos de campo' },
  'sin-catalogo-panel': { display: 'Aviso de catálogo', desc: 'Aviso de catálogo no disponible con acción de carga' },
  'login': { display: 'Acceso', desc: 'Autenticación y validación de acceso' },
};

/** Sinónimos ES/EN para emparejar screenshots con features */
const SHOT_SYNONYMS = {
  alerts: ['alertas', 'alerta'],
  alert: ['alertas', 'alerta'],
  search: ['buscar', 'busqueda'],
  dashboard: ['inicio', 'hoy'],
  report: ['reporte', 'reportes', 'informe'],
  form: ['formulario', 'form'],
  catalog: ['catalogo'],
  state: ['estado'],
  clients: ['clientes'],
  client: ['clientes'],
  net: ['netos'],
  ficha: ['ficha'],
  radar: ['radar'],
  login: ['ingreso', 'acceso'],
  header: ['encabezado'],
};

/**
 * Detección para apps web: SvelteKit (routes), React (pages),
 * Lit/Componentes (src/components) y capacidades desde package.json.
 */
async function analyzeWebApp(projectDir, result) {
  const pkgPath = path.join(projectDir, 'package.json');
  const pkg = (await fs.pathExists(pkgPath))
    ? await fs.readJson(pkgPath).catch(() => null)
    : null;
  const deps = { ...(pkg?.dependencies || {}), ...(pkg?.devDependencies || {}) };
  const hasDep = (n) => Object.keys(deps).some((d) => d === n || d.startsWith(n));

  if (pkg) {
    result.name = result.name || pkg.name || '';
    result.version = result.version || pkg.version || '';
  }

  // Framework
  if (hasDep('@sveltejs/kit')) result.framework = result.framework || 'SvelteKit';
  else if (hasDep('solid-js') || hasDep('solid')) result.framework = result.framework || 'SolidJS';
  else if (hasDep('lit')) result.framework = result.framework || 'Lit';
  else if (hasDep('react')) result.framework = result.framework || 'React';
  else if (hasDep('vue')) result.framework = result.framework || 'Vue';
  if (result.framework) result.type = 'web';

  // Capabilidades desde dependencias
  if (hasDep('exceljs') || hasDep('xlsx') || hasDep('sheetjs')) result.hasExport = true;
  if (hasDep('@supabase/supabase-js')) result.hasSupabase = true;
  if (hasDep('vite-plugin-pwa') || hasDep('workbox-window')) result.hasPwa = true;
  if (hasDep('chart.js') || hasDep('recharts') || hasDep('echarts')) result.hasCharts = true;
  if (hasDep('tailwindcss') || hasDep('@tailwindcss/vite')) result.hasTailwind = true;

  // Módulos: SvelteKit routes (src/routes/**/+page.svelte, incluye subrutas dinámicas)
  const routesDir = path.join(projectDir, 'src', 'routes');
  if (await fs.pathExists(routesDir)) {
    const entries = await fs.readdir(routesDir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const routeDir = path.join(routesDir, entry.name);
      const pageFile = await findPageSvelte(routeDir);
      if (!pageFile) continue;
      result.features.push({
        name: entry.name,
        display: capitalize(entry.name),
        desc: WEB_ROUTE_MAP[entry.name] || `Sección ${entry.name} de la aplicación.`,
        file: path.relative(projectDir, pageFile).split(path.sep).join('/'),
        path: pageFile,
        kind: 'route',
      });
      result.modules.push(entry.name);
    }
  }

  // Módulos: componentes web destacados (src/components/*.js) — solo si no hay routes
  const componentsDir = path.join(projectDir, 'src', 'components');
  if (result.features.length === 0 && await fs.pathExists(componentsDir)) {
    const files = (await fs.readdir(componentsDir))
      .filter((f) => /\.(js|ts|tsx|jsx)$/.test(f));
    for (const file of files) {
      const base = file.replace(/\.(js|ts|tsx|jsx)$/, '');
      if (WEB_INFRA_NAMES.has(base.toLowerCase())) continue;
      const known = WEB_COMPONENT_MAP[base];
      if (known?.infra) continue; // contenedores internos no son funcionalidades
      result.features.push({
        name: base,
        display: known?.display || describeComponentName(base),
        desc: known?.desc || `Sección dedicada a ${describeComponentName(base).toLowerCase()}.`,
        file: `src/components/${file}`,
        path: path.join(componentsDir, file),
        kind: 'component',
      });
    }
  }

  // Buscador global: por nombre de componente/ruta o contenido de las páginas
  if (result.features.some((f) => /search|busca/i.test(f.name))) {
    result.hasSearch = true;
  } else {
    for (const f of result.features) {
      if (f.path && /\.(svelte|js|ts)$/.test(f.path)) {
        try {
          const content = await fs.readFile(f.path, 'utf-8');
          if (/search|buscador|lupa/i.test(content)) { result.hasSearch = true; break; }
        } catch { /* ignorar */ }
      }
    }
  }

  // Flujos web: modales/buscador como workflows si hay PWA/Supabase (solo títulos)
  if (result.features.length > 0 && result.hasPwa) {
    result.workflows.push({
      name: 'PWA',
      display: 'Instalación PWA y modo offline',
      steps: [
        'Abrir la URL de la app en el navegador',
        'Instalar desde el menú (Android/iOS)',
        'Usar con cache offline cuando no haya señal',
      ],
    });
  }
  if (result.hasSearch) {
    result.workflows.push({
      name: 'Busqueda',
      display: 'Búsqueda global',
      steps: ['Abrir el buscador', 'Escribir el criterio', 'Abrir el resultado'],
    });
  }
}

/**
 * Convierte PascalCase a nombre descriptivo separando palabras.
 * Ejemplo: PersonalDataSection → "Personal Data Section"
 */
function describeComponentName(pascalName) {
  return pascalName
    .replace(/([A-Z])/g, ' $1')
    .trim()
    .replace(/\b\w/g, (l) => l.toUpperCase());
}

/** Componentes que son infraestructura interna y no funcionalidad de usuario */
const WEB_INFRA_NAMES = new Set(['app', 'app-root', 'root', 'main', 'index', '__init__', 'entrypoint']);

/** Mapeo de palabras comunes EN→ES para nombres de componentes web */
const WORD_MAP = {
  preview: 'vista previa', panel: 'panel', section: 'sección', modal: 'ventana modal',
  form: 'formulario', buttons: 'botones', button: 'botón', contact: 'contacto',
  social: 'social', banner: 'banner', alerts: 'alertas', alert: 'alerta',
  search: 'búsqueda', catalog: 'catálogo', stock: 'stock', config: 'configuración',
  advanced: 'avanzada', personal: 'personal', data: 'datos',
  visual: 'visual', customization: 'personalización', upload: 'carga',
  signature: 'firma', creator: 'generador', generator: 'generador',
  status: 'estado', dashboard: 'panel principal', action: 'acción',
};

/** Busca recursivamente +page.svelte dentro de un directorio de ruta (subrutas dinámicas incluidas). */
async function findPageSvelte(dir, depth = 0) {
  if (depth > 3) return null;
  const direct = path.join(dir, '+page.svelte');
  if (await fs.pathExists(direct)) return direct;
  try {
    const children = await fs.readdir(dir, { withFileTypes: true });
    for (const child of children) {
      if (!child.isDirectory()) continue;
      const found = await findPageSvelte(path.join(dir, child.name), depth + 1);
      if (found) return found;
    }
  } catch { /* ignorar */ }
  return null;
}

/**
 * Mapeo de clase UI → tipo de slide recomendado.
 */
export function classifyFeature(feature) {
  if (feature.name.includes('Kpi') || feature.name.includes('Card')) return 'kpi';
  if (feature.name.includes('Modal')) return 'workflow';
  if (feature.name.includes('Dashboard')) return 'screenshot';
  if (feature.name.includes('Search')) return 'feature';
  return 'feature';
}
