"""Readable diagnosis audit (M2a.1), in Spanish, rebuilt only from the database: evidence, findings, scores, rules.

Technical facts, pending checks and the commercial-impact hypothesis are separate sections. The report never contains
contact values, raw HTML, page text, evidence ids or timestamps other than the scoring date, so the same database
content always renders the same file. No figures are invented: impact is a qualitative hypothesis from
impact_rules.v1 and nothing is said about traffic, sales or conversion.
"""
import re

from . import assessment, evaluation
from . import evidence as E
from .diagnose import CHECKS, rules

CHECK_TEXT = {
    "SEO_BASICS_MISSING": "falta título, descripción o H1 en la página de inicio, o está marcada `noindex`",
    "NO_LOCAL_SIGNALS": "no hay dirección, zona ni datos LocalBusiness en la página de inicio",
    "BROKEN_INTERNAL_LINKS": "enlaces internos que apuntan a páginas inexistentes (umbral P-05)",
    "MIXED_CONTENT": "recursos cargados por http:// en una página https://",
    "NOT_MOBILE_READY": "la página de inicio no declara viewport para móvil",
    "NO_MOBILE_CONTACT_PATH": "no hay tel:, mailto:, WhatsApp, formulario de contacto ni enlace de contacto en la "
                              "página de inicio ni en las páginas que enlaza",
    "NO_HTTPS": "la web no se sirve por HTTPS", "TLS_INVALID": "certificado TLS no válido",
    "SITE_DOWN": "la web no responde", "SLOW_MOBILE": "carga lenta en móvil",
    "LAYOUT_SHIFT": "desplazamientos de diseño durante la carga", "A11Y_SERIOUS": "problemas graves de accesibilidad",
}
REASON_TEXT = {
    "NOT_RUN": "no ejecutada: requiere red o navegador (fase PD-08 no aprobada)",
    "CONTACT_PATH_FOUND": "hay al menos una posible vía de contacto (tel:, mailto:, WhatsApp, formulario o enlace de "
                          "contacto); no se ha comprobado que funcione ni que el negocio responda, y su posición en "
                          "móvil requiere un navegador",
    "STATIC_INCONCLUSIVE": "el HTML estático no muestra el problema, pero confirmarlo requiere un navegador",
    "NOT_HTTPS_CAPTURE": "la captura no es HTTPS; no se puede evaluar contenido mixto",
    "CRAWL_TRUNCATED": "se alcanzó el límite de páginas del rastreo local; hay páginas sin revisar",
    "HOME_NOT_CAPTURED": "la captura no contiene la página de inicio",
    "AMBIGUOUS_SIGNAL": "el texto contiene el nombre de un municipio de la campaña solo dentro de otra palabra",
    "CONFLICTING_EVIDENCE": "las evidencias registradas se contradicen",
    "DETECTED_WITHOUT_VALID_FINDING": "la medición indica un problema, pero no hay hallazgo con evidencia válida",
    "NO_EVIDENCE": "no hay ninguna evidencia registrada para esta comprobación",
}
IMPACT_TEXT = {
    "SEO_BASICS_MISSING": "podría reducir la visibilidad de la web en buscadores",
    "NO_LOCAL_SIGNALS": "podría dificultar que aparezca en búsquedas de su zona",
    "BROKEN_INTERNAL_LINKS": "podría interrumpir la navegación de quien busca un servicio",
    "MIXED_CONTENT": "algunos navegadores podrían bloquear recursos o mostrar avisos",
    "NOT_MOBILE_READY": "podría dificultar el uso de la web desde el móvil",
    "NO_MOBILE_CONTACT_PATH": "podría dificultar que un visitante contacte desde el móvil",
}
REVIEW_TEXT = {
    "SEO_BASICS_MISSING": "abrir la web publicada y comprobar título, descripción, H1 y directiva robots",
    "NO_LOCAL_SIGNALS": "comprobar si la web menciona dirección o zona de servicio en otra página",
    "BROKEN_INTERNAL_LINKS": "abrir los enlaces rotos en la web publicada (pueden existir en el servidor)",
    "MIXED_CONTENT": "comprobar en un navegador si los recursos http:// se cargan o se bloquean",
    "NOT_MOBILE_READY": "ver la página en un móvil real o emulado",
    "NO_MOBILE_CONTACT_PATH": "buscar en la web publicada otros canales (p. ej. un teléfono escrito sin enlace o un chat)",
}
STATUS_TEXT = {
    "PROBLEMS_FOUND": "hay problemas confirmados por evidencia válida",
    "NO_PROBLEMS_FOUND": "las comprobaciones del alcance estático se completaron sin problemas; esto no garantiza "
                         "la calidad general de la web: las demás comprobaciones figuran abajo como no verificadas",
    "INSUFFICIENT_EVIDENCE": "quedan comprobaciones del alcance sin verificar; no se puede afirmar ni negar que la "
                             "web tenga problemas",
}
FACT_LABELS = (("business.municipality", "municipio"), ("business.category", "categoría"),
               ("business.activity_dated", "fecha de actividad"), ("activity.signal.service_pages", "páginas de servicios"),
               ("business.phone", "teléfono"), ("business.email", "email"))


