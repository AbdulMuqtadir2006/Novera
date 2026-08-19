import { Link } from "react-router-dom";
import { Github, Twitter, Linkedin } from "lucide-react";
import { Wordmark } from "../ui/Wordmark";

const columns = [
  {
    title: "Product",
    links: [
      { label: "Our Product", to: "/buy" },
      { label: "Dashboard", to: "/dashboard" },
      { label: "Reports", to: "/reports" },
      { label: "Voice", to: "/voice" },
      { label: "Natural Recovery", to: "/self-care" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About", to: "/more" },
      { label: "Research", to: "/more" },
      { label: "Careers", to: "/more" },
      { label: "Contact", to: "/more" },
    ],
  },
  {
    title: "Legal",
    links: [
      { label: "Privacy", to: "/more" },
      { label: "Terms", to: "/more" },
      { label: "Research disclaimer", to: "/more" },
    ],
  },
];

const socials = [
  { icon: Twitter, label: "Novera on X" },
  { icon: Linkedin, label: "Novera on LinkedIn" },
  { icon: Github, label: "Novera on GitHub" },
];

export function Footer() {
  return (
    <footer className="relative z-10 border-t border-white/10 bg-ink text-slate-300">
      <div className="container-page py-14">
        <div className="grid gap-10 md:grid-cols-[1.5fr_1fr_1fr_1fr]">
          <div className="max-w-xs">
            <Wordmark tone="light" />
            <p className="mt-4 text-sm leading-relaxed text-slate-400">
              An agentic AI saliva biosensor platform, turning a single sample
              into a screening summary you can actually read.
            </p>
            <div className="mt-6 flex gap-3">
              {socials.map(({ icon: Icon, label }) => (
                <a
                  key={label}
                  href="#"
                  aria-label={label}
                  className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/10 text-slate-400 transition-colors duration-200 hover:border-signal/50 hover:text-signal"
                >
                  <Icon size={18} />
                </a>
              ))}
            </div>
          </div>

          {columns.map((col) => (
            <div key={col.title}>
              <h4 className="font-mono text-xs uppercase tracking-[0.2em] text-slate-500">
                {col.title}
              </h4>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((l, i) => (
                  <li key={`${l.label}-${i}`}>
                    <Link
                      to={l.to}
                      className="text-sm text-slate-400 transition-colors duration-200 hover:text-signal"
                    >
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 border-t border-white/10 pt-6">
          <p className="max-w-3xl text-xs leading-relaxed text-slate-500">
            Novera is a research-stage screening platform, built to explore what
            saliva biomarkers can tell us — not to diagnose, treat, or replace
            care from a medical professional.
          </p>
          <p className="mt-4 text-xs text-slate-600">
            © {new Date().getFullYear()} Novera Research. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
