import { Component } from "react";

// Catches WebGL init failures (context creation can throw synchronously on
// some GPU-blocklisted/software-rendering browsers) so a single visual
// section can never blank the rest of the marketing page.
export class FlowErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn("AgentFlow3D: falling back to static view —", error);
    }
  }

  render() {
    if (this.state.hasError) return this.props.fallback;
    return this.props.children;
  }
}
