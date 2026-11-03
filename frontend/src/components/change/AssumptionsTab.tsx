import { useEffect, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import { api, type Assumptions, type ChangeType, type QuantityRule, type WorkedExample } from "../../api/client";
import { aed, formatDate, formatDelta, formatNumber, workingDays } from "../../format";
import { ErrorState, LoadingState } from "../layout/Panel";

/**
 * Rates and assumptions behind the cost and time calculations (display only).
 * Every value comes from GET /api/assumptions (data files and engine outputs); nothing is computed here.
 */

interface AssumptionsTabProps {
  /** The change selected on the start screen, if any, and its sizes; used for the worked example. */
  changeType: ChangeType | null;
  values: Record<string, number>;
}

const SECTIONS = [
  ["rates", "Work rates"],
  ["crews", "Crews"],
  ["cost", "Cost"],
  ["time", "Time"],
  ["quantities", "Quantity rules"],
  ["example", "Worked example"],
] as const;

type SectionId = (typeof SECTIONS)[number][0];

function Source({ children }: { children: ReactNode }) {
  return <div className="mt-1 text-[10px] text-text-muted">Source: {children}</div>;
}

function Section({ id, title, children, refs }: {
  id: SectionId;
  title: string;
  children: ReactNode;
  refs: MutableRefObject<Partial<Record<SectionId, HTMLElement | null>>>;
}) {
  return (
    <section ref={(el) => { refs.current[id] = el; }} className="flex flex-col gap-2 border-t border-border pt-3 first:border-t-0 first:pt-0">
      <h3 className="text-sm font-semibold text-accent">{title}</h3>
      {children}
    </section>
  );
}

function Rule({ children }: { children: ReactNode }) {
  return <p className="rounded-card bg-surface p-2 text-xs leading-relaxed">{children}</p>;
}

function Th({ children, right }: { children?: ReactNode; right?: boolean }) {
  return <th className={`py-1 pr-2 font-normal ${right ? "text-right" : "text-left"}`}>{children}</th>;
}

function Td({ children, right, mono, wrap }: { children?: ReactNode; right?: boolean; mono?: boolean; wrap?: boolean }) {
  return (
    <td
      className={`py-1 pr-2 align-top ${right ? "text-right" : ""} ${right && !wrap ? "whitespace-nowrap" : ""} ${mono ? "font-mono whitespace-nowrap" : ""}`}
    >
      {children}
    </td>
  );
}

function label(key: string): string {
  return key.replace(/_/g, " ");
}

function GeometryValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) return <>{value.map((v) => formatNumber(Number(v))).join(" x ")}</>;
  if (typeof value === "number") return <>{formatNumber(value)}</>;
  if (value && typeof value === "object") {
    return (
      <>
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k}>
            <span className="font-mono">{k}</span>: {String(v)}
          </div>
        ))}
      </>
    );
  }
  return <>{String(value)}</>;
}

