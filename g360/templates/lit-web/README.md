# Mi Proyecto G360

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="g360/brand/g360/logotypes/logo-g360-light.svg">
  <img alt="G360" height="64" src="g360/brand/g360/logotypes/logo-g360-dark.svg">
</picture>

> Aplicacion web G360 con Lit Web Components

## Quick Start

```bash
npm install
npm run dev
```

## Estructura del Proyecto

```mermaid
flowchart TD
    Frontend["Frontend<br/>Lit Web Components"]
    Assets["Assets<br/>brand · signature · favicon"]
    Config["Config<br/>skill.json"]

    Frontend --> Assets
    Frontend --> Config
```

## Identidad de Marca

| Elemento | Valor |
|---|---|
| Marca | G360 |
| Color primario | `#00d084` |
| Signature mode | `powered` |
| Signature text | "powered by G360" |

## Footer

```html
<g360-signature mode="powered"></g360-signature>
```

---

**Marca**: G360 · **Isotipo**: 3 puntos + chevron `>`
**Signature**: powered by G360 · **Powered by**: [g360-signature](https://github.com/carloscus/g360-signature)