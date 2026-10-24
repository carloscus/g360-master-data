# ARCHITECTURE.md

> Arquitectura del proyecto. Generado automaticamente por `g360 docs --level architecture`.

## Arquitectura General

```mermaid
flowchart TD
    subgraph Frontend["Frontend"]
        Index["index.html / App"]
        Main["Main entry"]
        Components["Components"]
        Styles["Styles"]
    end
    subgraph Assets["Assets"]
        Brand["Brand / logo"]
        Signature["Signature"]
        Favicon["Favicon"]
    end
    subgraph Config["Config"]
        Skill["skill.json"]
        Manifest["manifest"]
    end
    Frontend --> Assets
    Frontend --> Config
```

## Flujo de Datos

```mermaid
flowchart LR
    INPUT["Entrada del usuario"] --> PROCESS["Procesamiento"]
    PROCESS --> VALIDATE["Validacion"]
    VALIDATE --> OUTPUT["Resultado"]
    OUTPUT --> PERSIST["Persistencia"]
```

## Componentes

| Componente | Responsabilidad |
|---|---|
| Entry point | Punto de inicio de la aplicacion |
| Core | Logica de negocio y configuracion |
| UI | Presentacion e interaccion con el usuario |
| Assets | Recursos estaticos (imagenes, iconos, marca) |
| Config | Archivos de configuracion (skill.json, manifest) |

---

*Generado por `g360 docs --level architecture`*