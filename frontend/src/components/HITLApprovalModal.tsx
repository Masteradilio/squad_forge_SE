import React, { useState } from 'react';

export interface HITLGateData {
  gate_id: string;
  gate_type: string;
  role_name: string;
  prompt_message: string;
  question_options?: Record<string, any>;
  status: string;
}

interface HITLApprovalModalProps {
  gate: HITLGateData | null;
  onResolve: (gate_id: string, response: string, approve: boolean) => void;
}

export const HITLApprovalModal: React.FC<HITLApprovalModalProps> = ({ gate, onResolve }) => {
  const [inputText, setInputText] = useState('');

  if (!gate || gate.status !== 'PAUSED') return null;

  const isDynamicInput = gate.gate_type === 'DYNAMIC_INPUT';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4">
      <div className="bg-slate-900 border border-amber-500/50 rounded-2xl shadow-2xl max-w-lg w-full p-6 animate-in fade-in zoom-in-95">
        <div className="flex items-center gap-3 mb-4 border-b border-slate-800 pb-3">
          <div className="w-10 h-10 rounded-full bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 text-xl font-bold">
            ⚠️
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-100">
              {isDynamicInput ? 'Dynamic PO Clarification Required' : 'Human-in-the-Loop (HITL) Gate'}
            </h3>
            <p className="text-xs text-amber-400 font-mono">Agent Role: {gate.role_name}</p>
          </div>
        </div>

        <p className="text-sm text-slate-300 mb-6 bg-slate-950 p-4 rounded-xl border border-slate-800 font-mono leading-relaxed">
          {gate.prompt_message}
        </p>

        {isDynamicInput ? (
          <div className="mb-6">
            <label className="block text-xs font-semibold text-slate-400 mb-2">Provide Input for Squad:</label>
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="Type clarification or value here..."
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            />
          </div>
        ) : null}

        <div className="flex items-center justify-end gap-3 pt-2">
          {!isDynamicInput && (
            <button
              onClick={() => onResolve(gate.gate_id, 'Rejected by PO', false)}
              className="px-4 py-2 rounded-lg bg-rose-950 hover:bg-rose-900 text-rose-300 text-xs font-bold border border-rose-800 transition-all"
            >
              Reject / Request Adjustment
            </button>
          )}
          <button
            onClick={() => onResolve(gate.gate_id, inputText || 'Approved by PO', true)}
            className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow-lg shadow-emerald-900/30 transition-all"
          >
            {isDynamicInput ? 'Submit Clarification' : 'Approve Execution'}
          </button>
        </div>
      </div>
    </div>
  );
};
