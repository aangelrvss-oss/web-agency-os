# Revisión crítica de la Fase 0 — Web Agency OS

Fecha: 2026-10-19. Idioma: español (los documentos de diseño están en inglés; la elección de idioma está pendiente, PD-06).

> **Cómo leer este documento.** Es el informe de revisión tal como se entregó, sobre la versión de la documentación del
> commit `b46e5cc`. Las referencias a líneas (`archivo:línea`) se refieren a esa versión y ya no coinciden con los
> documentos corregidos. El [Anexo A](#anexo-a--estado-de-incorporación) indica dónde se ha incorporado cada hallazgo y
> qué decisiones tomó el usuario después de la revisión.

**Qué se hizo en la revisión:** lectura completa de los siete documentos de `docs/` y del `README.md`. No se modificaron
archivos, no se instaló nada, no se ejecutó código, no se consultó la web y no se hicieron commits ni pushes.

**Etiquetas usadas en el informe:**

| Etiqueta | Significado |
|---|---|
| **[COMPROBADO]** | Verificado directamente: contenido de los archivos, coherencia entre documentos, estructura del repositorio OI leída en la Fase 0 |
| **[DOC]** | Lo afirma la documentación. Procede de la investigación de la Fase 0 (un subagente consultó registros npm/PyPI, avisos de seguridad y el BOE) y **no se ha vuelto a verificar** |
| **[HIPÓTESIS]** | Supuesto razonable sin datos que lo respalden todavía |
| **[PENDIENTE]** | Nadie lo sabe aún; requiere una decisión, una prueba o un abogado |

En los documentos corregidos estas etiquetas se corresponden con VERIFIED, REPORTED, HYPOTHESIS y PENDING
([decisions.md](decisions.md#status-labels)).

---

## Resumen ejecutivo

1. **Los principios son sólidos; el alcance es excesivo para un primer sistema complejo.** El diseño describe 14
   componentes, 12 agentes, 4 almacenes, unos 20 contratos, presupuestos en 5 niveles y 9 tipos de aprobación. Muchos de
   esos detalles no hacen falta para empezar. Se propone un M1 mucho más pequeño (sección 2).
2. **Hay errores e incoherencias en los documentos [COMPROBADO].** Siete de ellos (E1–E7) hay que corregirlos antes de
   implementar. Dos son graves: el sistema de puntuación depende de datos que en el plan solo se obtienen más tarde, y la
   generación de previews queda bloqueada por la revisión legal, que el plan sitúa después.
3. **Los mayores riesgos no son técnicos.** Son tres: de dónde salen legalmente los prospectos (la fuente de
   descubrimiento sigue sin decidir); si los fallos técnicos de una web predicen de verdad la intención de compra
   [HIPÓTESIS sin validar]; y qué canales de contacto están permitidos en España [PENDIENTE de abogado].
4. **La fábrica web puede producir webs excelentes, pero no lo garantiza.** La calidad visual dependerá de una
   biblioteca de componentes diseñada por personas y de la fotografía, no de la arquitectura.
5. **Recomendación:** primero una corrección documental breve (sin código) que fije un "M1 mínimo". Después, con
   aprobación explícita, implementar ese M1 en local, sin red y sin coste. En paralelo y fuera del sistema, iniciar ya la
   consulta jurídica, porque es lo que más tarda.

---

## 0. Errores e incoherencias en la documentación [COMPROBADO]

| # | Problema | Dónde (versión `b46e5cc`) | Consecuencia |
|---|---|---|---|
| E1 | El diagrama dice que el QA runner usa "LHCI" (Lighthouse CI), pero D-012 lo descarta. | `docs/architecture.md:156` | Contradicción menor; puede confundir. |
| E2 | Las puertas de puntuación (zona geográfica, actividad, categoría) necesitan evidencias como la dirección, la zona de servicio o contenido fechado. En el flujo, esas evidencias solo las produce el agente investigador (A4, con IA, en M5), que trabaja **después** de puntuar. | `data-contracts.md:198-206` frente a `architecture.md:263-267` | En M4 casi todos los prospectos quedarían en `PENDING`. Hace falta extraer de forma determinista (sin IA), ya en M2, los datos básicos: teléfono (`tel:`), dirección, JSON-LD, pie de página. |
| E3 | La categoría `PRIORITY` exige R ≥ 2 (canal de contacto apto con comprobaciones: evaluación de interés legítimo y Lista Robinson). Eso depende de la revisión legal, prevista en M8. Pero las previews T1/T2 de M7 exigen `PRIORITY`. | `data-contracts.md:225`, `roadmap.md` | M7 no puede empezar hasta M8: el orden está invertido. |
| E4 | El piloto real de M2 analiza webs de autónomos, que son personas identificables. Sin embargo, la evaluación de interés legítimo (LIA) y el análisis de riesgos (DPIA) aparecen en M4. | `roadmap.md:53-70`, `security-and-compliance.md:94` | Se tratarían datos personales antes de tener la base jurídica documentada. |
| E5 | El rastreador debe identificarse con una URL y un contacto de baja, pero la identidad de la agencia figura como desconocida hasta M8 (U-4). | `security-and-compliance.md:122` | Bloquea el piloto real de M2. |
| E6 | Las capturas de páginas se borran a los 90 días, pero una evidencia `KNOWN` exige `capture_id` para poder volver a verificarla. | `security-and-compliance.md:93`, `data-contracts.md:84` | Pasados 90 días se pierde la trazabilidad. Hay que decidir qué se conserva. |
| E7 | M2 exige una aprobación tipo `CAMPAIGN_PLAN`, pero no hay interfaz de aprobaciones hasta M3. | `roadmap.md:57-58` | M1 necesita al menos aprobar desde la línea de comandos. |
| E8 | Los costes relativos de cada tier ("~5×", "~20–40×") y los presupuestos de tokens por agente no tienen base. | `architecture.md:280-283`, `agent-design.md:47-60` | Son [HIPÓTESIS] y deberían presentarse como tales con más claridad. |
| E9 | La prueba AT1.6 ("replaying the event log rebuilds an identical read model") obliga a hacer *event sourcing* completo. | `roadmap.md:46` | Complejidad innecesaria al principio. |
| E10 | Los plazos de retención (6 y 12 meses) y los umbrales (70 %, 90 %, 0,95) no tienen fundamento empírico ni jurídico. | Varios | Deben marcarse como propuestas provisionales. |

---

## 1. Arquitectura: ¿demasiado compleja para empezar?

**Sí.** La arquitectura completa es razonable como destino final, pero como punto de partida multiplica lo que hay que
construir y depurar antes de aprender nada del negocio.

Cuatro ideas que **sí deben conservarse desde el primer día**, porque son baratas al principio y muy caras de añadir
después:

1. **El código decide y la IA solo propone.** Los cambios de estado, el gasto y los permisos los controla código
   determinista.
2. **Toda afirmación lleva evidencia y estado de verdad.** Se adopta el vocabulario de OI (`KNOWN`, `INFERRED`,
   `UNKNOWN`…). Un dato desconocido nunca cuenta como aprobado.
3. **Registro de eventos de solo-añadir.** Cada acción queda apuntada y nunca se edita ni se borra.
4. **Un único punto de salida a la red.** Además, en las pruebas la red está bloqueada.

| Componente | Propuesta | Motivo |
|---|---|---|
| PostgreSQL + cola de trabajos | **Posponer**: SQLite y ejecución secuencial | Sin trabajadores concurrentes no hace falta una cola. |
| *Event sourcing* completo | **Eliminar**: log de eventos + tablas de estado normales, en la misma transacción | Misma trazabilidad con mucha menos complejidad. |
| Motor de políticas genérico | **Simplificar**: funciones normales con reglas en JSON | Abstracción prematura. |
| Presupuesto en 5 niveles | **Simplificar** a 2 niveles (global y por ejecución) + interruptor de pago desactivado | No hay gasto real hasta M5. |
| Puente con OI | **Posponer**: solo el vocabulario | No aporta valor hasta que haya datos que intercambiar. |
| Dashboard (M3) | **Posponer**: en M1, un comando `trace` | El dashboard muestra los mismos eventos; primero hay que tenerlos. |
| 12 agentes | **Reducir**: 0 en M1–M2; 2–3 cuando llegue la IA | A1, A2, A9, A11 y A12 son prescindibles al principio. |
| Spike de AgentScope (S1) | **Posponer** hasta que exista un ejecutor propio | Sin agentes, no hay nada que evaluar. |
| Exportación OpenTelemetry, cuatro ojos, Google Sheets | **Posponer** | No aportan nada al principio. |
| Fábrica con 3 temas y unos 25 componentes | **Reducir** a 1 tema y unos 10 componentes, partiendo de una web de referencia hecha a mano | La calidad visual se valida antes de automatizar. |

---

## 2. M1: el entregable mínimo

**Definición:** un programa Python de línea de comandos que funciona en local y sin red, con datos **exclusivamente
sintéticos**. Debe poder cargar una campaña y prospectos de ejemplo; registrar evidencias y hallazgos; puntuar de forma
determinista; mover cada prospecto por su máquina de estados con reglas; apuntar cada acción en un log que no se puede
modificar; denegar cualquier herramienta de pago; registrar aprobaciones; exportar un CSV seguro. Queda fuera:
dashboard, IA, red, PostgreSQL y el puente con OI.

**Módulos:** `contracts/`, `store` (SQLite con *triggers* que impiden `UPDATE`/`DELETE` en eventos), `workflow`,
`evidence`, `scoring`, `budget` (doble llave `PAID_CALLS_ENABLED=false`), `gateway` (herramientas falsas), `approvals`
(ligadas al hash de la acción exacta), `export` (CSV con protección contra inyección de fórmulas), `cli`.

**Contratos JSON esenciales (7):** `Lead`, `EvidenceRecord`, `Finding`, `ScoreRecord`, `Event`, `ApprovalRequest`,
`LedgerEntry`.

**Cinco pruebas de aceptación:**

1. **Evidencia no inventada.** Una evidencia `KNOWN` cuyo fragmento no aparece literalmente en la captura se rechaza
   (`evidence.rejected`). Una `KNOWN` sin `source_url` falla la validación.
2. **Transiciones protegidas.** `DISCOVERED` → `SHORTLISTED` directo da error, el estado no cambia y queda
   `state.transition_denied`. El camino válido genera exactamente un evento por transición.
3. **Lo desconocido no aprueba.** Puerta geográfica `UNKNOWN` → `PENDING`, nunca prioridad. Misma entrada → mismo
   resultado y mismo `rules_hash`; cambiar las reglas cambia el hash.
4. **Cero gasto y cero red.** Con el interruptor apagado, herramienta con precio > 0 o desconocido → `DENIED` + evento.
   Toda la batería con *sockets* bloqueados.
5. **Log inalterable y trazable.** `UPDATE`/`DELETE` en eventos falla. `cli trace <lead>` reconstruye la historia. Una
   aprobación deja de valer si cambia el texto de la acción.

---

## 3. M2: detectar necesidad real sin confundirla con errores técnicos

**El problema [HIPÓTESIS fuerte]:** muchas webs pequeñas sacan una puntuación de rendimiento baja en Lighthouse en
móvil, incluidas webs de negocios satisfechos con ellas. Si un hallazgo aparece en casi todas las webs, no discrimina.
Un fallo técnico **no es** una oportunidad comercial.

**Cuatro capas que no se mezclan nunca:**

| Capa | Pregunta | Quién lo decide | Ejemplo |
|---|---|---|---|
| 1. Hecho técnico | ¿Existe el fallo y es reproducible? | Medición determinista | LCP de 5,2 s (mediana de 3 ejecuciones) |
| 2. Impacto en captación | ¿Afecta a que un cliente contacte? | Regla por código de hallazgo [HIPÓTESIS] | Sin botón de llamada en móvil: alto. CLS alto: bajo |
| 3. Señales de negocio | ¿Está activo, la web le importa y su categoría tiene valor? | Evidencias + reglas | Servicios publicados, contenido reciente, web propia |
| 4. Desconocidos | ¿Qué no sabemos? | Siempre explícito | Presupuesto, intención de compra |

**Clasificación inicial de impacto [HIPÓTESIS]:** alto (`NO_SITE`, `SITE_DOWN`, `NO_MOBILE_CONTACT_PATH`,
`NOT_MOBILE_READY`, `NO_HTTPS`); medio (`SLOW_MOBILE`, `SEO_BASICS_MISSING`, `NO_LOCAL_SIGNALS`,
`BROKEN_INTERNAL_LINKS`); bajo (`LAYOUT_SHIFT`, `MIXED_CONTENT`, `A11Y_SERIOUS` a efectos de venta). Solo con hallazgos
de impacto bajo nunca hay oportunidad.

**Contraseñales:** web rehecha recientemente; crédito "diseñado por [agencia]"; franquicia o plantilla corporativa;
negocio grande o cadena; presencia digital clara por otro canal.

**Evidencias necesarias para afirmar "oportunidad":** identidad confirmada; al menos un hallazgo de impacto alto o medio
reproducible; actividad fechada en los últimos 12 meses de fuente oficial o registro público; zona y categoría
confirmadas por la propia web; un canal de contacto publicado por el propio negocio, con el texto literal.

**Debe quedar como `UNKNOWN`:** presupuesto y disposición a pagar; quién decide; tráfico real y conversiones; experiencia
real de los usuarios; facturación y empleados salvo fuente oficial; contrato con otra agencia o planes de rediseño; por
qué la web está como está; "sin web" queda en `INFERRED` salvo dos fuentes independientes, y aun así puede ser
deliberado.

**Cambio necesario en la validación:** una segunda etiqueta humana por web ("¿le propondrías una web nueva?") y medir la
frecuencia de cada hallazgo. El corpus sintético aporta poco sobre webs reales.

---

## 4. Fábrica web: ¿permitirá webs excelentes?

**Bien resuelto:** salida estática con JS mínimo; *tokens*; componentes con esquema; sin terceros; fuentes propias;
controles de móvil; presupuestos de rendimiento; axe + lista manual WCAG 2.2 AA, separando calidad visual y
accesibilidad; animaciones que respetan `prefers-reduced-motion`; la IA no escribe código.

**Huecos:**

1. El techo de calidad lo marcan la biblioteca de componentes y la fotografía.
2. Falta una web de referencia hecha a mano antes de automatizar.
3. La conversión está poco especificada: falta un catálogo de componentes de conversión y una forma de medirla en
   producción [PENDIENTE].
4. La rúbrica de diseño no está definida, ni quién revisa.
5. Animaciones: soporte de navegadores [PENDIENTE]; falta la regla "nunca animar el elemento LCP ni la primera
   pantalla" y una prueba de Lighthouse con animaciones activas.
6. Las previews con muchos marcadores pueden parecer inacabadas.

**Veredicto:** la arquitectura permite webs rápidas, accesibles y adaptadas a móvil; la excelencia visual y la
orientación a conversión solo se garantizan con una biblioteca diseñada por personas, una web de referencia y revisión
humana con criterios escritos.

---

## 5. Agentes y oficina visual

| Código determinista | Agente de IA (propone) | Persona |
|---|---|---|
| Mediciones, hallazgos, puntuación, puertas | Extraer afirmaciones con fragmento literal | Aprobar campañas, previews T2 y contactos |
| Estados, presupuesto, permisos | Redactar diagnósticos citando hallazgos | Subir límites de gasto |
| Canales aptos, bajas | Proponer estructura, textos, componentes | Publicar |
| Precios, esquemas, calidad, construcción, exportación | Crítica visual orientativa | Identidades ambiguas, conflictos, diseño, visto bueno legal |

El registro lo escriben el *gateway* y el ejecutor, no el agente. La oficina visual muestra solo eventos almacenados, sin
animaciones de "pensando" ni progresos inventados, y ya es útil antes de que haya IA. En M1 basta con `cli trace`.

---

## 6. Seguridad

**Riesgos principales:** Chromium frente a webs hostiles (en contenedores suele ir con `--no-sandbox`) [PENDIENTE];
cadena de suministro npm [HIPÓTESIS]; SSRF; datos personales de autónomos en capturas; inyección de instrucciones (M5+);
XSS en el dashboard.

**No verificado:** todas las versiones y avisos son [DOC]; ningún árbol transitivo auditado; sin evaluar
`html-validate`, validador JSON-LD, framework del dashboard, driver de PostgreSQL, `jsonschema`, `pytest`; versiones que
corrigen los avisos de AgentScope desconocidas; tests de OI no reproducidos.

**Pruebas antes de ejecutar herramientas de terceros:** instalación desde *lockfile* con *scripts* desactivados; SBOM y
escaneo OSV; primera ejecución en contenedor sin red, sin credenciales, sin root, con límites y registro de conexiones y
escrituras; solo contra webs de prueba locales; verificar el sandbox de Chromium; batería SSRF; después, piloto real
limitado y aprobado.

---

## 7. Cumplimiento comercial en España

> **Esto no es asesoramiento jurídico.** Son conclusiones preliminares de ingeniería que requieren revisión de un abogado.

La tabla completa de afirmaciones y su estado se mantiene en
[security-and-compliance.md § 1.1](security-and-compliance.md#11-legal-claims-and-their-verification-status)
(L1–L19). Resumen: LSSI art. 21 [DOC]; medios equivalentes [PENDIENTE]; Ley 11/2022 art. 66.1.b [DOC, verificar BOE y
Circular 1/2023]; empresas frente a autónomos [PENDIENTE]; LOPDGDD art. 19 y 23.4 [DOC, alcance pendiente]; RGPD art. 14
[PENDIENTE]; DPIA [PENDIENTE]; base para el análisis pasivo de webs de autónomos [PENDIENTE]; uso del nombre o logo en
previews [PENDIENTE]; plazos de retención [HIPÓTESIS]; AI Act art. 50 [DOC, confianza media]; accesibilidad, minería de
textos [PENDIENTE]; Google Places [DOC]; BORME [PENDIENTE]; afirmaciones de venta [PENDIENTE].

---

## 8. Costes

**Sin APIs de pago:** local; Python + SQLite; herramientas Node locales (Lighthouse en local, no la API de PageSpeed);
sin IA; sin alojamiento; CSV preparado a mano. Coste en APIs: 0 €. Costes reales fuera de tablas: tiempo humano,
abogado, más adelante dominio y alojamiento.

**Control de gasto por capas:** (1) sin credenciales; (2) doble interruptor; (3) único punto de salida a la red; (4)
precio desconocido = bloqueado; (5) reserva previa del coste máximo; (6) límite en el proveedor sin recarga automática;
(7) conciliación; (8) interruptor de emergencia y aprobación para subir límites. M1 necesita las capas 1–4.

---

## 9. Validar el negocio con una muestra pequeña

Piloto "manual primero": 20–30 negocios de una categoría y una zona desde una fuente legítima documentada; diagnóstico
con doble revisión humana; 5–8 seleccionados con diagnóstico de una página; contacto solo tras el visto bueno legal
ofreciendo el informe gratuito; informe a quien lo pida (consentimiento registrado) y concepto visual a mano para 2–3;
medir aceptación, reuniones, propuestas, ventas, horas y qué hallazgos interesan. Umbrales fijados antes de empezar por
el usuario. Con muestras pequeñas el resultado orienta, no es estadístico. El piloto ya usa datos personales y contacto
real: necesita evaluación de interés legítimo y visto bueno jurídico.

---

## 10. Decisiones pendientes (según la revisión)

**Bloqueantes para M1:** alcance de M1 mínimo; Python + SQLite; dependencias (librería estándar, `pytest`,
`jsonschema`); repositorio público o privado; aprobación de la corrección documental.

**Antes de M2:** entorno aislado para Chromium y revisión de Playwright, Lighthouse y axe; identidad de la agencia, URL y
contacto de baja para el rastreador (o M2 solo con webs de prueba); una categoría y una zona; base jurídica del análisis
de webs reales; clasificación de impacto y política de conservación de capturas.

**Aplazables:** proveedor de IA y límite; AgentScope; alojamiento de previews; Google Sheets; precios; CRM; temas;
puente con OI; PostgreSQL; dashboard. Iniciar ya la consulta legal sobre canales.

---

## Tabla de riesgos

| # | Riesgo | Prob. | Impacto | Mitigación | Naturaleza |
|---|---|---|---|---|---|
| R1 | La complejidad impide terminar M1 | Alta | Alto | M1 mínimo | [COMPROBADO] |
| R2 | No hay fuente legal y viable de prospectos | Alta | Alto | CSV manual, fuentes oficiales, consulta legal | [PENDIENTE] |
| R3 | Los fallos técnicos no predicen la compra | Media-alta | Alto | Doble etiqueta y piloto pequeño | [HIPÓTESIS] |
| R4 | Restricciones de canal reducen la conversión | Alta | Alto | Canales aprobados por el abogado; informe solicitado | [DOC] + [PENDIENTE] |
| R5 | Webs visualmente genéricas | Media | Alto | Web de referencia, diseño humano, rúbrica | [HIPÓTESIS] |
| R6 | Navegador comprometido por una web hostil | Media | Alto | Sandbox, contenedor aislado | [PENDIENTE] |
| R7 | Paquete npm comprometido | Media | Alto | Lockfile, scripts desactivados, OSV, ejecución aislada | [HIPÓTESIS] |
| R8 | Datos de autónomos sin base documentada | Media | Alto | Evaluación de interés legítimo antes del piloto | [COMPROBADO] (E4) |
| R9 | Gasto no autorizado al activar la IA | Baja | Medio | Controles por capas | Diseño [DOC] |
| R10 | Inyección de instrucciones vía webs | Media | Medio-alto | Contenido como datos, evaluaciones | Diseño [DOC] |
| R11 | Afirmaciones de venta engañosas | Media | Medio | Fecha y herramienta; `sales_safe` | Diseño [DOC] |
| R12 | Todos los papeles recaen en una persona | Alta | Medio | Reducir alcance y priorizar | [HIPÓTESIS] |
| R13 | OI sin fusionar y tests no reproducidos | Baja | Bajo | Solo se reutiliza el vocabulario | [COMPROBADO] |

## Recomendación de la revisión

Corrección documental sin código; después, con aprobación explícita, implementar M1 mínimo (local, sin red, sin IA,
datos sintéticos, coste 0 €). M2 no empieza hasta resolver las decisiones "antes de M2".

---

## Anexo A — Estado de incorporación

### Decisiones del usuario posteriores a la revisión (2026-10-19)

1. Autorizada **exclusivamente** la corrección documental; **no** autorizada la implementación de M1 (PD-01).
2. M1: Python + SQLite, sin IA, sin APIs de pago, sin red, datos sintéticos (D-018).
3. Alcance de M1: contratos JSON, evidencias, puntuación determinista, máquina de estados, registro de eventos,
   aprobaciones por CLI, control de gasto, exportación CSV segura (D-018).
4. Excluidos en esta fase: integración de código con OI, PostgreSQL, dashboard, AgentScope, Google Sheets (D-019).
5. Fuera de alcance hasta aprobar sus fases: rastreo de webs reales, contacto comercial, despliegue público, generación
   automática de previews (D-020).
6. Separar evidencia técnica, impacto en captación y oportunidad comercial; ninguna puntuación técnica es intención de
   compra (D-021).
7. No inventar valores comerciales, umbrales ni plazos legales: registro de parámetros provisionales (D-025).

### Dónde se ha incorporado cada hallazgo

| Hallazgo | Incorporación |
|---|---|
| E1–E10 | [decisions.md § Correction log](decisions.md#correction-log-e1e10) |
| §1 Complejidad | [architecture § 4.1](architecture.md#41-phase-status-of-each-component) (estado por fase de cada componente) |
| §2 M1 mínimo | [roadmap § M1](roadmap.md#m1--minimal-deterministic-core-offline): 8 contratos (se añadió `SuppressionEntry` para las pruebas de protección de datos) y 12 pruebas (las 5 de la revisión + 7) |
| §3 Capas y desconocidos | [data-contracts § 6](data-contracts.md#6-three-layer-assessment-technical-evidence-acquisition-impact-commercial-opportunity), [architecture § 5.2](architecture.md#52-three-layers-and-contactability-d-021-d-023) |
| §4 Fábrica | [quality-gates § 1](quality-gates.md#1-website-factory) (web de referencia, componentes de conversión, animaciones, rúbrica) |
| §5 Agentes y registro | [agent-design § 2 y § 8](agent-design.md#2-what-is-deterministic-what-an-agent-may-do-what-a-person-decides), [architecture § 11](architecture.md#11-observability-how-real-actions-are-recorded) |
| §6 Seguridad | [security-and-compliance § 2 y § 6](security-and-compliance.md#6-supply-chain-and-dependency-admission) |
| §7 Legal | [security-and-compliance § 1](security-and-compliance.md#1-legal-position-status-reported-not-legal-advice) y § 12 |
| §8 Costes | [roadmap § 4](roadmap.md#4-costs) |
| §9 Validación del negocio | [roadmap § P1](roadmap.md#p1--business-validation-pilot-manual-first-gated) |
| §10 Decisiones | [decisions.md § Pending decisions](decisions.md#pending-decisions) |
| Limitaciones de SQLite y del log | [architecture § 6](architecture.md#6-m1-storage-sqlite-triggers-and-the-event-log--design-and-limitations) |
