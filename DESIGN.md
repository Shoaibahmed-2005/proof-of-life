# DESIGN.md: Portal Design Guide

This guide defines the look of the **whole web portal**: every page, not just the landing page. The Android app follows the same colours and type in a simpler form.

**Reference image:** `docs/design-reference.jpeg` (a government embassy website). Use it for **style only**: colours, layout rhythm and component types. Do not copy it.

**Never copy from the reference:**
- The State Emblem of India, G20, Azadi Ka Amrit Mahotsav, MEA, india.gov.in or any other official or partner logos.
- Its text, photos, monument images or illustrations.
- The "Embassy of India" name or any wording that makes the portal look like a real government site.

Use a fictional portal name and our own simple logo mark (e.g. "Jeevan Suraksha – Pension Life Certificate Portal"), our own screenshots, and openly licensed illustrations (see section 5).

---

## 1. Visual identity

The feel is **warm, official, trustworthy and friendly for elderly users**: saffron/coral warmth on clean white, with a dark charcoal frame at the top and bottom.

### Colours (define as CSS variables and use them everywhere)

| Token | Hex | Use |
|---|---|---|
| `--primary` | `#E8603C` | Primary buttons, active nav, key highlights |
| `--primary-dark` | `#C94A28` | Button hover, **orange text on white** (for contrast) |
| `--primary-soft` | `#FBD9C7` | Hero gradient end, soft banners |
| `--peach-bg` | `#FFF1E8` | Section backgrounds, banner strips, table headers |
| `--accent-green` | `#1E7B5E` | Success states, "Active", "Certificate issued" |
| `--warning` | `#B7791F` on `#FFF4DE` | "Under review" |
| `--danger` | `#B42318` on `#FDECEC` | "Rejected", "Frozen" |
| `--text` | `#1F2933` | Body text |
| `--text-muted` | `#5B6573` | Secondary text |
| `--surface` | `#FFFFFF` | Page and cards |
| `--border` | `#EADFD7` | Card and table borders |
| `--charcoal` | `#26282B` | Top utility bar and footer |
| `--charcoal-2` | `#1B1C1E` | Bottom copyright bar |

The hero uses a gradient from `--primary` to `--primary-soft`. Check that all text meets **WCAG AA contrast**. White text on `--primary` passes only at large or bold sizes, so button labels must be bold, 16px or larger.

### Typography
- **Headings:** Poppins or Montserrat (Google Fonts), 600–700 weight. Section titles are centred, uppercase and bold, like "ABOUT EMBASSY" in the reference.
- **Body:** Inter or Noto Sans, 16px minimum, **18px on pensioner-facing pages** (elderly users).
- Use **Noto Sans Devanagari** for Hindi labels.

### Shape and depth
- Cards: 12px radius, 1px `--border`, soft shadow (`0 6px 20px rgba(0,0,0,0.06)`).
- Buttons: pill shape (fully rounded), 48px minimum height.
- Round icon buttons for carousel arrows, as in the reference.
- Generous white space. Content max width 1200px, centred.

---

## 2. Page shell (on every page)

1. **Top utility bar** (`--charcoal`, thin): helpline email and phone on the left; "Accessibility" and text-size controls (A-, A, A+) on the right.
2. **Header** (white): our logo mark and portal name on the left; a **language selector pill** (English / हिन्दी) and a rounded search box with an orange search button on the right.
3. **Main nav** (white, below the header): Home, Submit Life Certificate, Check Status, Officer Login, How It Works, Help & FAQs, Contact. Active item underlined in `--primary`.
4. **Page banner** (inner pages only): short peach band with the page title and breadcrumb.
5. **Footer** (`--charcoal`): portal name and logo, office hours, and link columns (Policies, Help, Accessibility, Contact).
6. **Copyright bar** (`--charcoal-2`): one centred line.

---

## 3. Component library

