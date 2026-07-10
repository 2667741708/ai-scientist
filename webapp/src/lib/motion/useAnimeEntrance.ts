import { createTimeline, stagger } from "animejs";
import { type RefObject, useEffect } from "react";
import { useReducedMotion } from "./useReducedMotion";

type MotionRef = RefObject<HTMLElement | null>;

function getMotionTargets(root: HTMLElement) {
  return {
    header: root.querySelectorAll<HTMLElement>(
      ".page-header-copy, .page-header-actions, .panel-heading, .output-header",
    ),
    surfaces: root.querySelectorAll<HTMLElement>(
      ".surface-card, .run-panel, .output-workspace, .task-surface, .state-card",
    ),
  };
}

export function useRouteEntranceMotion(containerRef: MotionRef, motionKey: string) {
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    const root = containerRef.current;
    if (!root || prefersReducedMotion) return undefined;
    const { header, surfaces } = getMotionTargets(root);
    const timeline = createTimeline({
      defaults: {
        ease: "outCubic",
      },
    });

    if (header.length > 0) {
      timeline.add(header, {
        opacity: [0, 1],
        y: [12, 0],
        duration: 280,
        delay: stagger(24),
      });
    }

    if (surfaces.length > 0) {
      timeline.add(
        surfaces,
        {
          opacity: [0, 1],
          y: [18, 0],
          scale: [0.985, 1],
          duration: 420,
          delay: stagger(42),
        },
        "<<+=80",
      );
    }

    return () => {
      timeline.revert();
    };
  }, [containerRef, motionKey, prefersReducedMotion]);
}

export function useListEntranceMotion(
  containerRef: MotionRef,
  motionKey: string,
  selector = ":scope > *",
) {
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    const root = containerRef.current;
    if (!root || prefersReducedMotion) return undefined;
    const targets = root.querySelectorAll<HTMLElement>(selector);
    if (targets.length === 0) return undefined;
    const animation = createTimeline({
      defaults: {
        ease: "outCubic",
      },
    }).add(targets, {
      opacity: [0, 1],
      y: [14, 0],
      duration: 360,
      delay: stagger(55),
    });

    return () => {
      animation.revert();
    };
  }, [containerRef, motionKey, prefersReducedMotion, selector]);
}

export function useDrawerEntranceMotion(containerRef: MotionRef) {
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    const root = containerRef.current;
    if (!root || prefersReducedMotion) return undefined;
    const animation = createTimeline({
      defaults: {
        ease: "outCubic",
      },
    })
      .add(root, {
        opacity: [0, 1],
        duration: 180,
      })
      .add(
        root.querySelectorAll<HTMLElement>(".reference-drawer"),
        {
          opacity: [0, 1],
          x: [28, 0],
          duration: 320,
        },
        "<<",
      )
      .add(
        root.querySelectorAll<HTMLElement>(".reference-section, .drawer-note"),
        {
          opacity: [0, 1],
          y: [10, 0],
          duration: 260,
          delay: stagger(42),
        },
        "<<+=120",
      );

    return () => {
      animation.revert();
    };
  }, [containerRef, prefersReducedMotion]);
}
