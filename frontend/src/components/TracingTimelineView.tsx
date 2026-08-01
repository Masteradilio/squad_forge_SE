import React from 'react';

export interface TraceSpanItem {
  span_id: str;
  role_name: string;
  action_name: string;
  start_time: number;
  end_time?: number;
  duration_ms?: number;
  tool_calls?: string[];
  status: string;
}

interface TracingTimelineViewProps {
  spans: TraceSpanItem[];
}

export const TracingTimelineView: React.FC<TracingTimelineViewProps> = ({ spans }) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl">
      <div className="flex items-center justify-between mb-6 border-b border-slate-800 pb-4">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <span className="text-cyan-400">📊</span> OpenTelemetry Squad Tracing Timeline
          </h2>
          <p className="text-sm text-slate-400 mt-1">Real-time latency metrics & tool execution per Squad role</p>
        </div>
        <span className="bg-cyan-950 text-cyan-400 text-xs font-mono px-3 py-1 rounded-full border border-cyan-800">
          Live Telemetry: Active
        </span>
      </div>

      {spans.length === 0 ? (
        <div className="text-center py-8 text-slate-500 font-mono text-sm">
          No telemetry spans recorded yet. Launch a Squad run to visualize execution latency.
        </div>
      ) : (
        <div className="space-y-4">
          {spans.map((span) => (
            <div key={span.span_id} className="bg-slate-950 border border-slate-800/80 rounded-lg p-4 transition-all hover:border-cyan-500/50">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
                  <h3 className="font-semibold text-slate-200">{span.role_name}</h3>
                  <span className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded font-mono">
                    {span.action_name}
                  </span>
                </div>
                <div className="flex items-center gap-3 font-mono text-xs">
                  <span className="text-cyan-400 font-bold">{span.duration_ms ? `${span.duration_ms} ms` : 'In Progress'}</span>
                  <span className={`px-2 py-0.5 rounded font-semibold ${
                    span.status === 'SUCCESS' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-amber-950 text-amber-400 border border-amber-800'
                  }`}>
                    {span.status}
                  </span>
                </div>
              </div>

              {span.tool_calls && span.tool_calls.length > 0 && (
                <div className="mt-2 text-xs text-slate-400 font-mono bg-slate-900/60 p-2 rounded border border-slate-800/50">
                  <span className="text-slate-500">Tool Calls:</span> {span.tool_calls.join(', ')}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
