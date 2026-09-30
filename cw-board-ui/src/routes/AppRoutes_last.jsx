// src/routes/AppRoutes.jsx
import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLegacy from "../AppLegacy";

import MemberLayout from "../pages/member/MemberLayout";
import MemberInvitePage from "../pages/member/MemberInvitePage";
import MemberEvaluationPage from "../pages/member/MemberEvaluationPage";
import MemberQuestionsPage from "../pages/member/MemberQuestionsPage";
import MemberSubmitPage from "../pages/member/MemberSubmitPage";
import MemberThankYouPage from "../pages/member/MemberThankYouPage";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/consultant" replace />} />

      {/* Consultant */}
      <Route path="/consultant/*" element={<AppLegacy />} />

      {/* ✅ Board Member portal (nested) */}
      <Route path="/member" element={<MemberLayout />}>
        <Route index element={<Navigate to="invite" replace />} />

        <Route path="invite" element={<MemberInvitePage />} />
        <Route path="invite/:token" element={<MemberInvitePage />} />

        <Route path=":token/evaluation" element={<MemberEvaluationPage />} />
        <Route path=":token/questions" element={<MemberQuestionsPage />} />
        <Route path=":token/submit" element={<MemberSubmitPage />} />
        <Route path=":token/thank-you" element={<MemberThankYouPage />} />

        {/* fallback inside member */}
        <Route path="*" element={<Navigate to="invite" replace />} />
      </Route>

      {/* during migration, send anything unknown to consultant */}
      <Route path="*" element={<Navigate to="/consultant" replace />} />
    </Routes>
  );
}
