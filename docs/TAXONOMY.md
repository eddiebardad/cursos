# Taxonomía normativa y guía semántica de Cursodex

**Versión de referencia:** Cursodex Extractor `v0.4.1`

**Fuentes de verdad del comportamiento:** [`mappings/vocab_map.yml`](../mappings/vocab_map.yml) y [`schemas/models.py`](../schemas/models.py).
**Propósito:** catalogación consistente, auditoría de resultados y base de conocimiento para el futuro generador de rutas `schema:ItemList` (Hito 4).

Este manual distingue el vocabulario que el software aplica hoy de la interpretación disciplinar que guía a curadores y a sistemas de recomendación. Los disparadores enumerados por categoría son los literales del YAML vigente; no se deben tratar como un clasificador semántico entrenado ni como una garantía de que cualquier frase coincidente pertenezca a la disciplina.

## 1. Arquitectura Semántica de Catalogación en Cursodex

### 1.1 Capas de anotación

| Capa | Propiedad Schema.org / espejo | Vocabulario o forma | Función catalográfica |
|---|---|---|---|
| Área temática macro | `schema:about` / `dcterms:subject` | Vocabulario cerrado de 17 categorías (`CustomVocab:1`, convención prevista para Omeka S) | Asigna un dominio principal para facetas, búsqueda y filtro duro de rutas. Si no hay clasificación fiable, el valor se retiene como metadato privado y no se publica como asunto. |
| Tema granular | `schema:keywords` | Lista abierta de etiquetas de origen | Retiene herramientas, lenguajes, técnicas, productos y conceptos concretos. Complementa el área macro; no la sustituye ni debe promoverse automáticamente a categoría. |
| Progresión | `schema:educationalLevel` | `Principiante`, `Intermedio`, `Avanzado` (`CustomVocab:2`, convención prevista) | Permite ordenar cursos por dificultad estimada/declarada. La ausencia de nivel es válida y por sí sola no activa `needs_review`. |
| Acceso y credencial | `schema:educationalCredentialAwarded` | Etiqueta derivada de `AccessType` (`CustomVocab:3`, convención prevista) | Comunica si el curso gratuito incluye credencial, permite auditoría con credencial de pago o no ofrece credencial. |
| Requisitos | `schema:coursePrerequisites` | Lista de textos declarados | Conserva requisitos explícitos o normalizados por el proveedor. En el grafo de una ruta puede inspirar dependencias, pero no es un identificador de curso ni una relación ya resuelta. |
| Tiempo estimado | `schema:timeRequired` | Duración ISO 8601, por ejemplo `PT2H30M`, `P3D` | Permite calcular carga acumulada cuando las duraciones sean interpretables y comparables. |

### 1.2 Límite entre el extractor y la configuración de Omeka S

Los nombres `CustomVocab:1`, `CustomVocab:2` y `CustomVocab:3` se usan aquí como **convención de despliegue** para los vocabularios de área, nivel y acceso. No son IDs de propiedad que el extractor envíe ni identificadores definidos en este repositorio: `JSONLDExporter` emite las etiquetas como valores literales con `property_id: "auto"`. La persona administradora debe confirmar los IDs reales de `Custom Vocab` en cada instancia de Omeka S y mapear allí las etiquetas canónicas.

`Pendiente_Categoria` es un centinela de trabajo del modelo, no una de las 17 categorías. El exportador conserva la categoría en `_cursodex_meta.category`, pero omite `schema:about` y `dcterms:subject` para que una clasificación no curada no contamine el grafo público.

### 1.3 Qué significa cada capa para catalogación

- **Una categoría principal, varias keywords:** `category` resuelve un área controlada; `keywords` puede conservar, por ejemplo, `Python`, `Azure`, `Excel` o nombres de competencias. No se deben sustituir las etiquetas del proveedor por sinónimos inventados.
- **Un idioma de curso no es el área Idiomas:** `schema:inLanguage` describe el idioma del material (ISO 639-1, como `es` o `en`). La categoría `Idiomas` se refiere al aprendizaje/adquisición de lenguas (`0231`), no al idioma en que se enseña un curso.
- **Nivel no equivale a prerrequisito:** `educationalLevel` es una etiqueta ordinal; `coursePrerequisites` expresa conocimientos o cursos previos. No deducir un nivel solo del título.
- **Acceso gratuito no equivale a credencial gratuita:** `isAccessibleForFree` debe ser verdadero para todos los cursos admitidos; `AccessType` distingue la credencial y no permite aceptar un curso cuyo acceso obligatorio sea de pago.
- **Datos ausentes se mantienen ausentes:** no completar duración, requisitos, nivel, idioma o credenciales por inferencia no verificable. Los campos incompletos activan el triaje establecido por el modelo.

## 2. Fuentes Normativas Internacionales y Europeas

### 2.1 UNESCO CINE-F 2013 / ISCED-F

La **Clasificación Internacional Normalizada de la Educación: Campos de Educación y Formación 2013 (CINE-F / ISCED-F 2013)** es la estructura disciplinar de referencia. Sus campos amplios `00`–`10` clasifican el campo principal de educación/formación; los códigos de tres y cuatro dígitos aportan detalle. La taxonomía Cursodex conserva esa estructura donde es útil y agrupa algunas ramas digitales, ambientales y de servicios para disponer de 17 facetas operativas.

En conjunto, las 17 categorías cubren los once campos amplios `00`–`10`; la correspondencia no es uno-a-uno: algunas categorías desagregan un campo (por ejemplo TIC y lenguas) y otras reúnen campos/subcampos afines (`08` + `052`).

| Campo amplio | Denominación CINE-F 2013 |
|---|---|
| `00` | Programas y cualificaciones genéricos |
| `01` | Educación |
| `02` | Artes y humanidades |
| `03` | Ciencias sociales, periodismo e información |
| `04` | Administración de empresas y derecho |
| `05` | Ciencias naturales, matemáticas y estadística |
| `06` | Tecnologías de la información y la comunicación (TIC) |
| `07` | Ingeniería, industria y construcción |
| `08` | Agricultura, silvicultura, pesca y veterinaria |
| `09` | Salud y bienestar |
| `10` | Servicios |

Subcampos decisivos para interpretar esta taxonomía:

- `0011` corresponde a programas y cualificaciones básicos; Cursodex lo usa como anclaje práctico para alfabetización/competencias digitales básicas, no como afirmación de que toda ofimática sea un programa básico.
- `0031` es desarrollo de habilidades personales. Se relaciona aquí con la categoría de habilidades transversales; no es un código de administración empresarial.
- `021` cubre artes; `022`, humanidades excepto idiomas; `023`, idiomas. Dentro de `023`, **`0231` es adquisición de idiomas** y **`0232` es literatura y lingüística**. En consecuencia, Filología, Literatura y Lingüística se sitúan en `#13`, mientras que aprender una lengua extranjera se sitúa en `#15`.
- `0414` es marketing y publicidad; `04` agrupa administración de empresas y derecho.
- `052` corresponde a medio ambiente. La categoría `#10` combina ese subcampo con el campo amplio `08` (agricultura, silvicultura, pesca y veterinaria).
- `061` es TIC. El vocabulario subdivide esta área en datos/IA (`0613`), redes/cloud/seguridad (`0612`), desarrollo de software (`0613`), competencias digitales/ofimática (`0011`) y TIC general (`061`).
- `101`–`104` corresponden, respectivamente, a servicios personales, higiene y salud laboral, servicios de seguridad y servicios de transporte. La categoría `#17` agrupa estas áreas de servicios.

### 2.2 Marcos europeos y vocabularios complementarios

