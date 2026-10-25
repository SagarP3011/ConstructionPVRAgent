import type { ReactNode } from "react";
import { Panel } from "../layout/Panel";
import { BoqLines } from "./BoqLines";
import { ChangeCard } from "./ChangeCard";
import { Clauses } from "./Clauses";
import { DrawingDiff } from "./DrawingDiff";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs tracking-wide text-text-muted uppercase">{title}</h3>
      {children}
    </section>
  );
}

/** Left column: the change, the drawing or parameter diff, the BOQ lines and the cited clauses. */
export function EvidencePanel() {
  return (
    <Panel title="Evidence" hint="What the agents work from: the change request, the drawing revisions, the bill of quantities and the contract clauses.">
      <div className="flex flex-col gap-5">
        <ChangeCard />
        <DrawingDiff />
        <Section title="BOQ (bill of quantities) lines">
          <BoqLines />
        </Section>
        <Section title="Cited contract clauses">
          <Clauses />
        </Section>
      </div>
    </Panel>
  );
}
