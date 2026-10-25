import { useRoom } from "../../state/RoomContext";
import { EmptyState, LoadingState } from "../layout/Panel";

/** "An agent is working on this" while the run goes on; a plain notice once the run has stopped or ended
 * without producing it. */
export function Waiting({ message }: { message: string }) {
  const { state } = useRoom();
  if (state.status === "failed") return <EmptyState message="Not available: the run stopped before this was produced." />;
  if (state.status === "completed" || state.status === "rejected") {
    return <EmptyState message="Not produced in this run." />;
  }
  return <LoadingState message={message} />;
}