function QuantityRuleCard({ rule }: { rule: QuantityRule }) {
  const { note, ...geometry } = rule.geometry as Record<string, unknown> & { note?: string };
  return (
    <div className="rounded-card border border-border p-3 text-xs">
      <div className="font-semibold">{rule.title}</div>
      <div className="mt-1 text-text-muted">
        Sizes you can set:{" "}
        {rule.parameters.map((p) => `${p.label} ${formatNumber(p.min)} to ${formatNumber(p.max)} (default ${formatNumber(p.default)})`).join("; ")}
        {Object.keys(rule.fixed).length
          ? `. Fixed: ${Object.entries(rule.fixed).map(([k, v]) => `${label(k)} ${formatNumber(v)}`).join(", ")}`
          : ""}
      </div>
      <table className="mt-2 w-full">
        <tbody>
          {Object.entries(geometry).map(([k, v]) => (
            <tr key={k} className="border-t border-border">
              <Td>{label(k)}</Td>
              <Td>
                <GeometryValue value={v} />
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
      {note ? <p className="mt-1 text-text-muted">{note}</p> : null}
      <div className="mt-2 font-semibold">How each BOQ line is measured</div>
      <ul className="mt-1 flex flex-col gap-0.5">
        {rule.lines.map((l) => (
          <li key={l.code}>
            <span className="font-mono">{l.code}</span> {l.description} ({l.unit}): {l.basis}
          </li>
        ))}
      </ul>
      {rule.unaffected.length ? (
        <div className="mt-2">
          <span className="font-semibold">Not changed: </span>
          {rule.unaffected.map((u) => `${u.code} (${u.reason})`).join("; ")}
        </div>
      ) : null}
      {rule.requires_review.length ? (
        <div className="mt-1">
          <span className="font-semibold">Flagged for review, priced at 0: </span>
          {rule.requires_review.map((r) => `${r.code} (${r.reason})`).join("; ")}
        </div>
      ) : null}
    </div>
  );
}

function Example({ example }: { example: WorkedExample }) {
  const nc = example.no_extra_crews;
  return (
    <div className="flex flex-col gap-3 text-xs">
      <div>
        <div className="font-semibold">1. Quantity change</div>
        <table className="w-full">
          <thead className="text-text-muted">
            <tr><Th>Code</Th><Th>Basis</Th><Th right>Old</Th><Th right>New</Th><Th right>Change</Th></tr>
          </thead>
          <tbody>
            {example.quantities.map((q) => (
              <tr key={q.code} className="border-t border-border">
                <Td mono>{q.code}</Td>
                <Td>{q.basis}</Td>
                <Td right>{q.old === null ? "" : formatNumber(q.old)}</Td>
                <Td right>{q.new === null ? "" : formatNumber(q.new)}</Td>
                <Td right>{formatDelta(q.delta)} {q.unit}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <div className="font-semibold">2. Direct cost = change x BOQ rate</div>
        <table className="w-full">
          <tbody>
            {example.cost.lines.map((l) => (
              <tr key={l.code} className="border-t border-border">
                <Td mono>{l.code}</Td>
                <Td>
                  {formatNumber(l.delta)} {l.unit} x {aed(l.rate_aed)}
                </Td>
                <Td right>{aed(l.amount_aed)}</Td>
              </tr>
            ))}
            <tr className="border-t border-border font-semibold">
              <Td>Direct cost</Td>
              <Td>{example.cost.rate_source}</Td>
              <Td right>{aed(example.cost.direct_cost_aed)}</Td>
            </tr>
          </tbody>
        </table>
        {example.cost.unpriced_items.length ? (
          <p className="mt-1 text-text-muted">
            Not priced (needs review): {example.cost.unpriced_items.map((u) => u.code).join(", ")}
          </p>
        ) : null}
      </div>

      <div>
        <div className="font-semibold">3. Added days = change / output per crew-day, rounded up per activity</div>
        <table className="w-full">
          <thead className="text-text-muted">
            <tr><Th>Activity</Th><Th>Crew-days per item</Th><Th right>Added</Th><Th right>Duration</Th><Th right>Float</Th></tr>
          </thead>
          <tbody>
            {example.durations.map((d) => (
              <tr key={d.activity_id} className="border-t border-border">
                <Td>
                  <span className="font-mono">{d.activity_id}</span> {d.name}
                </Td>
                <Td>
                  {d.items.map((i) => (
                    <div key={i.code}>
                      {i.code}: {formatNumber(i.delta)} / {formatNumber(i.productivity_per_day)} = {formatNumber(i.crew_days)}
                    </div>
                  ))}
                </Td>
                <Td right>{d.added_days}</Td>
                <Td right>
                  {d.baseline_duration} to {d.new_duration}
                </Td>
                <Td right>{d.baseline_total_float}</Td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-text-muted">Float is the activity's total float in the unchanged programme, in working days.</p>
      </div>

      <div>
        <div className="font-semibold">4. Result with no extra crews ({nc.option_id})</div>
        <table className="w-full">
          <tbody>
            <tr className="border-t border-border">
              <Td>Completion</Td>
              <Td right>
                working day {nc.completion_working_day} ({formatDate(nc.completion_date)}); contract day{" "}
                {example.contract_completion_working_day}
              </Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Delay</Td>
              <Td right>{workingDays(nc.delay_working_days)}</Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Direct cost</Td>
              <Td right>{aed(nc.direct_cost_aed)}</Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Time-related cost ({aed(example.time_related_cost_per_working_day_aed)} per day of delay)</Td>
              <Td right>{aed(nc.time_related_cost_aed)}</Td>
            </tr>
            <tr className="border-t border-border font-semibold">
              <Td>Total cost</Td>
              <Td right>{aed(nc.total_cost_aed)}</Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Time buffer left</Td>
              <Td right>{workingDays(nc.time_buffer_remaining_days)}</Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Contingency left</Td>
              <Td right>
                <span className={nc.contingency_remaining_aed < 0 ? "text-alert" : ""}>{aed(nc.contingency_remaining_aed)}</span>
              </Td>
            </tr>
          </tbody>
        </table>
      </div>

      {example.one_extra_crew.length ? (
        <div>
          <div className="font-semibold">5. Effect of one extra crew on a single activity</div>
          <table className="w-full">
            <thead className="text-text-muted">
              <tr><Th>Activity</Th><Th right>Duration</Th><Th right>Crew cost</Th><Th right>Delay</Th><Th right>Total cost</Th></tr>
            </thead>
            <tbody>
              {example.one_extra_crew.map((o) => (
                <tr key={o.option_id} className="border-t border-border">
                  <Td mono>{o.activity_id}</Td>
                  <Td right>
                    {o.duration_before} to {o.duration_after}
                  </Td>
                  <Td right>{aed(o.crew_cost_aed)}</Td>
                  <Td right>{o.delay_working_days}</Td>
                  <Td right>{aed(o.total_cost_aed)}</Td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-text-muted">Combinations of crews are compared in the Options tab during a run.</p>
        </div>
      ) : null}
      <Source>{example.source}</Source>
    </div>
  );
}

export function AssumptionsTab({ changeType, values }: AssumptionsTabProps) {
  const [data, setData] = useState<Assumptions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [example, setExample] = useState<WorkedExample | null>(null);
  const [exampleError, setExampleError] = useState<string | null>(null);
  const refs = useRef<Partial<Record<SectionId, HTMLElement | null>>>({});

  useEffect(() => {
    api
      .assumptions()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load the assumptions"));
  }, []);

  const changeId = changeType?.id ?? null;
  const valuesKey = JSON.stringify(values);
  useEffect(() => {
    if (!changeId) {
      setExample(null);
      return;
    }
    let current = true;
    // Wait for the slider to settle before asking the backend.
    const timer = window.setTimeout(() => {
      api
        .workedExample(changeId, JSON.parse(valuesKey) as Record<string, number>)
        .then((e) => {
          if (current) {
            setExample(e);
            setExampleError(null);
          }
        })
        .catch((e: unknown) => {
          if (current) setExampleError(e instanceof Error ? e.message : "Could not load the worked example");
        });
    }, 250);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [changeId, valuesKey]);

  if (error) return <ErrorState message={error} />;
  if (!data) return <LoadingState message="Loading the rates and assumptions" />;

  const { work_rates: rates, crews, cost, time } = data;
  const crewRules = cost.additional_crew;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs leading-relaxed text-text-muted">
        Every value here is read from the project data files or produced by the deterministic engines. A single BOQ
        line hides the work behind it, so this tab shows the rates and assumptions the cost and time calculations use.
      </p>
      <div className="flex flex-wrap gap-1">
        {SECTIONS.map(([id, title]) => (
          <button
            key={id}
            type="button"
            onClick={() => refs.current[id]?.scrollIntoView({ behavior: "smooth", block: "start" })}
            className="rounded-full border border-border px-2.5 py-0.5 text-[11px] text-text-muted hover:border-accent hover:text-accent"
          >
            {title}
          </button>
        ))}
      </div>

      <Section id="rates" title="Work rates" refs={refs}>
        <table className="w-full text-xs">
          <thead className="text-text-muted">
            <tr><Th>BOQ item</Th><Th>Activity</Th><Th right>Output per crew per day</Th></tr>
          </thead>
          <tbody>
            {rates.items.map((r) => (
              <tr key={r.boq_code} className="border-t border-border">
                <Td>
                  <span className="font-mono">{r.boq_code}</span> {r.description}
                </Td>
                <Td>
                  <span className="font-mono">{r.activity_id}</span> {r.activity_name} ({r.baseline_duration} days)
                </Td>
                <Td right>
                  {formatNumber(r.output_per_crew_day)} {r.unit}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
        <Rule>
          <span className="font-semibold">Added days rule: </span>
          {rates.rule}
        </Rule>
        <Source>{rates.source}</Source>
      </Section>

      <Section id="crews" title="What a crew is" refs={refs}>
        <div className="rounded-card border border-accent-2 bg-accent-tint p-2 text-xs">
          <span className="font-semibold">{crews.status}. </span>
          {crews.note}
        </div>
        <ul className="flex flex-col gap-2">
          {crews.items.map((c) => (
            <li key={c.activity_id} className="rounded-card border border-border p-2 text-xs">
              <div className="font-semibold">
                <span className="font-mono">{c.activity_id}</span> {c.activity_name}: {c.crew_name}
              </div>
              <div className="mt-0.5">
                {c.people} people, {formatNumber(c.hours_per_day)} hours a day:{" "}
                {c.trades.map((t) => `${t.count} ${t.trade.toLowerCase()}`).join(", ")}
              </div>
              <div className="text-text-muted">Equipment: {c.equipment.join(", ")}</div>
              <div className="mt-1">
                {c.work_items.map((w) => (
                  <div key={w.boq_code}>
                    <span className="font-mono">{w.boq_code}</span>: {c.people} x {formatNumber(c.hours_per_day)} h /{" "}
                    {formatNumber(w.output_per_crew_day)} {w.unit} = {formatNumber(w.labour_hours_per_unit)} labour hours per{" "}
                    {w.unit}
                  </div>
                ))}
              </div>
            </li>
          ))}
        </ul>
        <Source>{crews.source} (assumed), with output per crew-day from data/productivity.json</Source>
      </Section>

      <Section id="cost" title="How cost is calculated" refs={refs}>
        <Rule>
          <span className="font-semibold">Direct cost: </span>
          {cost.direct_cost_rule} The BOQ rate already includes labour, equipment, materials and overheads, so cost is
          not built up from labour hours or crews ({cost.rate_source}).
        </Rule>
        <table className="w-full text-xs">
          <tbody>
            <tr className="border-t border-border">
              <Td>Additional crew: mobilisation per crew per activity</Td>
              <Td right>{aed(crewRules.mobilisation_aed_per_crew_per_activity)}</Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Additional crew: day rate</Td>
              <Td right>{aed(crewRules.day_rate_aed)}</Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Most extra crews per activity</Td>
              <Td right>{crewRules.max_additional_crews_per_activity}</Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Activities that can take an extra crew</Td>
              <Td right wrap>
                {Object.entries(crewRules.eligible_activities_by_change_type).map(([ct, acts]) => (
                  <div key={ct}>
                    {label(ct)}: {acts.join(", ")}
                  </div>
                ))}
              </Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Time-related cost per working day of delay</Td>
              <Td right>{aed(cost.time_related_cost_per_working_day_aed)}</Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Cost contingency remaining</Td>
              <Td right>{aed(cost.cost_contingency_remaining_aed)}</Td>
            </tr>
          </tbody>
        </table>
        <Rule>
          <span className="font-semibold">Extra crew cost: </span>
          {crewRules.rule}
          <br />
          <span className="font-semibold">Total cost: </span>
          {cost.total_cost_rule}
        </Rule>
        <ul className="flex flex-col gap-1 text-xs">
          {cost.clauses.map((c) => (
            <li key={c.clause}>
              <span className="font-semibold text-accent">
                {c.clause} {c.title}:
              </span>{" "}
              <span className="text-text-muted">{c.text}</span>
            </li>
          ))}
        </ul>
        <Source>{cost.source}</Source>
      </Section>

      <Section id="time" title="How time is calculated" refs={refs}>
        <table className="w-full text-xs">
          <tbody>
            <tr className="border-t border-border">
              <Td>Working calendar</Td>
              <Td right wrap>
                {time.calendar.working_days.join(", ")} (not {time.calendar.non_working_days.join(", ")}); day 0 is{" "}
                {formatDate(time.calendar.start_date)}
                {time.calendar.holidays.length ? `; holidays ${time.calendar.holidays.join(", ")}` : "; no holidays"}
              </Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Data date</Td>
              <Td right>
                working day {time.data_date_working_day} ({formatDate(time.data_date)})
              </Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Contract completion</Td>
              <Td right>
                working day {time.contract_completion_working_day} ({formatDate(time.contract_completion_date)})
              </Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Completion in the unchanged programme</Td>
              <Td right>
                working day {time.baseline_completion_working_day} ({formatDate(time.baseline_completion_date)})
              </Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Time buffer</Td>
              <Td right>{workingDays(time.time_buffer_working_days)}</Td>
            </tr>
            <tr className="border-t border-border">
              <Td>Employer's commitment</Td>
              <Td right>
                working day {time.employer_commitment_working_day} ({formatDate(time.employer_commitment_date)})
              </Td>
            </tr>
          </tbody>
        </table>
        <Rule>
          <span className="font-semibold">Added duration: </span>
          {time.added_duration_rule}
          <br />
          <span className="font-semibold">Extra crew: </span>
          {time.additional_crew_rule}
          <br />
          <span className="font-semibold">Delay: </span>
          {time.delay_rule}
          <br />
          <span className="font-semibold">Buffer and contingency: </span>
          {time.buffer_rule}
        </Rule>
        <div className="text-xs">
          <span className="font-semibold">Critical path (zero float): </span>
          <span className="font-mono">{time.baseline_critical_path.join(" > ")}</span>
        </div>
        <table className="w-full text-xs">
          <thead className="text-text-muted">
            <tr><Th>Activity</Th><Th right>Duration</Th><Th right>Start</Th><Th right>Finish</Th><Th right>Float</Th></tr>
          </thead>
          <tbody>
            {time.activities.map((a) => (
              <tr key={a.activity_id} className={`border-t border-border ${a.critical ? "font-semibold" : ""}`}>
                <Td>
                  <span className="font-mono">{a.activity_id}</span> {a.name}
                </Td>
                <Td right>{a.duration}</Td>
                <Td right>{a.early_start}</Td>
                <Td right>{a.early_finish}</Td>
                <Td right>{a.total_float}</Td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-[11px] text-text-muted">
          Working days, unchanged programme. Critical activities are in bold. Float is how many days an activity can
          slip before completion moves.
        </p>
        <ul className="flex flex-col gap-1 text-xs">
          {time.clauses.map((c) => (
            <li key={c.clause}>
              <span className="font-semibold text-accent">
                {c.clause} {c.title}:
              </span>{" "}
              <span className="text-text-muted">{c.text}</span>
            </li>
          ))}
        </ul>
        <Source>{time.source}</Source>
      </Section>

      <Section id="quantities" title="Quantity rules per change type" refs={refs}>
        {data.quantity_rules.map((r) => (
          <QuantityRuleCard key={r.change_type} rule={r} />
        ))}
        <Source>{data.quantity_rules_source}</Source>
      </Section>

      <Section id="example" title={`Worked example${changeType ? `: ${changeType.title}` : ""}`} refs={refs}>
        {!changeType ? (
          <p className="rounded-card bg-surface p-3 text-xs text-text-muted">
            Choose a change on the left to see its worked example here.
          </p>
        ) : exampleError ? (
          <ErrorState message={exampleError} />
        ) : !example || example.change_type !== changeType.id ? (
          <LoadingState message="Working out the example" />
        ) : (
          <>
            <p className="text-xs text-text-muted">
              For{" "}
              {changeType.parameters
                .map((p) => `${p.label.toLowerCase()} ${formatNumber(example.parameters[p.name] ?? p.default)}`)
                .join(", ")}
              , as set on the left.
            </p>
            <Example example={example} />
          </>
        )}
      </Section>
    </div>
  );
}
