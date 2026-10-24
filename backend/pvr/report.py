"""Readable deterministic assessment of one change, built only from engine results (no LLM)."""

from __future__ import annotations

from datetime import date

from pvr.engines import buffer, change, cost, cpm, options, productivity, quantities
from pvr.models import ProjectData, RunContext


def aed(value: float) -> str:
    """AED with thousands separators; whole amounts without decimals, negatives with a minus sign."""
    text = f"{abs(value):,.2f}".removesuffix(".00")
    return ("-" if value < 0 else "") + text


def qty(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def day(d: date) -> str:
    return d.strftime("%a %d %b %Y")


def _table(headers: list[str], rows: list[list[str]], right: set[int]) -> list[str]:
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def fmt(cells: list[str]) -> str:
        return "  ".join(c.rjust(w) if i in right else c.ljust(w) for i, (c, w) in enumerate(zip(cells, widths)))

    return [fmt(headers), fmt(["-" * w for w in widths]), *(fmt(r) for r in rows)]


def assessment_report(ctx: RunContext, data: ProjectData) -> str:
    """Full deterministic assessment: change, quantities, cost, programme, options, buffer, claim."""
    req = change.get_change_request(ctx, data)
    params = ", ".join(f"{p.label} = {change.format_parameter(p.value, p.step)}" for p in req.parameters)
    out = [f"== {req.title} ({params}; mode {req.mode}) ==", f"Instruction: {req.instruction_text}"]

    drawing = change.compare_drawing_revisions(ctx, data)
    to_rev = f"Rev {drawing.to_revision}" if drawing.to_revision else "requested change"
    for c in drawing.changes:
        note = f" {c.note}" if c.note else ""
        out.append(f"Drawing {drawing.drawing} Rev {drawing.from_revision} -> {to_rev}: "
                   f"{c.parameter} {qty(c.old)} -> {qty(c.new)} {c.unit}{note}")

    q = quantities.quantify_change(ctx, data)
    out += ["", "Quantities"]
    unaffected = {u.code: u.reason for u in q.unaffected}
    for line in q.lines:
        change_text = f"+{qty(line.delta)} {line.unit}" if line.delta else f"0 (not affected: {unaffected.get(line.code, '')})"
        out.append(f"  {line.code}  {line.description:<62} {change_text}")
    for r in q.requires_review:
        out.append(f"  {r.code}  {r.description:<62} needs review: {r.reason}")

    c = cost.price_change(ctx, data)
    out += ["", f"Cost ({c.rate_source})"]
    out += ["  " + row for row in _table(
        ["BOQ code", "Change", "Rate", "Amount (AED)"],
        [[ln.code, f"{qty(ln.delta)} {ln.unit}", aed(ln.rate_aed), aed(ln.amount_aed)] for ln in c.lines],
        right={1, 2, 3},
    )]
    out.append(f"  Direct cost: AED {aed(c.direct_cost_aed)}")
    for item in c.unpriced_items:
        flag = "new rate needed" if item.needs_new_rate else "not priced, under review"
        out.append(f"  {item.code}: AED 0 ({flag})")

    impact = productivity.added_duration(ctx, data)
    baseline = cpm.run_cpm(data)
    impacted = cpm.run_cpm(data, impact.new_durations())
    float_days = min((baseline.activities[a.activity_id].TF for a in impact.activities), default=0)
    delay = max(0, impacted.completion_working_day - data.project.contract_completion_working_day)
    out += ["", "Programme"]
    for a in impact.activities:
        out.append(f"  {a.activity_id} {a.name}: +{a.added_days} wd ({a.baseline_duration} -> {a.new_duration})")
    out.append(f"  Added duration {impact.total_added_days} wd in total; baseline float of the affected chain "
               f"{float_days} wd; delay without acceleration {delay} wd")
    out.append(f"  Completion without acceleration: day {impacted.completion_working_day} "
               f"({day(impacted.completion_date)}); contract completion day "
               f"{data.project.contract_completion_working_day} ({day(baseline.completion_date)})")

    search = options.search_options(ctx, data)
    pareto = set(search.pareto_option_ids)
    out += ["", f"Options ({len(search.options)} evaluated; * = Pareto set, presented in this order: "
            f"{', '.join(search.pareto_option_ids)})"]
    rows = []
    for o in search.options:
        b = buffer.check_buffer(ctx, data, o.option_id)
        money = aed(b.contingency_remaining_aed) + (" (uplift needed)" if b.budget_uplift_needed_aed else "")
        rows.append([
            ("* " if o.option_id in pareto else "  ") + o.option_id,
            ", ".join(o.extra_crews_on) or "none",
            str(o.delay_working_days),
            day(o.completion_date),
            aed(o.acceleration_cost_aed),
            aed(o.time_related_cost_aed),
            aed(o.total_cost_aed),
            str(b.time_buffer_remaining_days) + (" (breach)" if b.exceeds_employer_commitment else ""),
            money,
        ])
    out += ["  " + row for row in _table(
        ["Option", "Extra crews", "Delay", "Completion", "Accel.", "Time cost", "Total", "Buffer left",
         "Contingency left"],
        rows, right={2, 4, 5, 6, 7, 8},
    )]

    if change.contractor_claim_applies(ctx):
        cc = cost.compare_contractor_claim(ctx, data)
        out += ["", f"Contractor claim check ({cc.pvr_ref} against {cc.instruction_ref})"]
        out += ["  " + row for row in _table(
            ["Claimed line", "BOQ code", "Qty claimed", "Qty assessed", "Rate claimed", "BOQ rate", "Clause"],
            [[ln.claimed_description, ln.matched_code, qty(ln.claimed_quantity), qty(ln.assessed_quantity),
              aed(ln.claimed_rate_aed), aed(ln.boq_rate_aed), ln.clause] for ln in cc.lines],
            right={2, 3, 4, 5},
        )]
        out.append(f"  Claimed: AED {aed(cc.claimed_subtotal_aed)} + {qty(cc.claimed_preliminaries_percent)}% "
                   f"preliminaries AED {aed(cc.claimed_preliminaries_aed)} = AED {aed(cc.claimed_total_aed)}; "
                   f"extension {cc.claimed_extension_days} wd")
        out.append(f"  Assessed: AED {aed(cc.assessed_direct_cost_aed)} at BOQ rates; difference "
                   f"AED {aed(cc.difference_direct_aed)}")
        for adj in cc.adjustments:
            if adj.unit == "AED":
                out.append(f"  {adj.item}: claimed AED {aed(adj.claimed)}, allowed AED {aed(adj.assessed)} "
                           f"(clause {adj.clause}: {adj.reason})")
            elif adj.unit == "working days":
                out.append(f"  {adj.item}: claimed {qty(adj.claimed)} wd, assessed {qty(adj.assessed)} wd "
                           f"(clause {adj.clause}: {adj.reason})")
        out.append(f"  Time-related costs: AED {aed(cc.time_related_cost_per_day_aed)} per working day, only for "
                   f"an extension actually granted (AED {aed(cc.time_related_cost_if_extension_granted_aed)} "
                   f"if {cc.assessed_extension_days_without_acceleration} wd are granted)")
        n = cc.notice
        out.append(f"  Notice: {n.calendar_days} calendar days after the instruction; "
                   f"{'within' if n.within_limit else 'NOT within'} {n.limit_days} days (clause {n.clause})")
    return "\n".join(out)
