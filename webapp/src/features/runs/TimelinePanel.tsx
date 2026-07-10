import { Activity } from "lucide-react";
import { useRef } from "react";
import { copy, formatBackendText, formatStageLabel, getTimelineDetail } from "../../lib/formatters/workbench";
import type { RunRecord } from "../../types/workbench";
import { classNames } from "../../lib/formatters/workbench";
import { useListEntranceMotion } from "../../lib/motion/useAnimeEntrance";

export function TimelinePanel({
  record,
  error,
  isHistoricalDemo,
}: {
  record: RunRecord | null;
  error: string | null;
  isHistoricalDemo: boolean;
}) {
  const events = record?.timeline ?? [];
  const eventListRef = useRef<HTMLDivElement | null>(null);
  useListEntranceMotion(eventListRef, `${record?.run_id ?? "empty"}-${events.length}`);

  if (!error && events.length === 0) return null;
  return (
    <section className="timeline-panel">
      <div className="section-title">
        <Activity size={18} />
        <h2>过程记录</h2>
      </div>
      {error ? <div className="status-banner warning" role="status">{error}</div> : null}
      {events.length === 0 ? (
        <div className="empty-state">
          {isHistoricalDemo
            ? "这是历史合成记录；若当时未保留过程事件，这里不会再补生成新的轨迹。"
            : "还没有运行事件。实时模式会在运行开始后流式返回研究工作流事件。"}
        </div>
      ) : (
        <div className="event-list" ref={eventListRef}>
          {events.map((event, index) => {
            const detail = getTimelineDetail(event);
            return (
              <div className={classNames("event-row", event.status)} key={`${event.stage}-${index}`}>
                <span className="event-time">{event.time}</span>
                <span className="event-stage">{formatStageLabel(event.stage)}</span>
                <span className="event-copy">
                  <strong>
                    {event.status === "error" ? copy.workflow.stageNeedsAttention : formatBackendText(event.event)}
                  </strong>
                  {detail ? <em>{detail}</em> : null}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
