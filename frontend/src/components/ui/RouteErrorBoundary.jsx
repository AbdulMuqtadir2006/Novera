import { Component } from "react";
import { RefreshCw, TriangleAlert } from "lucide-react";

// Root-level safety net: without this, ANY uncaught render error on any
// page unmounts the whole React tree, leaving only <body>'s bg-ink behind
// — a black screen with nothing on it and no way to recover except manually
// reloading (reported live: crashes right after adding a reading and
// navigating to another page). Doesn't depend on LanguageContext or any
// other app state, since that could plausibly be part of what's broken.
export class RouteErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error("[RouteErrorBoundary] a page crashed:", error, info?.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    const rtl = typeof document !== "undefined" && document.documentElement.dir === "rtl";
    const t = rtl
      ? {
          title: "حدث خطأ غير متوقع",
          body: "واجهت هذه الصفحة خطأً غير متوقع. عادةً ما تحل إعادة التحميل المشكلة.",
          reload: "إعادة تحميل الصفحة",
        }
      : {
          title: "Something went wrong",
          body: "This page hit an unexpected error. Reloading usually fixes it.",
          reload: "Reload page",
        };
    return (
      <div dir={rtl ? "rtl" : "ltr"} className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-mist px-6 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-status-attention/10 text-status-attention">
          <TriangleAlert size={26} />
        </span>
        <h1 className="font-display text-2xl font-bold text-depth">{t.title}</h1>
        <p className="max-w-sm text-sm leading-relaxed text-depth/60">{t.body}</p>
        <button type="button" onClick={() => window.location.reload()} className="btn-primary mt-2">
          <RefreshCw size={16} /> {t.reload}
        </button>
      </div>
    );
  }
}