Los marcos de la Comisión Europea/JRC complementan el anclaje CINE-F con competencias transversales. No reemplazan CINE-F ni constituyen todos un segundo vocabulario jerárquico configurado en el YAML.

| Marco | Uso en Cursodex |
|---|---|
| **DigComp 2.2** | Referencia para competencia digital ciudadana y especializaciones de TIC/ofimática. El proyecto declara específicamente la edición 2.2 en su vocabulario. |
| **DigCompEdu** | Referencia para competencias digitales docentes y el dominio educativo; no debe confundirse con un nivel de dificultad del curso. |
| **EntreComp** | Competencia emprendedora y creación de valor; relevante para emprendimiento, administración y proyectos. |
| **LifeComp** | Competencias personales, sociales y de aprender a aprender; principal marco complementario de `#16`. |
| **GreenComp** | Competencias de sostenibilidad; principal marco complementario de `#10`. |
| **ESCO** | Clasificación multilingüe europea de ocupaciones, competencias y cualificaciones. Puede enriquecer enlaces entre cursos y perfiles/skills, pero no es una fuente de sinónimos implementada por `resolve_category()`. |
| **MCER / CEFR** | Marco del Consejo de Europa para describir aprendizaje y dominio de lenguas. Da contexto pedagógico a `#15` (`0231`); el modelo actual no calcula niveles MCER A1–C2. |

> **Versionado:** la fuente del proyecto especifica DigComp 2.2. La documentación externa de JRC puede presentar ediciones posteriores; no se deben sustituir las etiquetas o reglas locales basándose en una versión posterior sin un cambio de taxonomía explícito.

Referencias oficiales:

