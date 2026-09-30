import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }

  componentDidCatch(error, info) {
    // show in console too
    console.error("[ErrorBoundary]", error, info);
    this.setState({ error, info });
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 16, fontFamily: "system-ui", background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 12 }}>
          <div style={{ fontWeight: 900, color: "#991B1B" }}>App crashed</div>
          <pre style={{ whiteSpace: "pre-wrap", marginTop: 10, color: "#991B1B" }}>
            {String(this.state.error?.message || this.state.error)}
          </pre>
          <pre style={{ whiteSpace: "pre-wrap", marginTop: 10, color: "#7F1D1D", fontSize: 12 }}>
            {String(this.state.info?.componentStack || "")}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}
