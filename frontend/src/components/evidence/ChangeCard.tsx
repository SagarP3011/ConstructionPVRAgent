import { aed, formatDate, workingDays } from "../../format";
import { useRoom } from "../../state/RoomContext";
import { LoadingState } from "../layout/Panel";

/** The change instruction and, in contractor PVR mode, the instruction and the contractor's claim. */
export function ChangeCard() {
  const { state } = useRoom();
  const cr = state.results.changeRequest;
  const notice = state.results.notice;
  if (!cr) return <LoadingState message="The Intake agent is reading the change" />;
  return (
    <div className="flex flex-col gap-3 text-sm">
      <div>
        <div className="text-xs text-text-muted">{cr.id}</div>
        <h3 className="text-base">{cr.title}</h3>
        <p className="mt-1 leading-relaxed">{cr.instruction_text}</p>
      </div>
      {cr.variation_instruction ? (
        <div className="rounded-card bg-surface p-3">
          <div className="text-xs font-semibold text-accent">
            {cr.variation_instruction.ref} · issued by the {cr.variation_instruction.issued_by} ·{" "}
            {formatDate(cr.variation_instruction.date)}
          </div>
        </div>
      ) : null}
      {cr.contractor_pvr ? (
        <div className="rounded-card border border-border p-3">
          <div className="text-xs font-semibold text-accent">
            {cr.contractor_pvr.ref} from {cr.contractor_pvr.contractor} · {formatDate(cr.contractor_pvr.date)}
          </div>
          <p className="mt-1 text-xs leading-relaxed text-text-muted">{cr.contractor_pvr.text}</p>
          <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
            <dt className="text-text-muted">Claimed</dt>
            <dd className="text-right font-bold">{aed(cr.contractor_pvr.claimed_total_aed)}</dd>
            <dt className="text-text-muted">Extension claimed</dt>
            <dd className="text-right font-bold">{workingDays(cr.contractor_pvr.claimed_extension_working_days)}</dd>
          </dl>
        </div>
      ) : null}
      {notice ? (
        <div className={`text-xs ${notice.within_limit ? "text-text-muted" : "text-alert"}`}>
          Notice given {notice.calendar_days} calendar days after the instruction;{" "}
          {notice.within_limit ? "within" : "outside"} the {notice.limit_days}-day limit (clause {notice.clause}).
        </div>
      ) : null}
    </div>
  );
}
