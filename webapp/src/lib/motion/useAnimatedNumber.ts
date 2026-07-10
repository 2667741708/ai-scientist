import { animate } from "animejs";
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "./useReducedMotion";

export function useAnimatedNumber(value: number, options?: { duration?: number; formatter?: (value: number) => string }) {
  const prefersReducedMotion = useReducedMotion();
  const previousValueRef = useRef(value);
  const [displayValue, setDisplayValue] = useState(() => formatValue(value, options?.formatter));

  useEffect(() => {
    if (prefersReducedMotion) {
      previousValueRef.current = value;
      setDisplayValue(formatValue(value, options?.formatter));
      return undefined;
    }

    const state = { value: previousValueRef.current };
    const animation = animate(state, {
      value,
      duration: options?.duration ?? 520,
      ease: "outCubic",
      onRender: () => {
        setDisplayValue(formatValue(state.value, options?.formatter));
      },
    });

    previousValueRef.current = value;
    return () => {
      animation.revert();
    };
  }, [options?.duration, options?.formatter, prefersReducedMotion, value]);

  return displayValue;
}

function formatValue(value: number, formatter?: (value: number) => string) {
  if (formatter) return formatter(value);
  return String(Math.round(value));
}