def _safe(value, limit=80):
    """Report text from data: one line, no Markdown control characters, long digit runs masked."""
    text = re.sub(r"[^\w .,;:/()'-]", "?", str(value), flags=re.UNICODE)
    return re.sub(r"\d{6,}", "######", text)[:limit]


def _fact_line(evidence, field, label):
    status, value, _ = E.resolve(evidence, field)
    if field in E.PERSONAL_FIELDS:
        return f"- {label}: {'presente en la web (no se incluye en este informe)' if status == 'KNOWN' else 'no encontrado'}"
    if status == "CONFLICTING":
        values = sorted({str(e["value"]) for e in evidence if e["field"] == field and e["claim_status"] == "KNOWN"})
        return f"- {label}: **CONTRADICTORIO** ({' / '.join(_safe(v) for v in values)}); no se elige ninguno"
    if status == "UNKNOWN":
        return f"- {label}: desconocido"
    shown = "sí" if value is True else _safe(value)
    return f"- {label}: {shown} ({'citado literalmente en la captura' if status == 'KNOWN' else 'inferido del texto, no confirmado'})"


def _recommendations(ev, score, evidence):
    out = []
    for code in ev["confirmed"]:
        out.append(f"Verificar {code}: {REVIEW_TEXT.get(code, 'revisar manualmente en la web publicada')}.")
    in_scope = [p["code"] for p in ev["pending"] if p["in_scope"]]
    if ev["status"] == "NO_PROBLEMS_FOUND":
        out.append(f"Resultado limitado al alcance estático: {len(ev['pending'])} comprobaciones siguen sin verificar; "
                   "no presentar la web como correcta.")
    if in_scope:
        out.append(f"No tratar la web como correcta: faltan {', '.join(in_scope)} dentro del alcance. Repetir el "
                   "diagnóstico con una captura completa antes de decidir.")
    for field, label in FACT_LABELS[:2]:
        if E.resolve(evidence, field)[0] == "CONFLICTING":
            out.append(f"Resolver a mano el {label} contradictorio (registrar la decisión como HUMAN_REVIEW).")
    unknown_gates = [g["gate_id"] for g in score.get("gates", []) if g["result"] == "UNKNOWN"]
    if unknown_gates:
        out.append(f"Completar las puertas sin resolver ({', '.join(unknown_gates)}) antes de priorizar el contacto.")
    out.append("No afirmar al negocio nada sobre las comprobaciones no verificadas ni sobre su impacto comercial.")
    return out


