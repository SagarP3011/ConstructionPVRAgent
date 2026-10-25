import { useRef } from "react";
import { outputUrl } from "../../api/client";

interface PvrFormPreviewProps {
  runId: string;
  file: string;
  title: string;
}

/** An HTML artifact written by an approved action, shown in a frame, with print to PDF. */
export function PvrFormPreview({ runId, file, title }: PvrFormPreviewProps) {
  const frame = useRef<HTMLIFrameElement>(null);
  const url = outputUrl(runId, file);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm">{title}</h3>
        <div className="flex gap-2 text-xs">
          <a href={url} target="_blank" rel="noreferrer" className="rounded-full border border-border px-3 py-1 text-accent hover:border-accent">
            Open
          </a>
          <button
            type="button"
            onClick={() => frame.current?.contentWindow?.print()}
            className="rounded-full bg-accent px-3 py-1 font-semibold text-white"
          >
            Print to PDF
          </button>
        </div>
      </div>
      <iframe ref={frame} src={url} title={title} className="h-[420px] w-full rounded-card border border-border bg-white" />
    </div>
  );
}
