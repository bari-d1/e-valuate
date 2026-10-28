import React, { useEffect, useRef } from "react";
import { color, font, radius, space } from "../../../theme.js";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * A dialog over the current page: the page behind is dimmed and can't be scrolled.
 * Closes on Escape, the close button or a click on the backdrop; keeps keyboard focus
 * inside while open and returns it to where it was on close.
 */
export default function Modal({ title, labelledBy, onClose, children, width = 980 }) {
  const dialog = useRef(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const before = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab" || !dialog.current) return;
      const items = [...dialog.current.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      before?.focus?.();
    };
  }, []);

  return (
    <div
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(15, 23, 42, 0.55)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: `${space.xl}px ${space.lg}px`,
        overflowY: "auto",
      }}
    >
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-label={labelledBy ? undefined : title}
        aria-labelledby={labelledBy}
        tabIndex={-1}
        style={{
          position: "relative",
          width: `min(${width}px, 100%)`,
          background: color.surface,
          borderRadius: radius.lg,
          boxShadow: "0 24px 60px rgba(15, 23, 42, 0.35)",
          padding: "56px clamp(16px, 4vw, 24px) 24px", // room for the close button above the content
          outline: "none",
        }}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          style={{
            position: "absolute",
            top: space.sm,
            right: space.sm,
            width: 40,
            height: 40,
            border: 0,
            borderRadius: radius.pill,
            background: "transparent",
            color: color.textMuted,
            fontSize: 24,
            lineHeight: 1,
            fontWeight: font.weight.bold,
            cursor: "pointer",
          }}
        >
          ×
        </button>
        {children}
      </div>
    </div>
  );
}