| Component | Description | Used on |
|---|---|---|
| **Hero carousel** | Orange gradient panel. Left: large bold headline + subline + white pill button. Right: rounded image card with a white border. Round prev/next buttons below. A soft torn-paper or wave edge between the two halves. | Home |
| **Highlight strip** | Wide peach band with a flat illustration on the left and a headline + key stats on the right. | Home, Treasury |
| **Sidebar + info card** | Left: "General Information" link list with dividers. Right: white card with a title in `--primary-dark`, short text, a "Know More ›" link and an illustration. | Home (About), How It Works |
| **Feature cards (4-up)** | White cards with an illustration on top, bold title, 2-line muted description and a "Know More ›" link. Lift slightly on hover. | Home services, How It Works |
| **Gradient showcase banner** | Rounded peach gradient block with a title on the left and an image carousel with thumbnails on the right. | Home (demo screenshots) |
| **Feed columns (3-up)** | Titled columns, each with a scrollable card list. | Home: Announcements · Recent Certificates · Ledger Activity |
| **Useful links** | Bulleted link list next to an illustration. | Home, Help |
| **Circular icon carousel** | Round white badges with icons and arrows either side. | Home: "Pulse Check · Face Match · Hardware Signature · Tamper-proof Ledger · Officer Review · Privacy" |
| **Status stepper** | Horizontal steps with numbered circles: grey (pending), orange (active, pulsing), green (done), red (failed), with a text label under each. | Submit Life Certificate, Registration |
| **QR panel** | Large white card, QR code centred, a countdown timer ("expires in 4:32"), plain-language instructions and a mini phone illustration. | Submit Life Certificate, Registration |
| **Status badge** | Pill badge: Active (green), Under Review (amber), Rejected / Frozen (red), Pending (grey). | Everywhere statuses appear |
| **Stat tiles** | White cards with a big number, a label and a small trend. | Treasury dashboard |
| **Data table** | Peach header row, zebra rows, status badges, a right-aligned action button. | Records, Review Queue, Ledger |
| **Forms** | Labels above fields, 48px inputs, orange focus ring, inline validation messages, one primary orange button. | Registration, Login |
| **Certificate card** | Certificate-style card: pensioner name, year, issue date, match score, ledger hash (monospace, with a copy button), green "Verified" seal. | Certificate result |
| **Toast / live alert** | Slides in when a WebSocket event arrives ("Pulse detected", "Certificate issued"). | All live pages |

---

## 4. Pages and which components they use

1. **Home:** hero carousel ("Submit your life certificate from home, in under a minute") → highlight strip (key numbers) → about section (sidebar + info card) → feature cards (Submit Certificate, Check Status, Officer Registration, Help & Support) → gradient showcase banner with real app screenshots → feed columns → circular icon carousel of how the security works → useful links → footer.
2. **Submit Life Certificate:** page banner → pension ID form → QR panel → status stepper driven live by WebSocket (Waiting for scan → Measuring pulse → Challenge → Face match → Result) → certificate card or a clear reason for rejection or review.
3. **Check Status:** pension ID lookup → pensioner summary card with status badge → certificate history table.
4. **Officer – Register Pensioner:** form → QR panel → live stepper → Approve button.
5. **Officer – Review Queue:** data table of borderline cases → detail drawer (match score, BPM, SNR, challenge result) → Approve / Reject with a reason.
6. **Pensioner Records:** searchable data table → detail page.
7. **Treasury Dashboard:** stat tiles (Active, Frozen, certificates this year, rejected attempts) → simple charts (released vs frozen; rejection reasons) → table.
8. **Audit Ledger:** data table of hash-chained entries → "Verify chain integrity" button → green or red result banner.
9. **How It Works / Help & FAQs:** sidebar + info cards, feature cards, FAQ accordion.

---

## 5. Imagery rules

- **Illustrations:** flat, friendly vector illustrations in the same warm palette. Use openly licensed sets (e.g. unDraw, recoloured to `--primary`) or simple hand-made SVGs. **No AI-generated images.** The idea PPT will be checked for AI content and the portal will appear in screenshots.
- **Photos:** only real ones taken by the team (the app on the phone, the laptop + phone demo setup, team at work).
- **Motifs:** a subtle, generic line-art pattern or skyline is fine as hero decoration. No official emblems, flags used as logos, or copied monument artwork.

---

## 6. Accessibility and elderly-friendly rules

- Body text at least 16px (18px on pensioner pages); a working text-size control in the top bar.
- WCAG AA contrast everywhere; never rely on colour alone (badges always include text).
- Every page is keyboard navigable with a visible focus ring.
- One clear primary action per screen; plain-language labels ("Submit Life Certificate", not "Initiate verification session").
- Status changes are announced (ARIA live region) as well as shown.
- Responsive down to tablet and phone width; no horizontal scrolling.

---

## 7. Android app (same identity, simpler)

- Same colour tokens and fonts; white screens with orange primary buttons and green success states.
- Four screens only: **Scan QR → Consent → Face Scan → Result**.
- Face scan: dark camera view, a large face-guide circle (orange while measuring, green when verified), big prompt text ("Hold still", "Blink twice now"), live BPM and a smooth waveform, and a progress ring.
- Result: large icon + one-line outcome + reason; the laptop portal updates at the same moment.

---

## 8. Build notes for the agent

- Put all colours, radii, shadows and fonts in one theme file (CSS variables or a Tailwind theme). Build the shared components once and reuse them on every page; don't restyle per page.
- Build the page shell (section 2) first, then components (section 3), then pages (section 4).
- After building, compare each page against the reference image **for style consistency only**, and against this guide for content.
