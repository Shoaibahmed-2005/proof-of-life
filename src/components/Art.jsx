/**
 * Original flat illustrations (hand-made SVG, DESIGN.md §5): warm palette,
 * no AI imagery, no emblems or copied artwork. Decorative ones are aria-hidden.
 */

const O = '#E8603C';   // --primary
const OD = '#C94A28';  // --primary-dark
const S = '#FBD9C7';   // --primary-soft
const P = '#FFF1E8';   // --peach-bg
const G = '#1E7B5E';   // --accent-green
const C = '#26282B';   // --charcoal
const SKIN = '#E9B48F';

export function Logo({ size = 52 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="Proof of Life logo">
      <path d="M32 3 7 12v18c0 16 10.5 27 25 31 14.5-4 25-15 25-31V12L32 3z" fill={O} />
      <path d="M32 9 13 16v14c0 12 8 21 19 24.5C43 51 51 42 51 30V16L32 9z" fill={OD} opacity="0.35" />
      <path d="M14 34h9l4-9 6 17 4-10 3 2h10" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function PhonePulse({ width = 220 }) {
  return (
    <svg width={width} viewBox="0 0 220 180" aria-hidden="true">
      <ellipse cx="110" cy="165" rx="90" ry="10" fill={S} />
      <rect x="70" y="10" width="80" height="150" rx="14" fill={C} />
      <rect x="77" y="22" width="66" height="122" rx="6" fill="#fff" />
      <circle cx="110" cy="62" r="24" fill={P} stroke={O} strokeWidth="3" strokeDasharray="6 5" />
      <circle cx="110" cy="58" r="9" fill={SKIN} />
      <path d="M96 76c3-8 25-8 28 0" fill={SKIN} />
      <path d="M82 112h14l5-12 8 22 6-14 4 4h14" fill="none" stroke={G} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="92" y="126" width="36" height="10" rx="5" fill={O} />
      <path d="M30 70c-10 8-10 26 0 34M42 78c-5 5-5 13 0 18" fill="none" stroke={O} strokeWidth="3" strokeLinecap="round" />
      <path d="M190 70c10 8 10 26 0 34M178 78c5 5 5 13 0 18" fill="none" stroke={O} strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function ElderAtHome({ width = 240 }) {
  return (
    <svg width={width} viewBox="0 0 240 180" aria-hidden="true">
      <rect x="0" y="150" width="240" height="30" fill={S} />
      <path d="M150 60 200 25l50 35v90h-100z" fill="#fff" stroke={OD} strokeWidth="3" transform="translate(-20 0)" />
      <rect x="160" y="100" width="24" height="50" fill={O} />
      <rect x="200" y="80" width="20" height="20" fill={P} stroke={OD} strokeWidth="2" />
      <rect x="40" y="96" width="78" height="10" rx="5" fill={C} />
      <rect x="46" y="106" width="6" height="44" fill={C} /><rect x="106" y="106" width="6" height="44" fill={C} />
      <circle cx="78" cy="48" r="16" fill={SKIN} />
      <path d="M64 42c2-12 26-12 28 0" fill="#E7E3DF" />
      <rect x="62" y="64" width="32" height="40" rx="12" fill={G} />
      <rect x="92" y="70" width="14" height="24" rx="3" fill={C} />
      <rect x="95" y="74" width="8" height="15" rx="1" fill="#fff" />
      <path d="M97 81h2l1-3 2 6 1-3" fill="none" stroke={O} strokeWidth="1.2" />
      <rect x="64" y="104" width="12" height="46" fill="#8C6A4F" /><rect x="80" y="104" width="12" height="46" fill="#8C6A4F" />
    </svg>
  );
}

export function OfficerDesk({ width = 220 }) {
  return (
    <svg width={width} viewBox="0 0 220 170" aria-hidden="true">
      <rect x="10" y="110" width="200" height="12" rx="4" fill={OD} />
      <rect x="24" y="122" width="10" height="40" fill={C} /><rect x="186" y="122" width="10" height="40" fill={C} />
      <rect x="120" y="58" width="74" height="50" rx="6" fill={C} />
      <rect x="126" y="64" width="62" height="36" rx="3" fill="#fff" />
      <rect x="132" y="70" width="22" height="22" fill={P} stroke={OD} strokeWidth="2" />
      <path d="M160 74h22M160 82h18M160 90h22" stroke={S} strokeWidth="4" />
      <circle cx="70" cy="40" r="17" fill={SKIN} />
      <path d="M53 36c2-16 32-16 34 0" fill={C} />
      <rect x="50" y="58" width="40" height="52" rx="14" fill={O} />
      <rect x="84" y="72" width="26" height="32" rx="3" fill="#fff" stroke={C} strokeWidth="2" />
      <path d="M90 82h14M90 88h14M90 94h9" stroke={G} strokeWidth="2.5" />
    </svg>
  );
}

export function LedgerChain({ width = 220 }) {
  const block = (x, label) => (
    <g transform={`translate(${x} 45)`}>
      <rect width="56" height="70" rx="8" fill="#fff" stroke={OD} strokeWidth="3" />
      <rect x="8" y="10" width="40" height="8" rx="4" fill={O} />
      <path d="M8 30h40M8 40h32M8 50h36" stroke={S} strokeWidth="5" strokeLinecap="round" />
      <text x="28" y="66" textAnchor="middle" fontSize="9" fontFamily="monospace" fill={C}>{label}</text>
    </g>
  );
  return (
    <svg width={width} viewBox="0 0 220 160" aria-hidden="true">
      <rect x="0" y="130" width="220" height="10" rx="5" fill={S} />
      {block(8, '#41')}{block(82, '#42')}{block(156, '#43')}
      <path d="M64 80h18M138 80h18" stroke={G} strokeWidth="5" strokeLinecap="round" />
      <circle cx="73" cy="80" r="5" fill={G} /><circle cx="147" cy="80" r="5" fill={G} />
    </svg>
  );
}

export function ShieldCheck({ width = 120 }) {
  return (
    <svg width={width} viewBox="0 0 120 120" aria-hidden="true">
      <circle cx="60" cy="60" r="56" fill={P} />
      <path d="M60 18 28 30v24c0 22 14 37 32 44 18-7 32-22 32-44V30L60 18z" fill={G} />
      <path d="M44 60l12 12 22-24" fill="none" stroke="#fff" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function HelpChat({ width = 200 }) {
  return (
    <svg width={width} viewBox="0 0 200 150" aria-hidden="true">
      <rect x="10" y="20" width="110" height="64" rx="16" fill={O} />
      <path d="M36 84l-8 22 26-22z" fill={O} />
      <path d="M32 44h66M32 60h46" stroke="#fff" strokeWidth="6" strokeLinecap="round" />
      <rect x="80" y="62" width="110" height="60" rx="16" fill="#fff" stroke={OD} strokeWidth="3" />
      <path d="M164 122l8 20-24-20z" fill="#fff" stroke={OD} strokeWidth="3" strokeLinejoin="round" />
      <text x="135" y="101" textAnchor="middle" fontSize="30" fontWeight="700" fontFamily="Poppins, sans-serif" fill={OD}>?</text>
    </svg>
  );
}

/** Generic line-art skyline for the hero (no real monuments). */
export function Skyline() {
  return (
    <svg className="hero-skyline" viewBox="0 0 1200 90" preserveAspectRatio="none" aria-hidden="true">
      <path fill="none" stroke="#fff" strokeWidth="2"
        d="M0 90V60h40V40h30v20h30V30h40v30h30V50h50v40M270 90V45h26V25h30v20h26v45M370 90V55h60V35h20v20h40v35M510 90V40h36v-12h24v12h36v50M630 90V58h50V38h30v20h50v32M780 90V30h40v60M840 90V50h60V35h26v15h40v40M990 90V45h30V28h28v17h32v45M1100 90V55h40V40h20v15h40v35" />
    </svg>
  );
}

export function HeroWave() {
  return (
    <svg className="hero-wave" viewBox="0 0 90 400" preserveAspectRatio="none" aria-hidden="true">
      <path d="M45 0c30 40-30 80 0 120s-30 80 0 120 30 80 0 120 30 40 0 40h45V0z" fill="#fff" />
    </svg>
  );
}

/** Illustrated phone screens for the showcase (swap for real team screenshots). */
export function AppScreen({ variant = 'scan' }) {
  const screens = {
    scan: (
      <>
        <rect x="18" y="40" width="84" height="84" rx="6" fill="#fff" />
        {[0, 1, 2, 3, 4, 5].map((i) => <rect key={i} x={24 + (i % 3) * 26} y={46 + Math.floor(i / 3) * 40} width="20" height="20" fill={C} />)}
        <text x="60" y="150" textAnchor="middle" fontSize="10" fill="#fff" fontFamily="sans-serif">Scan QR code</text>
      </>
    ),
    measure: (
      <>
        <circle cx="60" cy="80" r="38" fill="none" stroke={O} strokeWidth="4" />
        <circle cx="60" cy="76" r="14" fill={SKIN} />
        <path d="M40 104c6-12 34-12 40 0" fill={SKIN} />
        <path d="M18 146h18l5-10 7 18 6-12 4 4h44" fill="none" stroke="#4ADE80" strokeWidth="3" strokeLinecap="round" />
        <text x="60" y="30" textAnchor="middle" fontSize="10" fill="#fff" fontFamily="sans-serif">Hold still · 74 BPM</text>
      </>
    ),
    result: (
      <>
        <circle cx="60" cy="78" r="30" fill={G} />
        <path d="M46 78l10 10 18-20" fill="none" stroke="#fff" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
        <text x="60" y="130" textAnchor="middle" fontSize="11" fill="#fff" fontWeight="700" fontFamily="sans-serif">Certificate issued</text>
      </>
    ),
  };
  return (
    <svg viewBox="0 0 120 190" width="150" role="img" aria-label={`App screen illustration: ${variant}`}>
      <rect x="4" y="4" width="112" height="182" rx="16" fill={C} />
      <rect x="10" y="16" width="100" height="158" rx="8" fill={variant === 'result' ? '#12352B' : '#16181B'} />
      {screens[variant]}
    </svg>
  );
}
