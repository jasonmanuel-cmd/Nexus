import React, { useEffect, useRef, useState } from "react";

/**
 * Ticker — animates a numeric value from 0 → target.
 * Props: value (number), prefix, suffix, decimals, duration, format
 */
export const Ticker = ({ value = 0, prefix = "", suffix = "", decimals = 0, duration = 1200, format }) => {
  const [n, setN] = useState(0);
  const rafRef = useRef(null);
  const startRef = useRef(null);
  const fromRef = useRef(0);

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    startRef.current = null;
    fromRef.current = n;
    const target = Number(value) || 0;

    const tick = (t) => {
      if (!startRef.current) startRef.current = t;
      const elapsed = t - startRef.current;
      const p = Math.min(1, elapsed / duration);
      const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
      const current = fromRef.current + (target - fromRef.current) * eased;
      setN(current);
      if (p < 1) rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const display = format
    ? format(n)
    : `${prefix}${n.toLocaleString("en-US", { maximumFractionDigits: decimals, minimumFractionDigits: decimals })}${suffix}`;

  return <span>{display}</span>;
};

export default Ticker;
