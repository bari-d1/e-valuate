// src/routes/AppRoutes.jsx
import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLegacy from "../AppLegacy";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/consultant" replace />} />

      {/* Consultant */}
      <Route path="/consultant/*" element={<AppLegacy />} />

     

      {/* during migration, send anything unknown to consultant */}
      <Route path="*" element={<Navigate to="/consultant" replace />} />
    </Routes>
  );
}
