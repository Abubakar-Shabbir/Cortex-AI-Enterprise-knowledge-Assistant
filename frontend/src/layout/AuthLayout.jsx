import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Lock } from 'lucide-react';
import Logo from '../components/Logo';

// Port of templates/auth_base.html — the split brand-panel shell every
// auth page (Login/Signup/Verify OTP/Forgot Password/Reset) renders
// inside. Keeps the exact same ambient "live enterprise system"
// decoration (grid backplane, drifting glow orbs, pulsing node/line
// network, rising telemetry particles, pointer-parallax, status pill)
// and the same card chrome (auth-card, "Secure sign-in" footer) as the
// Django template — see index.css's "Auth flow ambient styling"
// section for the ported keyframes/classes.
export default function AuthLayout({ title, children }) {
  const rootRef = useRef(null);
  const layerRef = useRef(null);

  useEffect(() => {
    if (title) document.title = `${title} · Cortex`;
  }, [title]);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (!window.matchMedia('(pointer: fine)').matches) return;

    const root = rootRef.current;
    const layer = layerRef.current;
    if (!root || !layer) return;

    const MAX_OFFSET_PX = 10;

    const onMove = (event) => {
      const rect = root.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
      const y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
      layer.style.transform = `translate(${x * MAX_OFFSET_PX}px, ${y * MAX_OFFSET_PX}px)`;
    };
    const onLeave = () => {
      layer.style.transform = 'translate(0, 0)';
    };

    root.addEventListener('mousemove', onMove);
    root.addEventListener('mouseleave', onLeave);
    return () => {
      root.removeEventListener('mousemove', onMove);
      root.removeEventListener('mouseleave', onLeave);
    };
  }, []);

  return (
    <div className="flex min-h-screen bg-surface dark:bg-surface-dark">
      {/* Brand panel */}
      <div ref={rootRef} className="relative hidden w-[42%] max-w-[560px] shrink-0 overflow-hidden bg-primary lg:flex lg:flex-col lg:justify-between dark:bg-primary-dark">
        <div className="pointer-events-none absolute inset-0 auth-grid-bg" aria-hidden="true"></div>

        <div ref={layerRef} id="auth-parallax-layer" className="pointer-events-none absolute inset-0" aria-hidden="true">
          <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/10 blur-3xl auth-glow-a"></div>
          <div className="absolute -bottom-32 -left-16 h-80 w-80 rounded-full bg-black/10 blur-3xl auth-glow-b"></div>

          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 400 700" preserveAspectRatio="none">
            <g stroke="white" strokeOpacity="0.16" strokeWidth="1" fill="none">
              <path className="auth-flow-line" d="M40,120 L150,190 L120,340" strokeDasharray="6 14"></path>
              <path className="auth-flow-line" style={{ animationDelay: '-3s' }} d="M340,90 L250,220 L300,380" strokeDasharray="6 14"></path>
              <path className="auth-flow-line" style={{ animationDelay: '-6s' }} d="M60,560 L180,480 L330,540" strokeDasharray="6 14"></path>
            </g>
            <g fill="white">
              <circle className="auth-node" cx="40" cy="120" r="3"></circle>
              <circle className="auth-node" cx="150" cy="190" r="2.5" style={{ animationDelay: '-0.6s' }}></circle>
              <circle className="auth-node" cx="120" cy="340" r="3" style={{ animationDelay: '-1.4s' }}></circle>
              <circle className="auth-node" cx="340" cy="90" r="2.5" style={{ animationDelay: '-2s' }}></circle>
              <circle className="auth-node" cx="250" cy="220" r="3" style={{ animationDelay: '-1s' }}></circle>
              <circle className="auth-node" cx="300" cy="380" r="2.5" style={{ animationDelay: '-2.6s' }}></circle>
              <circle className="auth-node" cx="60" cy="560" r="3" style={{ animationDelay: '-1.8s' }}></circle>
              <circle className="auth-node" cx="180" cy="480" r="2.5" style={{ animationDelay: '-0.3s' }}></circle>
              <circle className="auth-node" cx="330" cy="540" r="3" style={{ animationDelay: '-2.2s' }}></circle>
            </g>
          </svg>

          <span className="auth-particle absolute h-1 w-1 rounded-full bg-white/70" style={{ left: '12%', top: '88%', '--drift-duration': '12s', '--drift-delay': '-1s', '--drift-x': '18px' }}></span>
          <span className="auth-particle absolute h-[3px] w-[3px] rounded-full bg-white/50" style={{ left: '28%', top: '95%', '--drift-duration': '16s', '--drift-delay': '-6s', '--drift-x': '-14px' }}></span>
          <span className="auth-particle absolute h-1 w-1 rounded-full bg-white/60" style={{ left: '47%', top: '82%', '--drift-duration': '13.5s', '--drift-delay': '-3s', '--drift-x': '10px' }}></span>
          <span className="auth-particle absolute h-[3px] w-[3px] rounded-full bg-white/40" style={{ left: '63%', top: '98%', '--drift-duration': '18s', '--drift-delay': '-9s', '--drift-x': '-22px' }}></span>
          <span className="auth-particle absolute h-1 w-1 rounded-full bg-white/60" style={{ left: '78%', top: '90%', '--drift-duration': '15s', '--drift-delay': '-4.5s', '--drift-x': '16px' }}></span>
          <span className="auth-particle absolute h-[3px] w-[3px] rounded-full bg-white/50" style={{ left: '90%', top: '85%', '--drift-duration': '11s', '--drift-delay': '-7s', '--drift-x': '-12px' }}></span>
          <span className="auth-particle absolute h-1 w-1 rounded-full bg-white/45" style={{ left: '6%', top: '60%', '--drift-duration': '17s', '--drift-delay': '-2s', '--drift-x': '20px' }}></span>
          <span className="auth-particle absolute h-1 w-1 rounded-full bg-white/55" style={{ left: '82%', top: '55%', '--drift-duration': '14.5s', '--drift-delay': '-10s', '--drift-x': '-18px' }}></span>
        </div>

        <div className="relative px-10 pt-10">
          <Link to="/login" className="inline-flex items-center gap-2.5 text-white">
            <Logo size="h-9 w-9" mono />
            <span className="text-sm font-semibold">Cortex</span>
          </Link>
        </div>

        <div className="relative px-10">
          <h2 className="max-w-sm text-2xl font-bold leading-snug tracking-tight text-white">
            Answers grounded in your own documents.
          </h2>
          <p className="mt-3 max-w-sm text-sm leading-relaxed text-white/75">
            An enterprise knowledge assistant that reads what you upload, cites where every answer came from, and maps how your information connects.
          </p>

          <ul className="mt-8 space-y-5">
            <li className="flex items-start gap-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/10 text-white">
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>
              </span>
              <div>
                <p className="text-sm font-semibold text-white">Knowledge Graph</p>
                <p className="text-xs leading-relaxed text-white/70">Entities and relationships are extracted automatically, so you can explore how your documents connect.</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/10 text-white">
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V20c0 1 0 1 1 1z"></path><path d="M15 21c3 0 7-1 7-8V5c0-1.25-.757-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2h.75c0 2.25.25 4-2.75 4v3c0 1 0 1 1 1z"></path></svg>
              </span>
              <div>
                <p className="text-sm font-semibold text-white">Grounded, Cited Answers</p>
                <p className="text-xs leading-relaxed text-white/70">Every answer traces back to the exact source chunk it came from — never guesswork.</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/10 text-white">
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"></path><path d="m9 12 2 2 4-4"></path></svg>
              </span>
              <div>
                <p className="text-sm font-semibold text-white">Private by Default</p>
                <p className="text-xs leading-relaxed text-white/70">Your documents, questions, and answers are scoped to your account alone.</p>
              </div>
            </li>
          </ul>
        </div>

        <div className="relative px-10 pb-10">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-white/80">
            <span className="relative flex h-1.5 w-1.5">
              <span className="auth-status-ping absolute inline-flex h-full w-full rounded-full bg-emerald-300"></span>
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-300"></span>
            </span>
            <span className="text-[11px] font-medium tracking-wide">Secure connection active</span>
          </div>
          <p className="text-xs text-white/50">
            &copy; {new Date().getFullYear()} Cortex · Enterprise Edition
          </p>
        </div>
      </div>

      {/* Form panel */}
      <div className="relative flex min-h-screen flex-1 flex-col items-center justify-center overflow-hidden px-6 py-10">
        <div className="pointer-events-none absolute right-[-10%] top-[-10%] h-96 w-96 rounded-full bg-primary/[0.04] blur-3xl dark:bg-primary/[0.08]" aria-hidden="true"></div>

        <Link to="/login" className="relative mb-8 flex items-center gap-2.5 text-primary lg:hidden dark:text-primary-soft">
          <Logo size="h-9 w-9" />
          <span className="text-sm font-semibold text-ink dark:text-ink-dark">Cortex</span>
        </Link>

        <div className="relative w-full max-w-[400px]">
          <div className="auth-card rounded-2xl border border-line bg-card p-8 shadow-soft dark:border-line-dark dark:bg-card-dark">
            {children}
          </div>

          <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-xs text-muted dark:text-muted-dark">
            <Lock className="h-3.5 w-3.5" /> Secure sign-in
          </p>
        </div>
      </div>
    </div>
  );
}
