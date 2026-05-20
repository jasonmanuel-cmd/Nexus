import React from "react";

const LABEL = {
  idle: "IDLE",
  scanning: "SCANNING",
  thinking: "THINKING",
  closing: "CLOSING",
};

const COLOR = {
  idle: "#52525b",
  scanning: "#00f5d4",
  thinking: "#ff5500",
  closing: "#fafafa",
};

export const AgentStatus = ({ status = "idle", label, size = "sm", testid }) => {
  const dotClass = `nx-dot nx-dot-${status}`;
  const text = label ?? LABEL[status];
  return (
    <span
      className="inline-flex items-center gap-2"
      data-testid={testid || `agent-status-${status}`}
    >
      <span className={dotClass} style={{ background: COLOR[status] }} />
      <span
        className="nx-label"
        style={{ color: COLOR[status], fontSize: size === "xs" ? 9 : 10 }}
      >
        {text}
      </span>
    </span>
  );
};

export default AgentStatus;
