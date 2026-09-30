import React from "react";



export default function GenerateQuestionsAIPage(props) {
  console.log("[GenerateQuestionsAI] render ✅", props);

  return (
    <div style={{ padding: 20 }}>
      <div style={{ fontWeight: 900, marginBottom: 8 }}>
        GenerateQuestionsAIPage is rendering ✅
      </div>

      <div style={{ fontSize: 12, fontFamily: "monospace", whiteSpace: "pre-wrap" }}>
        task should be: generate_questions_ai
        {"\n\n"}
        props keys: {Object.keys(props || {}).join(", ")}
        {"\n\n"}
        ui keys: {Object.keys(props?.ui || {}).join(", ")}
      </div>
    </div>
  );
}