- [UNESCO UIS — ISCED](https://uis.unesco.org/en/topic/international-standard-classification-education-isced) y [CINE-F / ISCED-F 2013 (publicación UNESCO UIS)](https://uis.unesco.org/sites/default/files/documents/isced-fields-of-education-and-training-2013-en.pdf).
- [JRC — DigComp 2.2, publicación JRC128415](https://publications.jrc.ec.europa.eu/repository/handle/JRC128415).
- [JRC — DigCompEdu](https://publications.jrc.ec.europa.eu/repository/handle/JRC107466).
- [JRC — EntreComp](https://publications.jrc.ec.europa.eu/repository/handle/JRC101581).
- [JRC — LifeComp](https://publications.jrc.ec.europa.eu/repository/handle/JRC120911).
- [JRC — GreenComp](https://publications.jrc.ec.europa.eu/repository/handle/JRC128040).
- [Comisión Europea — portal ESCO](https://esco.ec.europa.eu/en).
- [Consejo de Europa — Marco común europeo de referencia para las lenguas](https://www.coe.int/en/web/common-european-framework-reference-languages).

### 2.3 Tabla maestra de las 17 categorías

Los códigos y etiquetas se transcriben de `mappings/vocab_map.yml`. Las correspondencias JRC indican la relación principal, no una equivalencia uno-a-uno con CINE-F.

| Índice | Etiqueta canónica exacta | Códigos CINE-F 2013 configurados | Marco europeo principal |
|---:|---|---|---|
| `01` | Ciencia de Datos e Inteligencia Artificial | `0613` | DigComp 2.2 |
| `02` | Redes, Cloud y Ciberseguridad | `0612` | DigComp 2.2 |
| `03` | Programación y Desarrollo de Software | `0613` | DigComp 2.2 |
| `04` | Marketing Digital y Comercio Electrónico | `0414` | DigComp 2.2; EntreComp |
| `05` | Competencias Digitales y Ofimática | `0011` | DigComp 2.2; DigCompEdu |
| `06` | Tecnologías de la Información y la Comunicación (General) | `061` | DigComp 2.2 |
| `07` | Administración de Empresas y Derecho | `04` | EntreComp |
| `08` | Ingeniería, Industria y Construcción | `07` | — |
| `09` | Ciencias Naturales, Matemáticas y Estadística | `05` | — |
| `10` | Sostenibilidad, Medio Ambiente y Agroalimentación | `08` + `052` | GreenComp |
| `11` | Salud y Bienestar | `09` | — |
| `12` | Educación y Pedagogía | `01` | DigCompEdu |
| `13` | Artes, Diseño y Humanidades | `021` + `022` + `0232` | — |
| `14` | Ciencias Sociales, Periodismo e Información | `03` | — |
| `15` | Idiomas | `0231` | MCER |
| `16` | Desarrollo Personal y Habilidades Transversales | `0031` | LifeComp |
| `17` | Hostelería, Turismo y Servicios | `101`–`104` | — |

## 3. Motor Determinista de Clasificación y Reglas de Desambiguación

La implementación está en [`schemas/models.py`](../schemas/models.py), en `normalize_text_for_matching()`, `match_synonym_boundary()` y `resolve_category()`.

1. **Fuentes analizadas:** el modelo reúne el `category_hint` proporcionado, las `keywords` limpias y el título limpio. La pista de categoría se incluye como texto de búsqueda. Si coincide exactamente (sin distinguir mayúsculas ni diacríticos) con una etiqueta `canonical`, esa etiqueta se devuelve directamente.
2. **Normalización de sinónimos y texto:** `normalize_text_for_matching()` convierte a minúsculas, aplica Unicode NFKD y elimina caracteres combinantes (diacríticos). No traduce, no lematiza, no convierte sinónimos a conceptos y no elimina puntuación.
3. **Fronteras léxicas:** `match_synonym_boundary()` busca el patrón normalizado con una frontera definida por la ausencia de letras ASCII `a-z` o dígitos `0-9` a ambos lados. Así evita que un sinónimo corto como `ia` coincida dentro de `historia`. Puntuación y espacios pueden servir como fronteras.
4. **Especificidad:** se evalúan las coincidencias contra category hint, keywords y título. Entre coincidencias se conserva el sinónimo de mayor longitud tras normalización. Por eso `gestión del tiempo` vence a `gestión` cuando ambos aparecen. No hay análisis contextual más profundo que este criterio léxico.
5. **Desempate:** si dos categorías producen patrones de igual longitud, gana la primera que aparece en `categories` de `vocab_map.yml`; el iterador solo reemplaza una coincidencia cuando la longitud es estrictamente mayor. El orden actual corresponde a `01`–`17` de la tabla maestra.
6. **Centinela:** si no hay coincidencia, el resultado es `Pendiente_Categoria`. El modelo lo incluye en `Course.category`, activa el motivo de revisión y lo conserva en `_cursodex_meta.category`. El exportador Omeka omite las propiedades RDF públicas `schema:about` y `dcterms:subject` hasta que exista una categoría curada.

### 3.1 Límites de la inferencia léxica

- Una coincidencia indica que una cadena configurada aparece en el texto; no demuestra que esa sea la materia principal del curso.
- Las keywords también intervienen: una etiqueta secundaria puede clasificar un curso si es la coincidencia más larga.
- La categoría canónica exacta recibida como `category_hint` tiene prioridad absoluta, aunque otras keywords sugieran otra disciplina.
- Los sinónimos cortos y polisémicos (por ejemplo `art`, `c`, `r`, `it`, `business`, `office`, `services`) requieren revisión del contexto. Las fronteras evitan coincidencias dentro de palabras, no la ambigüedad entre palabras completas.
- En los listados por categoría de la sección 4, los términos se presentan agrupados como español, inglés o técnico/internacional. Se muestran una sola vez cuando un mismo literal aparece duplicado en el YAML; la comparación de normalización descrita arriba determina su efecto.
- Se conservan las grafías de configuración, incluso cuando una entrada no lleva tilde. No se deben corregir los literales de este inventario sin modificar y probar `vocab_map.yml`.

## 4. Desglose Detallado de las 17 Categorías Canónicas

Cada ficha usa la misma estructura para facilitar su lectura, extracción y mantenimiento. Los ejemplos pedagógicos de rutas son orientación curatorial; no constituyen prerrequisitos codificados salvo que aparezcan en `schema:coursePrerequisites`.

### 01. Ciencia de Datos e Inteligencia Artificial

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Ciencia de Datos e Inteligencia Artificial`

#### Anclaje normativo

CINE-F `0613` (desarrollo y análisis de software y aplicaciones, dentro de TIC). Marco principal: DigComp 2.2. Los términos de medio ambiente o matemáticas generales no bastan para asignar esta categoría.

#### Qué incluye (Alcance disciplinar)

Ciencia e ingeniería de datos, análisis y analítica, minería de datos, Big Data, aprendizaje automático y profundo, inteligencia artificial generativa, procesamiento del lenguaje natural y visión artificial. Herramientas como Power BI, Tableau, Pandas, scikit-learn, TensorFlow y PyTorch son indicadores granulares.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- La palabra genérica `data`/`datos` no es disparador. Migración de datos o datos de infraestructura sin señal analítica se clasifica por el dominio más específico (por ejemplo Azure/cloud → `#02`).
- Programación de propósito general o desarrollo de software → `#03`; la especialidad de ciencia/IA prevalece cuando hay disparadores específicos más largos.
- Cursos generales de matemáticas/estadística → `#09` cuando no exista una señal de analítica, ciencia de datos o IA.
- Medio ambiente, agricultura y sostenibilidad → `#10`, aunque el curso use datos como herramienta.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `ciencia de datos`; `inteligencia artificial`; `ia`; `aprendizaje automatico`; `aprendizaje profundo`; `redes neuronales`; `mineria de datos`; `analisis de datos`; `analitica de datos`; `procesamiento de lenguaje natural`; `vision artificial`; `ia generativa`; `ingenieria de datos` |
| EN | `data science`; `artificial intelligence`; `ai`; `machine learning`; `deep learning`; `neural networks`; `big data`; `data mining`; `data analysis`; `data analytics`; `business intelligence`; `nlp`; `natural language processing`; `computer vision`; `llm`; `generative ai`; `genai`; `data engineer`; `data engineering` |
| Técnico / herramientas | `power bi`; `tableau`; `pandas`; `scikit-learn`; `tensorflow`; `pytorch` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** alfabetización de datos y estadística → análisis y visualización → ingeniería de datos o fundamentos de ML → ML/IA especializado. Usa `educationalLevel` como orden aproximado y los prerrequisitos declarados como restricciones.
- **Adyacencias útiles:** `#03` para programar modelos; `#09` para fundamentos matemáticos/estadísticos; `#02` para infraestructura y seguridad de plataformas; `#07` para aplicaciones de negocio.
- **Evitar:** unir cursos solo por la palabra `data`; no mezclar analítica ambiental con cursos de infraestructura sin confirmar que el objetivo pedagógico sea común.

### 02. Redes, Cloud y Ciberseguridad

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Redes, Cloud y Ciberseguridad`

#### Anclaje normativo

CINE-F `0612` (diseño y administración de bases de datos y redes; subcampo de TIC). Marco principal: DigComp 2.2, especialmente seguridad y uso responsable de tecnología.

#### Qué incluye (Alcance disciplinar)

Redes, administración de sistemas, cloud computing, ciberseguridad, seguridad de redes, criptografía, firewalls, VPN, hacking ético, SOC, DevOps, contenedores, Kubernetes, Cisco Packet Tracer, Azure, AWS y Google Cloud. Incluye operación y migración cloud, protección/compliance y observabilidad de servicios y aplicaciones.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Un `virtual environment`, `cloud environment` o `development environment` describe un entorno tecnológico, no medio ambiente natural: clasifica por la tecnología identificada (normalmente `#02` o `#03`), nunca por `#10` solo por la palabra *environment*.
- Implementación de software sin foco de redes, operaciones o seguridad → `#03`.
- Operación de sistemas de escritorio, Intune, soporte técnico y administración de endpoints → `#06`; en especial los patrones de dispositivo y producto más específicos vencen a señales genéricas de negocio o rol.
- El nombre de un rol (`administrator`, `business owner`, `technology manager`) no debe dominar un título o señal de producto más específica. Microsoft Learn evalúa conjuntamente `title + subjects + products` mediante la coincidencia léxica más larga de `resolve_category()` y recurre a `roles` solo si esas señales de contenido no clasifican.
- `Course` clasifica con la pista de categoría, keywords y título; no busca sinónimos en la descripción. Microsoft Learn aplica la misma prioridad por especificidad al título, las materias y los productos; los roles son respaldo, no evidencia temática preferente.
- Gobierno o estrategia empresarial de servicios cloud sin tema técnico puede pertenecer a `#07`; evita clasificar por el nombre del producto sin revisar el objetivo del curso.
- Sostenibilidad de centros de datos → `#10` solo cuando el objeto de estudio sea sostenibilidad/impacto ambiental, no la infraestructura en sí.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `ciberseguridad`; `seguridad informatica`; `computacion en la nube`; `redes`; `redes de computadoras`; `seguridad de redes`; `hacking etico`; `criptografia`; `administracion de sistemas`; `administracion de redes`; `internet de las cosas`; `migracion a azure`; `migracion a la nube`; `observabilidad cloud`; `solucionar problemas de aplicaciones en azure`; `aplicaciones en azure` |
| EN | `cybersecurity`; `information security`; `cloud computing`; `networking`; `computer networks`; `network security`; `ethical hacking`; `cryptography`; `cloud migration`; `insider risk` |
| Técnico / productos | `cloud`; `azure`; `aws`; `amazon web services`; `google cloud`; `gcp`; `cisco`; `ccna`; `ccnp`; `pentesting`; `soc`; `firewall`; `vpn`; `kubernetes`; `docker`; `devops`; `sysadmin`; `linux`; `iot`; `cisco packet tracer`; `packet tracer`; `purview`; `microsoft purview`; `azure monitor`; `application insights`; `entra`; `defender` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** fundamentos de redes/sistemas → administración cloud → seguridad/operaciones especializadas. No asumir que una certificación o nivel profesional es equivalente a `Avanzado` sin dato de origen.
- **Adyacencias útiles:** `#03` para automatización y scripting; `#06` para fundamentos TIC; `#01` para infraestructura de IA; `#08` para automatización industrial/IoT si el curso relaciona ambos dominios.
- **Evitar:** agrupar por las palabras `services` o `environment` sin el contexto técnico; no usar `#10` por la mera aparición de *environment*.
- Las señales `data analytics` clasifican como `#01`; en una ficha de observabilidad de Azure, patrones de contenido más específicos como `azure monitor`, `application insights` o `aplicaciones en azure` prevalecen globalmente. Una señal de rol como `analytics` solo se usa como respaldo si título, materias y productos no clasifican.

### 03. Programación y Desarrollo de Software

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Programación y Desarrollo de Software`

#### Anclaje normativo

CINE-F `0613` (desarrollo y análisis de software y aplicaciones, dentro del campo `06` TIC). DigComp 2.2 aporta competencias digitales relacionadas con creación de contenido digital y programación.

#### Qué incluye (Alcance disciplinar)

Programación, ingeniería y desarrollo de software, desarrollo web/backend/frontend/móvil/full-stack, algoritmos, estructuras de datos, APIs, frameworks, sistemas de control de versiones, lenguajes de programación y bases de datos cuando el foco sea implementarlos.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Redes, infraestructura cloud, contenedores u operaciones como objetivo principal → `#02`.
- Analítica, ciencia de datos o aprendizaje automático como objetivo principal → `#01`; una herramienta de programación mencionada como medio no cambia el dominio.
- Alfabetización digital y uso de aplicaciones de oficina → `#05`; conceptos generales de TIC → `#06`.
- `web services`, `cloud services`, `Azure services` y `microservicios` no son servicios turísticos; los dos últimos son indicios de software/cloud, según el contenido.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `programacion`; `desarrollo de software`; `desarrollo web`; `desarrollo backend`; `desarrollo frontend`; `desarrollo movil`; `desarrollo full stack`; `algoritmos`; `estructuras de datos`; `arquitectura de software`; `ingenieria de software` |
| EN | `programming`; `software development`; `web development`; `backend development`; `frontend development`; `mobile development`; `algorithms`; `data structures`; `software engineering` |
| Técnico / lenguajes | `fullstack`; `python`; `javascript`; `typescript`; `java`; `c#`; `c++`; `c`; `php`; `ruby`; `rust`; `golang`; `go`; `swift`; `kotlin`; `f#`; `fsharp`; `f sharp`; `dotnet`; `r`; `sql`; `html`; `css`; `react`; `angular`; `vue`; `node.js`; `nodejs`; `django`; `flask`; `spring boot`; `git`; `github`; `apis`; `api rest`; `graphql` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** fundamentos de programación → control de flujo/estructuras de datos → herramientas y pruebas → desarrollo especializado (web, móvil, backend, etc.).
- **Adyacencias útiles:** `#02` para despliegue/DevOps; `#01` para programación aplicada a datos/IA; `#06` para fundamentos de computación; `#08` si se trata de software embebido o automatización.
- **Evitar:** no mezclar un curso de programación con uno de operación de infraestructura solo por tener un lenguaje o plataforma en sus keywords; usar objetivos y prerrequisitos.

### 04. Marketing Digital y Comercio Electrónico

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Marketing Digital y Comercio Electrónico`

#### Anclaje normativo

CINE-F `0414` (marketing y publicidad), dentro de `04` Administración de empresas y derecho. DigComp 2.2 y EntreComp aportan referencias complementarias para el uso digital y la creación de valor.

#### Qué incluye (Alcance disciplinar)

Marketing digital, comercio electrónico, posicionamiento, publicidad en plataformas digitales, inbound/content/email marketing, redes sociales, analítica web, copywriting, CRM y ventas digitales.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Administración, finanzas, ventas generales o emprendimiento sin énfasis digital → `#07`.
- Desarrollo de la tienda, software o APIs → `#03`; operación cloud o redes → `#02`.
- La etiqueta `hubspot` está configurada como disparador de marketing por su función temática, no como proveedor activo.
- No confundir `analitica web` con analítica/ciencia de datos general (`#01`); gana el patrón más largo coincidente.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `marketing digital`; `comercio electronico`; `posicionamiento web`; `marketing de contenidos`; `redes sociales`; `analitica web`; `ventas digitales`; `publicidad digital` |
| EN | `digital marketing`; `inbound marketing`; `content marketing`; `social media marketing`; `email marketing`; `growth hacking` |
| Técnico / plataformas | `ecommerce`; `e-commerce`; `seo`; `sem`; `google ads`; `meta ads`; `facebook ads`; `google analytics`; `copywriting`; `crm`; `hubspot` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** fundamentos de marketing/cliente → contenido y canales → analítica/optimización → comercio electrónico o campañas especializadas.
- **Adyacencias útiles:** `#07` para negocio, ventas y emprendimiento; `#01` para analítica; `#05` para herramientas de productividad; `#03` para desarrollo de plataformas.
- **Evitar:** no ordenar cursos de programación o administración como parte obligatoria del itinerario de marketing sin prerrequisito explícito o una meta interdisciplinar documentada.

### 05. Competencias Digitales y Ofimática

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Competencias Digitales y Ofimática`

#### Anclaje normativo

CINE-F `0011` (programas y cualificaciones básicos) como aproximación operativa a competencias digitales básicas; DigComp 2.2 es la referencia ciudadana principal. DigCompEdu puede orientar el uso de estas competencias en docencia.

#### Qué incluye (Alcance disciplinar)

Alfabetización digital, uso básico y productivo de Internet, ofimática, hojas de cálculo, herramientas colaborativas, Microsoft 365, Google Workspace y aplicaciones de productividad.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- TIC generales o fundamentos de sistemas/telecomunicaciones → `#06`.
- Desarrollo de software, programación o automatización codificada → `#03`.
- Administración técnica de sistemas o ciberseguridad → `#02`.
- El literal `productividad personal` aparece tanto aquí como en `#16`; al tener igual longitud, gana `#05` por aparecer antes en el YAML. `personal productivity` (inglés) está configurado en `#16`.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `competencias digitales`; `alfabetizacion digital`; `ofimatica`; `hojas de calculo`; `productividad personal`; `mecanografia`; `computacion basica`; `uso de internet`; `herramientas colaborativas` |
| EN | `digital skills`; `digital literacy`; `spreadsheets` |
| Técnico / aplicaciones | `office`; `microsoft office`; `microsoft 365`; `excel`; `word`; `powerpoint`; `google sheets`; `google docs`; `google workspace`; `zoom`; `teams`; `power platform`; `power apps` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** alfabetización digital → archivos, ofimática y colaboración → herramientas específicas o competencias digitales avanzadas.
- **Adyacencias útiles:** `#06` como fundamentos conceptuales, `#12` para integración pedagógica y `#07` para tareas administrativas.
- **Evitar:** no convertir automáticamente todo curso de tecnología en ofimática; usar `#02`, `#03` o `#06` cuando el curso trate el funcionamiento técnico.

### 06. Tecnologías de la Información y la Comunicación (General)

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Tecnologías de la Información y la Comunicación (General)`

#### Anclaje normativo

CINE-F `061`, campo detallado general de TIC. Es la categoría residual de informática/TIC cuando los disparadores no permiten asignar una de las especialidades digitales `#01`–`#05`.

#### Qué incluye (Alcance disciplinar)

Fundamentos de informática, computación, tecnologías de información, sistemas de información y telecomunicaciones de carácter general; sistemas operativos de escritorio/cliente, administración de dispositivos y endpoints, soporte técnico y modern desktop.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Datos/IA → `#01`; redes/cloud/seguridad → `#02`; programación y desarrollo → `#03`; marketing digital → `#04`; competencias digitales/ofimática → `#05`.
- No clasificar como ofimática (`#05`) la administración/soporte de Windows, Intune o endpoints: esos temas técnicos quedan en `#06`. El uso básico de Word, Excel y Microsoft 365 continúa en `#05`.
- Infraestructura cloud, redes, ciberseguridad, Purview y observabilidad cloud → `#02`.
- `administracion de sistemas` está configurado tanto en `#02` como aquí. Al empatar su longitud, el orden YAML conserva la resolución en `#02`; una señal de escritorio/endpoint más específica como `windows 11 pro` o `endpoint management` resuelve `#06`.
- La descripción no participa en el matching de categoría del modelo. Las señales deben aparecer en título, keywords o pista; en Microsoft Learn una señal de subject/product más específica evita que una coincidencia secundaria de rol clasifique antes.
- No usar esta categoría solo porque el curso se imparta mediante tecnología; debe tratar de TIC como materia.
- `IT`, `tic`, `technology` e `informatica` son disparadores cortos o amplios: revisar siempre el texto completo y el orden de especificidad.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `tecnologias de la informacion`; `tic`; `informatica`; `ciencias de la computacion`; `computacion`; `tecnologia`; `sistemas de informacion`; `telecomunicaciones`; `windows 11`; `windows 11 pro`; `windows 10`; `sistema operativo`; `sistemas operativos`; `administracion de dispositivos`; `gestion de dispositivos`; `administracion de sistemas`; `soporte tecnico` |
| EN | `information technology`; `it`; `computer science`; `technology`; `telecommunications`; `operating system`; `operating systems`; `linux desktop`; `help desk`; `it support`; `device management`; `endpoint management`; `modern desktop` |
| Técnico / productos | `macos`; `intune`; `microsoft intune` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** fundamentos de computación/TIC → especialización posterior en una de `#01`–`#05`.
- **Adyacencias útiles:** las cinco categorías digitales especializadas; escoger una según `keywords`, prerrequisitos y objetivo formativo.
- **Evitar:** no mezclar automáticamente cursos de distintas especializaciones solo porque comparten `#06`; aplicar un filtro más fino por `schema:keywords`.

### 07. Administración de Empresas y Derecho

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Administración de Empresas y Derecho`

#### Anclaje normativo

CINE-F `04` (administración de empresas y derecho; incluye áreas como negocios/administración `041` y derecho `042`). EntreComp es un marco complementario para emprendimiento.

#### Qué incluye (Alcance disciplinar)

Administración, gestión empresarial, emprendimiento, finanzas, contabilidad, economía, derecho, recursos humanos, liderazgo organizativo, negocios, comercio, gestión de proyectos, ventas y metodologías de trabajo.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Marketing y comercio electrónico como especialidad digital → `#04`.
- Habilidades personales, gestión del tiempo o comunicación interpersonal → `#16`, cuando el objetivo sea individual/transversal y no la dirección de una empresa o equipo.
- Atención al cliente operativa, servicio al huésped o comedor → `#17`; administración de la función comercial → permanece en `#07`.
- `financial services` no es un disparador de servicios hosteleros: tampoco aparece como sinónimo configurado. No inferir `#17` por la palabra inglesa *services*.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `administracion`; `gestion empresarial`; `gestion`; `emprendimiento`; `finanzas`; `contabilidad`; `economia`; `derecho`; `leyes`; `recursos humanos`; `liderazgo`; `negocios`; `comercio`; `gestion de proyectos`; `ventas`; `atencion al cliente` |
| EN | `business`; `business administration`; `microsoft 365 business`; `management`; `entrepreneurship`; `finance`; `accounting`; `economics`; `law`; `legal`; `human resources`; `leadership`; `project management`; `customer service` |
| Técnico / metodologías | `pmp`; `scrum`; `agile` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** fundamentos de negocio → área funcional (finanzas, RR. HH., derecho, etc.) → gestión de proyectos o especialización. Emprendimiento puede constituir una rama paralela.
- **Adyacencias útiles:** `#04` para marketing; `#16` para habilidades de liderazgo personal; `#05` para herramientas de oficina; `#01` para analítica empresarial.
- **Evitar:** no inferir prerrequisitos de dirección empresarial a partir de una coincidencia aislada con `leadership` o `management`; el sistema de matching no distingue por sí solo liderazgo personal de organizativo.

### 08. Ingeniería, Industria y Construcción

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Ingeniería, Industria y Construcción`

#### Anclaje normativo

CINE-F `07` (ingeniería, industria y construcción), que comprende ingeniería y disciplinas técnicas, fabricación/procesamiento y arquitectura/construcción.

#### Qué incluye (Alcance disciplinar)

Ingeniería mecánica, eléctrica, electrónica, civil, industrial y química; robótica, automatización, mecatrónica, arquitectura, construcción, diseño industrial, fabricación, manufactura y electricidad.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Matemáticas, física o química como materias generales → `#09`; si son aplicación de una ingeniería concreta, mantener `#08`.
- Programación o software como objetivo formativo → `#03`; redes y administración de sistemas → `#02`.
- Agricultura, silvicultura, pesca y veterinaria → `#10`, no ingeniería, salvo que el curso trate específicamente ingeniería industrial aplicada.
- Diseño gráfico, artes visuales y humanidades → `#13`.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `ingenieria`; `ingenieria mecanica`; `ingenieria electrica`; `ingenieria electronica`; `ingenieria civil`; `ingenieria industrial`; `ingenieria quimica`; `robotica`; `automatizacion`; `electronica`; `mecatronica`; `arquitectura`; `construccion`; `diseno industrial`; `fabricacion`; `manufactura`; `electricidad` |
| EN | `engineering`; `robotics`; `automation`; `architecture`; `construction` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** fundamentos científicos/técnicos → herramientas y procesos del área → diseño o aplicación especializada.
- **Adyacencias útiles:** `#09` para fundamentos científicos; `#03` y `#02` para automatización conectada; `#10` cuando el curso se centre en producción agroalimentaria o sostenibilidad.
- **Evitar:** no concatenar un curso de programación con ingeniería aplicada únicamente porque ambos mencionen automatización; confirmar el objetivo y los prerrequisitos.

### 09. Ciencias Naturales, Matemáticas y Estadística

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Ciencias Naturales, Matemáticas y Estadística`

#### Anclaje normativo

CINE-F `05` (ciencias naturales, matemáticas y estadística), que agrupa ciencias biológicas, medio ambiente (`052`), ciencias físicas y matemáticas/estadística. El vocabulario local da prioridad ambiental específica a `#10`.

#### Qué incluye (Alcance disciplinar)

Matemáticas, cálculo, álgebra, geometría, probabilidad, estadística, física, química, biología, geología y astronomía cuando se enseñen como disciplinas generales.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Ecología, sostenibilidad y ciencias ambientales → `#10`; el código oficial `052` se incorpora en esa categoría, no se deja en esta faceta general.
- Analítica o ciencia de datos aplicada → `#01`, si hay disparadores específicos de datos/IA.
- Matemáticas o estadística como herramienta dentro de otra disciplina pueden conservarse en `keywords` mientras la categoría principal refleje el objetivo del curso.
- Salud y ciencias clínicas → `#11`.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `matematicas`; `estadistica`; `fisica`; `quimica`; `biologia`; `geologia`; `astronomia`; `calculo`; `algebra`; `geometria`; `probabilidad` |
| EN | `mathematics`; `math`; `statistics`; `physics`; `chemistry`; `biology`; `geology`; `astronomy` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** fundamentos matemáticos/científicos → métodos cuantitativos o disciplina específica → aplicación avanzada.
- **Adyacencias útiles:** `#01` para estadística aplicada a datos; `#08` para ingeniería; `#10` para ciencias ambientales; `#11` para ciencias de salud.
- **Evitar:** no hacer de toda ruta con una palabra científica una combinación de disciplinas; filtrar por categoría y usar `keywords` para similitud fina.

### 10. Sostenibilidad, Medio Ambiente y Agroalimentación

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Sostenibilidad, Medio Ambiente y Agroalimentación`

#### Anclaje normativo

CINE-F campo amplio `08` (agricultura, silvicultura, pesca y veterinaria) más `052` (medio ambiente). GreenComp es el marco europeo complementario principal.

#### Qué incluye (Alcance disciplinar)

Sostenibilidad y desarrollo sostenible; cambio climático, ecología, biodiversidad, ciencias ambientales, agua y residuos; reciclaje, economía circular y energías renovables; agricultura, producción agroalimentaria, silvicultura, pesca, veterinaria, horticultura, huertos, permacultura y agroecología.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- `virtual environment`, `cloud environment`, `development environment` o `entorno de desarrollo` no son medio ambiente natural. `environment` sin un patrón ambiental configurado no activa esta categoría.
- Un curso de redes/cloud o ciberseguridad → `#02`; programación y herramientas de desarrollo → `#03`.
- Ciencias naturales generales → `#09`; un curso de biología ambiental o ecología con disparadores específicos se enruta aquí por el patrón más largo/temático.
- La categoría agrupa campos CINE-F `08` y `052` para fines de catálogo; no implica que agricultura y cambio climático sean equivalentes.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `sostenibilidad`; `desarrollo sostenible`; `cambio climático`; `ecología`; `biodiversidad`; `medio ambiente`; `medio ambiente y sostenibilidad`; `ciencias ambientales`; `gestion del agua`; `recursos hidricos`; `gestion de residuos`; `residuos`; `reciclaje`; `economía circular`; `energías renovables`; `energía renovable`; `energías limpias`; `agricultura`; `agroalimentación`; `agroalimentaria`; `agropecuario`; `agropecuaria`; `silvicultura`; `pesca`; `veterinaria`; `huertos`; `huerto`; `horticultura`; `permacultura`; `agroecología` |
| EN | `sustainable development`; `sustainability`; `climate change`; `ecology`; `biodiversity`; `environmental science`; `environmental studies`; `nature & environment`; `nature and environment`; `water management`; `water resources`; `waste management`; `recycling`; `circular economy`; `renewable energy`; `clean energy`; `agriculture`; `farming`; `forestry`; `fishing`; `veterinary`; `horticulture`; `permaculture`; `agroecology` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** alfabetización/competencias de sostenibilidad → fundamentos ambientales o agroalimentarios → prácticas, gestión o especialización sectorial.
- **Adyacencias útiles:** `#09` para ciencias naturales; `#08` para ingeniería/energía; `#01` para análisis ambiental; `#07` para economía circular y gestión.
- **Evitar:** no unir cursos por el token genérico `environment`; excluir explícitamente entornos virtuales/cloud/de desarrollo. Separar rutas de agricultura, ecología y energía cuando no exista un objetivo común.

### 11. Salud y Bienestar

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Salud y Bienestar`

#### Anclaje normativo

CINE-F `09` (salud y bienestar), incluidos ámbitos de salud y bienestar social. La etiqueta canónica es una categoría operativa única.

#### Qué incluye (Alcance disciplinar)

Salud, medicina, enfermería, farmacia, nutrición, dietética, psicología, salud mental, fisioterapia, primeros auxilios, epidemiología, salud pública, odontología y bienestar.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Coaching, inteligencia emocional o habilidades transversales sin objeto clínico/sanitario → `#16`.
- Educación de profesionales o pedagogía sanitaria como objetivo principal → `#12`; el contenido clínico continúa en `#11`.
- Seguridad e higiene laboral / prevención de riesgos laborales → `#17` por el anclaje de servicios de higiene/seguridad configurado en CINE-F `102`.
- Veterinaria → `#10`, conforme al campo CINE-F `08` asignado por el proyecto.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `salud`; `medicina`; `enfermeria`; `farmacia`; `nutricion`; `dietetica`; `psicologia`; `salud mental`; `fisioterapia`; `primeros auxilios`; `epidemiologia`; `salud publica`; `odontologia`; `bienestar` |
| EN | `health`; `medicine`; `nursing`; `pharmacy`; `nutrition`; `psychology`; `mental health`; `first aid`; `public health`; `wellness` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** fundamentos del área sanitaria → conocimiento o práctica específica → especialización; respetar prerrequisitos profesionales y requisitos de seguridad.
- **Adyacencias útiles:** `#09` para ciencias biomédicas; `#12` para formación docente/sanitaria; `#16` para bienestar no clínico.
- **Evitar:** no crear rutas clínicas a partir de cursos de bienestar general sin evaluar credenciales, alcance y requisitos profesionales.

### 12. Educación y Pedagogía

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Educación y Pedagogía`

#### Anclaje normativo

CINE-F `01` (educación y formación). DigCompEdu es referencia principal para competencia digital docente; la etiqueta no representa por sí misma el nivel educativo del alumnado.

#### Qué incluye (Alcance disciplinar)

Educación, pedagogía, didáctica, docencia, formación docente, e-learning, tecnología educativa, evaluación y orientación educativa, y niveles de educación infantil, primaria y secundaria.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Aprender una lengua extranjera → `#15`, aunque el curso use un formato educativo.
- Aprender ofimática o herramientas digitales como estudiante → `#05`; formación docente en el uso pedagógico de tecnología → `#12` si ese es el objetivo explícito.
- Curso sobre una materia (por ejemplo programación) impartido en línea no es automáticamente educación/pedagogía; clasificar por contenido, no por modalidad.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `educacion`; `pedagogia`; `didactica`; `docencia`; `formacion docente`; `tecnologia educativa`; `evaluacion educativa`; `orientacion educativa`; `educacion infantil`; `educacion primaria`; `educacion secundaria` |
| EN / técnico | `education`; `pedagogy`; `teaching`; `elearning`; `e-learning`; `edtech` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** fundamentos pedagógicos → diseño didáctico/evaluación → especialización por etapa, modalidad o competencia digital docente.
- **Adyacencias útiles:** `#05` para herramientas; `#15` para enseñanza de lenguas solo si se registra el objetivo lingüístico; `#16` para aprender a aprender.
- **Evitar:** no ordenar cursos de una materia como prerrequisito pedagógico solo porque `teaching` aparezca incidentalmente.

### 13. Artes, Diseño y Humanidades

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Artes, Diseño y Humanidades`

#### Anclaje normativo

CINE-F `021` (artes) + `022` (humanidades, excepto idiomas) + **`0232` (literatura y lingüística)**. La asignación `0232` es explícita: Filología, Literatura, Lingüística, crítica literaria y Humanidades Digitales pertenecen a esta categoría.

#### Qué incluye (Alcance disciplinar)

Artes visuales y escénicas, historia, filosofía, filología, lingüística, literatura, estudios clásicos, crítica literaria, escritura creativa, humanidades digitales, música, diseño gráfico, fotografía, cine, animación, teatro, danza, patrimonio, arqueología, religión, teología, dibujo y pintura.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Aprendizaje/adquisición de una lengua extranjera, gramática práctica L2 y cursos MCER → `#15` (`0231`).
- Un título como *English literature* se clasifica aquí: `literature` es un disparador más largo que `english`. *Filología hispánica* y *Humanidades Digitales* son también `#13`.
- La traducción y la interpretación aparecen como disparadores configurados en `#15`; si el curso trata teoría, historia o análisis lingüístico/literario, revisar manualmente el resultado.
- Ciencias sociales, periodismo e información → `#14`; diseño industrial → `#08`.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `arte`; `artes visuales`; `historia`; `filosofia`; `filología`; `lingüística`; `literatura`; `crítica literaria`; `estudios literarios`; `musica`; `diseno grafico`; `fotografia`; `cine`; `animacion`; `artes escenicas`; `teatro`; `danza`; `patrimonio`; `arqueologia`; `religion`; `teologia`; `escritura creativa`; `humanidades digitales`; `estudios clásicos`; `dibujo`; `pintura` |
| EN | `art`; `history`; `philosophy`; `philology`; `linguistics`; `literature`; `literary criticism`; `literary studies`; `music`; `graphic design`; `photography`; `creative writing`; `digital humanities`; `classical studies` |
| Técnico / internacional | `audiovisual` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** fundamentos de la disciplina → lectura/análisis o práctica creativa → especialización en periodo, medio, lengua o método.
- **Adyacencias útiles:** `#14` para historia cultural/medios; `#15` para rutas de adquisición lingüística separadas; `#12` para pedagogía de las artes/literatura.
- **Evitar:** no unir cursos de literatura con cursos de idioma solo por el gentilicio o el nombre de la lengua. La distinción `0232`/`0231` depende del objetivo: estudiar textos/lenguaje frente a adquirir una lengua.

### 14. Ciencias Sociales, Periodismo e Información

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Ciencias Sociales, Periodismo e Información`

#### Anclaje normativo

CINE-F `03` (ciencias sociales, periodismo e información), con ciencias sociales/conductuales, periodismo e información.

#### Qué incluye (Alcance disciplinar)

Ciencias sociales, sociología, ciencia política, relaciones internacionales, antropología, periodismo, comunicación, medios de comunicación, biblioteconomía, documentación, archivística y geografía.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Historia, filosofía y humanidades → `#13`; aprendizaje de lenguas → `#15`.
- Comunicación interpersonal, hablar en público o pensamiento crítico como habilidades transversales → `#16`; periodismo y sistemas de información pública → `#14`.
- Sistemas de información empresariales o telecomunicaciones → `#06` si son TIC como materia.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `ciencias sociales`; `sociologia`; `ciencias politicas`; `politica`; `relaciones internacionales`; `antropologia`; `periodismo`; `comunicacion`; `medios de comunicacion`; `biblioteconomia`; `documentacion`; `archivistica`; `geografia` |
| EN | `social sciences`; `sociology`; `political science`; `international relations`; `anthropology`; `journalism`; `communication`; `geography` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** conceptos/metodologías de ciencias sociales → métodos o campo aplicado → especialización (periodismo, política pública, archivística, etc.).
- **Adyacencias útiles:** `#13` para historia/humanidades; `#07` para políticas de empresa; `#01` para métodos cuantitativos y análisis de datos; `#16` para comunicación como competencia transversal.
- **Evitar:** no mezclar una ruta de habilidades blandas con una ruta disciplinar social basándose únicamente en `communication`.

### 15. Idiomas

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Idiomas`

#### Anclaje normativo

CINE-F `0231` (adquisición de idiomas). Referencia europea: MCER/CEFR. Esta categoría se reserva conceptualmente a aprendizaje, adquisición y práctica de una lengua; el modelo no calcula niveles MCER A1–C2.

#### Qué incluye (Alcance disciplinar)

Aprendizaje y adquisición de lenguas extranjeras, vocabulario y gramática práctica L2, práctica oral, pronunciación y aprendizaje de inglés, francés, alemán, español, italiano, portugués, chino o japonés.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Literatura inglesa/española, Filología, Lingüística, crítica literaria y Humanidades Digitales → `#13` (`0232`), no `#15`.
- El motor sí conserva `traduccion`, `translation`, `interpretacion` y `gramatica` como disparadores de esta categoría; para cursos profesionales de traducción o estudios teóricos, validar el objetivo y corregir la categoría si procede.
- El nombre de la lengua del contenido (`inLanguage`) no basta para clasificar el curso aquí.
- No confundir un curso de idioma con educación de idiomas para docentes (`#12`) cuando el objetivo sea la metodología de enseñanza.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `idiomas`; `aprendizaje de idiomas`; `aprendizaje de lenguas`; `aprendizaje de lenguas extranjeras`; `lengua extranjera`; `lenguas extranjeras`; `aprendizaje del inglés`; `aprendizaje del francés`; `aprendizaje del alemán`; `aprendizaje del español`; `francés como lengua extranjera`; `alemán como lengua extranjera`; `español como lengua extranjera`; `vocabulario en ingles`; `vocabulario l2`; `gramática inglesa`; `gramática l2`; `gramática francesa`; `gramática alemana`; `practica de conversacion`; `pronunciacion inglesa`; `ingles`; `espanol`; `frances`; `aleman`; `italiano`; `portugues`; `chino`; `japones`; `traduccion`; `interpretacion`; `gramatica`; `vocabulario`; `pronunciacion` |
| EN | `languages`; `language learning`; `language acquisition`; `foreign language acquisition`; `second language acquisition`; `foreign language learning`; `foreign languages`; `english language learning`; `learning english`; `learning french`; `learning german`; `learning spanish`; `english vocabulary`; `l2 vocabulary`; `english grammar`; `l2 grammar`; `language practice`; `english pronunciation`; `english`; `spanish`; `french`; `german`; `italian`; `portuguese`; `chinese`; `japanese`; `translation` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** identificar lengua objetivo y nivel de partida → vocabulario/gramática/práctica inicial → comunicación y comprensión → progresión MCER solo si la fuente declara el nivel.
- **Adyacencias útiles:** `#12` para didáctica de lenguas; `#13` para literatura/lingüística si se crean itinerarios interdisciplinares explícitos.
- **Evitar:** no unir cursos de literatura inglesa con cursos de inglés comunicativo por el único token `English`; filtrar `#13` y `#15` como dominios separados antes de similitud por keywords.

### 16. Desarrollo Personal y Habilidades Transversales

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Desarrollo Personal y Habilidades Transversales`

#### Anclaje normativo

CINE-F `0031` (habilidades personales). LifeComp es el marco europeo principal para competencias personales, sociales y de aprender a aprender.

#### Qué incluye (Alcance disciplinar)

Desarrollo y productividad personal, gestión del tiempo, liderazgo personal, inteligencia emocional, habilidades blandas, comunicación interpersonal, oratoria, pensamiento crítico, técnicas de estudio, aprendizaje autónomo, empleabilidad, CV, búsqueda de empleo, deportes y fitness según los disparadores actuales.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- Gestión empresarial, liderazgo organizativo, gestión de proyectos y administración → `#07`; `#16` se centra en el desarrollo individual/transversal.
- Atención al cliente operativa, hostelería, transporte y seguridad laboral → `#17`.
- El literal español `productividad personal` aparece en `#05` y `#16`, con igual longitud; por el orden YAML gana `#05`. `personal productivity` está configurado en `#16`.
- `liderazgo`/`leadership` genéricos aparecen en `#07`; `liderazgo personal`/`personal leadership` son disparadores más específicos de esta categoría.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `desarrollo personal`; `autoayuda`; `productividad personal`; `gestion del tiempo`; `liderazgo personal`; `inteligencia emocional`; `habilidades blandas`; `comunicacion interpersonal`; `oratoria`; `pensamiento critico`; `tecnicas de estudio`; `aprendizaje autonomo`; `empleabilidad`; `busqueda de empleo`; `deportes` |
| EN | `personal development`; `personal productivity`; `time management`; `personal leadership`; `emotional intelligence`; `soft skills`; `interpersonal communication`; `public speaking`; `critical thinking`; `study skills`; `self-directed learning`; `employability`; `job search`; `sports`; `fitness` |
| Técnico / internacional | `coaching`; `curriculum vitae` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** diagnóstico/reflexión → competencia personal concreta → práctica/transferencia al estudio o empleo.
- **Adyacencias útiles:** `#12` para aprender a aprender; `#07` para administración/competencias emprendedoras; `#11` para salud mental o bienestar con alcance sanitario.
- **Evitar:** no incorporar gestión de proyectos de empresa como prerrequisito de productividad personal sin evidencia; no fusionar cursos de salud clínica con autoayuda.

### 17. Hostelería, Turismo y Servicios

#### Etiqueta canónica exacta (`CustomVocab:1`)

`Hostelería, Turismo y Servicios`

#### Anclaje normativo

CINE-F `101`–`104`: servicios personales (`101`), higiene y salud laboral (`102`), servicios de seguridad (`103`) y servicios de transporte (`104`).

#### Qué incluye (Alcance disciplinar)

Turismo, hostelería, gastronomía, cocina, panadería, repostería, coctelería, servicio al huésped/comedor, atención al cliente operativa, estética, peluquería, transporte operativo y seguridad e higiene laboral/PRL. El YAML incluye estos disparadores para fuentes como Aprende.org; no implica que todas las materias pertenezcan al mismo itinerario profesional.

#### Fronteras y exclusiones (Qué NO incluye y adónde va)

- `web services`, `cloud services`, `Azure services`, `microservicios` y `financial services` no son disparadores configurados de esta categoría. Un curso de software/cloud → `#02` o `#03`; finanzas/servicios financieros → `#07`.
- `atencion al cliente` genérica está en `#07`; `atencion al cliente operativa` y `operational customer service` son los disparadores de `#17`.
- Salud clínica → `#11`; habilidades de comunicación interpersonal → `#16`.
- Turismo, transporte y seguridad se agrupan por la decisión operativa Cursodex y por campos CINE-F `10`; no se deben concatenar cursos de estos subdominios sin comprobar afinidad y prerrequisitos.

#### Sinónimos y disparadores léxicos configurados (`mappings/vocab_map.yml`)

| Grupo | Literales |
|---|---|
| ES | `turismo`; `hosteleria`; `gastronomia`; `cocina`; `panaderia`; `reposteria`; `cocteleria`; `servicio al huesped`; `servicio de comedor`; `atencion al cliente operativa`; `estetica`; `peluqueria`; `transporte operativo`; `transporte de pasajeros`; `seguridad laboral`; `prevencion de riesgos`; `seguridad e higiene laboral`; `prevencion de riesgos laborales`; `prl` |
| EN | `tourism`; `hospitality`; `gastronomy`; `cooking`; `baking`; `pastry`; `bartender`; `guest service`; `food service`; `operational customer service`; `beauty services`; `hairdressing`; `passenger transport`; `occupational safety`; `occupational health and safety` |

#### Guía para Rutas de Aprendizaje con Python e IA (Hito 4)

- **Progresión sugerida:** fundamentos sectoriales → práctica operativa/seguridad → especialización en turismo, cocina, transporte u otro servicio.
- **Adyacencias útiles:** `#07` para gestión de empresas turísticas; `#16` para habilidades personales; `#11` para contenidos de higiene/salud cuando su objetivo sea clínico.
- **Evitar:** no agrupar por `services` aislado ni por nombres de productos cloud. Mantener itinerarios de turismo, hostelería, estética y transporte diferenciados salvo que exista una competencia común documentada.

## 5. Contrato de Datos para el Analizador de Rutas del Hito 4 (`schema:ItemList`)

### 5.1 Vocabularios de progresión y acceso

#### Niveles educativos (`CustomVocab:2`, convención prevista)

El orden ordinal usado por el consumidor de rutas es:

| Orden | Valor canónico emitido | Literales configurados en `educational_levels` |
|---:|---|---|
| `1` | `Principiante` | `principiante`, `beginner`, `basico`, `básico`, `introductorio`, `introductory`, `iniciacion`, `iniciación`, `starter`, `novice`, `fundamental`, `fundamentos`, `1` |
| `2` | `Intermedio` | `intermedio`, `intermediate`, `medio`, `medium`, `2` |
| `3` | `Avanzado` | `avanzado`, `advanced`, `experto`, `expert`, `profesional`, `master`, `3` |

El valor numérico describe el orden para secuenciar, no una calificación ni un nivel del MCER. El modelo normaliza los literales a una etiqueta española; si no encuentra nivel, la ruta debe tolerar un valor ausente y no inventar un ordinal.

#### Acceso/credencial (`CustomVocab:3`, convención prevista)

| Valor `AccessType` | `credential_label_es` | Interpretación |
|---|---|---|
| `free_with_certificate` | `Certificado gratuito` | Acceso al curso y certificado gratuitos, con evidencia suficiente del proveedor. |
| `free_audit_paid_certificate` | `Acceso gratuito (certificado de pago)` | El contenido puede cursarse gratuitamente; el certificado requiere pago. |
| `free_no_certificate` | `Curso gratuito (sin certificado)` | Acceso gratuito y no se ofrece certificado. |

El filtro anti-pago es independiente de la credencial: un curso cuyo acceso al contenido sea de pago o una prueba temporal no es admisible. Los tres valores describen solo modalidades gratuitas aceptadas. Las etiquetas son las del método `AccessType.credential_label_es`; no se infiere que Omeka ya tenga esos términos instalados.

### 5.2 Reglas de composición para una ruta

El futuro analizador puede serializar un itinerario como `schema:ItemList` y usar los registros de curso existentes como elementos. Este extractor **todavía no genera rutas `ItemList`**; la estructura siguiente es un contrato orientativo para el Hito 4:

```json
{
  "@type": "schema:ItemList",
  "schema:name": "Ruta de aprendizaje",
  "schema:itemListOrder": "https://schema.org/ItemListOrderAscending",
  "schema:itemListElement": [
    {
      "@type": "schema:ListItem",
      "schema:position": 1,
      "schema:item": {
        "@type": "schema:Course",
        "schema:about": "Competencias Digitales y Ofimática",
        "schema:keywords": ["hojas de cálculo", "Excel"],
        "schema:educationalLevel": "Principiante",
        "schema:coursePrerequisites": [],
        "schema:timeRequired": "PT2H"
      }
    }
  ]
}
```

Al construir rutas:

1. **Filtro duro de dominio:** comenzar por la categoría canónica exacta de `schema:about`. No mezclar categorías como si fueran sinónimos. Una ruta interdisciplinar debe declarar su objetivo y las transiciones entre dominios.
2. **Similitud granular:** comparar `schema:keywords` después del filtro. Las herramientas (`Python`, `Excel`, `Azure`) ayudan a ordenar o especializar cursos, pero no anulan el filtro macro.
3. **Secuenciación:** usar `Principiante < Intermedio < Avanzado` como señal ordinal, no como prueba de competencia ni como sustituto de prerrequisitos.
4. **Grafo de dependencias:** interpretar `schema:coursePrerequisites` como texto. Resolver referencias a cursos/temas contra el catálogo antes de crear aristas; conservar la fuente y distinguir dependencias declaradas de inferencias del recomendador.
5. **Duración agregada:** sumar valores `schema:timeRequired` válidos y compatibles como ISO 8601. Si una duración falta o es ambigua, informar una estimación parcial o desconocida; no convertir meses/años calendario a horas mediante una constante arbitraria.
6. **Acceso y revisión:** no incluir recursos que incumplan el filtro gratuito. Excluir o marcar cursos con `needs_review` y categorías `Pendiente_Categoria` hasta su resolución humana.
7. **Trazabilidad:** conservar IDs/URLs canónicas de cada elemento, procedencia de la recomendación y explicación de orden/prerrequisitos. El modelo actual no produce identificadores de ruta ni relaciones de curso resueltas.

### 5.3 Recomendación de consumo desde Python e IA

`mappings/vocab_map.yml` es la fuente parseable para categorías, niveles, idiomas y sinónimos; este documento explica el significado disciplinar. Para construir un itinerario, un consumidor debe cargar los valores desde YAML, filtrar categorías antes de calcular similitud textual y tratar cualquier prerrequisito generado por IA como **propuesta** hasta verificarlo en los datos del proveedor o mediante curaduría. Nunca convertir una sugerencia probabilística en `schema:coursePrerequisites` factual sin evidencia.