def render(store, lead_ids, title="Auditoría de diagnóstico"):
    cfg = rules()
    impact = assessment.load_rules()["impact_rules.v1.json"]["impact"]
    rows = []
    for lead_id in lead_ids:
        lead, evidence = store.lead(lead_id), store.evidence_for(lead_id)
        rows.append((lead, evidence, store.findings_for(lead_id), store.latest_score(lead_id) or {},
                     evaluation.evaluate(evidence, store.findings_for(lead_id), cfg)))
    counts = {s: sum(1 for r in rows if r[4]["status"] == s) for s in evaluation.STATUSES}
    dates = sorted({r[3]["computed_at"][:10] for r in rows if r[3]})
    out = [f"# {title}", "",
           f"Datos ficticios (`{'`, `'.join(sorted({r[0]['data_mode'] for r in rows}))}`). Procedimiento "
           f"`{cfg['procedure_version']}`: solo HTML local, sin red ni navegador. Fecha de puntuación: "
           f"{', '.join(dates) or '—'}. Material para revisión humana, no para enviar al negocio.", "",
           "## Resumen ejecutivo", "",
           f"- Webs analizadas: {len(rows)}. Con problemas confirmados: {counts['PROBLEMS_FOUND']}. Sin problemas en el "
           f"alcance evaluado: {counts['NO_PROBLEMS_FOUND']}. Con evidencia insuficiente: {counts['INSUFFICIENT_EVIDENCE']}.",
           f"- Alcance evaluado: {', '.join(cfg['evaluation_scope'])}. Las otras {len(CHECKS) - len(cfg['evaluation_scope'])} "
           "comprobaciones solo pueden confirmar un problema o quedar sin verificar; ninguna web de este informe puede "
           "considerarse sana.",
           "- La prioridad de revisión es independiente del estado de evaluación: una prioridad LOW no significa que "
           "la web esté bien, y no es una probabilidad de compra.", "",
           "| Web | Estado de evaluación | Prioridad de revisión | Problemas confirmados | Sin verificar (alcance / total) |",
           "|---|---|---|---|---|"]
    for lead, _, _, score, ev in rows:
        in_scope = sum(1 for p in ev["pending"] if p["in_scope"])
        out.append(f"| {_safe(lead['business'].get('name'))} | {ev['status']} | "
                   f"{score.get('layer3', {}).get('bucket', '—')} | {', '.join(ev['confirmed']) or '—'} | "
                   f"{in_scope} / {len(ev['pending'])} |")
    for lead, evidence, findings, score, ev in rows:
        l3 = score.get("layer3", {})
        tg, im = score.get("layer1", {}).get("TG", {}), score.get("layer2", {}).get("IM", {})
        out += ["", f"## {_safe(lead['business'].get('name'))} (`{lead['lead_id']}`)", "",
                f"- **Estado de evaluación:** {ev['status']} — {STATUS_TEXT[ev['status']]}.",
                f"- **Prioridad de revisión:** {l3.get('bucket', '—')} — prioridad para revisión humana, no una "
                f"probabilidad ni una intención de compra. Brecha técnica TG {tg.get('floor')} (máx. {tg.get('ceiling')} "
                f"si las comprobaciones pendientes fallaran); impacto IM {im.get('floor')} (máx. {im.get('ceiling')}).",
                "", "### Problemas confirmados (hechos técnicos)", ""]
        by_code = {f["code"]: f for f in findings if f["claim_status"] == "KNOWN"}
        captures = sorted({e["capture_sha256"][:12] for e in evidence if e.get("capture_sha256")})
        for code in ev["confirmed"]:
            f = by_code[code]
            measured = f" Valor medido: {_safe(f['measured_value'])}." if f.get("measured_value") is not None else ""
            out.append(f"- `{code}` (severidad {f['technical_severity']}): {CHECK_TEXT.get(code, code)}.{measured} "
                       f"Evidencia: medición `site.check.{code}` KNOWN, procedimiento `{f['rule_version']}`"
                       + (f", captura sha256 {captures[0]}…" if captures else "") + ".")
        if not ev["confirmed"]:
            out.append("- Ninguno confirmado.")
        out += ["", "### Comprobaciones sin verificar", ""]
        for p in ev["pending"]:
            where = "dentro del alcance" if p["in_scope"] else "fuera del alcance estático"
            out.append(f"- `{p['code']}` ({where}): {REASON_TEXT.get(p['reason_code'], p['reason_code'])}.")
        if not ev["pending"]:
            out.append("- Ninguna.")
        out += ["", "### Datos del negocio observados", ""]
        out += [_fact_line(evidence, field, label) for field, label in FACT_LABELS]
        gates = ", ".join(f"{g['gate_id']}={g['result']}" for g in score.get("gates", []))
        out.append(f"- puertas de la puntuación: {gates or '—'}")
        out += ["", "### Impacto comercial (hipótesis, no medido)", ""]
        if ev["confirmed"]:
            for code in ev["confirmed"]:
                out.append(f"- Hipótesis `{impact.get(code, 'sin regla')}` (impact_rules.v1) para `{code}`: "
                           f"{IMPACT_TEXT.get(code, 'sin hipótesis definida')}.")
            out.append("- No se ha medido tráfico, ventas ni conversión; estas hipótesis no son cifras ni probabilidades.")
        else:
            out.append("- Sin problemas confirmados no se formula ninguna hipótesis de impacto.")
        out += ["", "### Recomendaciones para la revisión humana", ""]
        out += [f"{i}. {text}" for i, text in enumerate(_recommendations(ev, score, evidence), 1)]
    return "\n".join(out) + "\n"
