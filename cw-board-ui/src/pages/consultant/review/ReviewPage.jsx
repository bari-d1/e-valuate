import React, { useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { CONSULTANT_NAME_KEY } from "../../../api/questionBankApi.js";
import { color, font, radius, space } from "../../../theme.js";
import { inputCss } from "../companies/helpers.js";
import ReviewOverview from "./ReviewOverview.jsx";
import ParticipantReview from "./ParticipantReview.jsx";
import SubjectReview from "./SubjectReview.jsx";

/**
 * Review questions: check, edit and approve every participant's assembled set before anything is sent.
 * Overview (all participants), one participant's set, and every question about one subject.
 */

function readName() {
  try {
    return localStorage.getItem(CONSULTANT_NAME_KEY) || "";
  } catch {
    return "";
  }
}

function tabStyle({ isActive }) {
  return {
    padding: "6px 12px",
    borderRadius: radius.sm,
    border: `1px solid ${isActive ? color.primarySoftBorder : "transparent"}`,
    background: isActive ? color.primarySoft : "transparent",
    color: isActive ? color.primaryText : color.text,
    fontWeight: font.weight.bold,
    fontSize: font.body,
    textDecoration: "none",
  };
}

export default function ReviewPage({ ui, evalId }) {
  const { Card } = ui;
  const [name, setName] = useState(readName);
  const saveName = (v) => {
    setName(v);
    try {
      localStorage.setItem(CONSULTANT_NAME_KEY, v.trim());
    } catch {
      /* the name is optional: changes are then recorded as "consultant" */
    }
  };

  return (
    <Card title="Review questions" subtitle="Check, edit and approve each participant's questions. Nothing reaches a participant until their set is approved.">
      <div style={{ display: "flex", gap: space.md, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", marginBottom: space.md }}>
        <nav aria-label="Review views" style={{ display: "flex", gap: space.xs, flexWrap: "wrap" }}>
          <NavLink to="/consultant/review" end style={tabStyle}>
            Overview
          </NavLink>
          <NavLink to="/consultant/review/participants" style={tabStyle}>
            By participant
          </NavLink>
          <NavLink to="/consultant/review/subjects" style={tabStyle}>
            By subject
          </NavLink>
        </nav>
        <label style={{ display: "flex", gap: space.sm, alignItems: "center", fontSize: 13, color: color.textMuted }}>
          Your name (for the change history)
          <input
            value={name}
            onChange={(e) => saveName(e.target.value)}
            placeholder="e.g. Ada"
            maxLength={80}
            style={inputCss({ width: 160 })}
          />
        </label>
      </div>
      <Routes>
        <Route index element={<ReviewOverview ui={ui} evalId={evalId} />} />
        <Route path="participants" element={<ParticipantReview ui={ui} evalId={evalId} />} />
        <Route path="participants/:participantId" element={<ParticipantReview ui={ui} evalId={evalId} />} />
        <Route path="subjects" element={<SubjectReview ui={ui} evalId={evalId} />} />
        <Route path="subjects/:subjectId" element={<SubjectReview ui={ui} evalId={evalId} />} />
        <Route path="*" element={<Navigate to="/consultant/review" replace />} />
      </Routes>
    </Card>
  );
}
