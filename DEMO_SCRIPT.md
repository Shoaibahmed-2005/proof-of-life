# DEMO_SCRIPT.md: Presenting Jeevan Suraksha (SIH26125)

About **10 minutes** plus questions. The laptop screen (portal) faces the judges; the phone is in the pensioner's hands. Every result appears **on the phone and on the laptop at the same moment**.

**Cast**
- **Presenter:** drives the laptop and speaks.
- **A:** the pensioner.
- **B:** the impostor.
- **Props:** a printed photo of A's face (A4, colour) and a short video of A looking at the camera (recorded on a second phone or laptop, about 30 s, A sitting still in good light).

**Use one phone (A's Pixel 7) for every scenario.** The pension is bound to the phone used at registration. If B uses a different phone, the result is "not the registered device" instead of the face mismatch we want to show.

---

## Before the judges arrive (30 minutes before)

| # | Step | Check |
|---|---|---|
| 1 | Laptop and phone on the **same Wi-Fi** (or the phone's hotspot; see ANDROID_BUILD.md, "Wi-Fi setup"). | |
| 2 | `cd backend` → `python scripts/reset_demo.py --yes --seed` (clean data; the old data goes to `data/backups/`). | "Demo data seeded." |
| 3 | `python run.py` (keep this window open). | The banner says `QR codes use  http://<LAN-IP>:8000`, with no "!" warnings about adapters. |
| 4 | Repo root: `npm run dev`. Open http://localhost:5173 in the browser, full screen, zoom 110–125 %. | Home page loads. |
| 5 | On the phone, open `http://<LAN-IP>:8000/api/v1/health` in Chrome. | JSON with `"status"`. If not: firewall rules (ANDROID_BUILD.md). |
| 6 | **Practice scan** once with A (portal → Practice Scan). | "Practice scan passed". Tells you the light is good. |
| 7 | Light: A faces a window or lamp; nothing bright behind A. Phone brightness up, battery > 50 %, Do Not Disturb on. | |
| 8 | Officer tab: log in (`officer` / `officer123`) in a **second browser tab**, and keep the pensioner tab in the first. | |
| 9 | Fallback ready: a terminal in `backend/` with the venv active (for `simulate_phone.py`, see "If something goes wrong"). | |

---

## The script

### 0. Opening (30 s)
> "Every year, millions of pensioners must prove they are alive, or their pension stops. For an 80-year-old veteran that means a trip to an office. Remote options can be fooled with a photo. Jeevan Suraksha lets them do it at home with their phone, and checks three things: a **real pulse**, a **random live action**, and a **1:1 face match**, all signed inside the phone's security chip."

### 1. S1: Register A (2 min)
1. Officer tab → **Register Pensioner**. Enter A's dummy details (name, PPO e.g. `PPO-DEMO-2001`, service number, bank last 4 digits, pension amount) → **Save and continue** → **Show QR code**.
   > "The officer checks the ID in person, like HR registering attendance. We never collect Aadhaar numbers."
2. A opens the app → **Scan QR code** → points it at the laptop → **Consent** screen → "I agree, start the scan".
   > "Plain-language consent. No photos leave the phone, only a code of numbers."
3. A holds still. The phone shows the orange guide circle, live pulse and waveform. The portal shows *Measuring pulse*.
4. The challenge appears on the phone and the portal at the same time (for example "Blink twice now"). A does it; the circle turns **green**.
   > "The backend chose this action when it made the QR code. A recording can't know it in advance."
5. Phone: **Face registered**. Portal: **Face captured** → click **Approve**. A shows as **Active**.

### 2. S2: A submits a life certificate (1.5 min)
1. Pensioner tab → **Submit Life Certificate** → A's pension ID → tick consent → **Show QR code**.
2. A scans and does the scan and challenge.
3. Phone: **Life certificate issued**. Portal: stepper completes, **certificate card** with face-match score, ledger hash and DID; "Life certificate issued for 2026" toast.
   > "Signed by the Titan M2 chip, matched only against A's own template, and recorded on a tamper-evident ledger."

### 3. S3: B pretends to be A (1 min)
1. Submit Life Certificate with **A's** pension ID → **B** scans with **A's phone**.
2. Phone and portal: **Rejected: face does not match**.
   > "Right phone, right pension ID, live person, but the wrong face."

### 4. S4: Photo of A (1 min)
1. New QR for A → hold the **printed photo** in front of the phone camera, steady.
2. After about 30 s: **Rejected: no pulse detected**.
   > "A photo has the right face but no heartbeat. The pulse comes from tiny colour changes in real skin."
   (While waiting, point to the live SNR on the phone staying low.)

### 5. S5: Video of A (1 min)
1. New QR for A → play the **video of A** on the second screen in front of the phone.
2. Either **Rejected: challenge failed** (the video can't blink or turn on request) or **Rejected: no pulse detected** (a screen often doesn't carry a clear pulse).
   > "Even if a video carried a pulse, it can't follow a random instruction it has never seen."

### 6. Finale: frozen, then restored (1 min)
1. After S5 the portal shows A's pension as **Frozen** (three failed attempts).
   > "Three attacks, and the pension is frozen. It is frozen, never cancelled, until an officer looks at it."
2. Officer tab → **Review Queue → Frozen pensions** → **Restore…** → type a reason → **Restore pension** → A is **Active** again.

### 7. Trust and transparency (1 min)
1. **Audit Ledger** → **Verify chain integrity** → green.
   > "Every registration, certificate, freeze and restore is chained by hashes. Changing any old entry breaks the chain."
2. **Treasury**: pensions released vs frozen, and rejections by reason.

### 8. Close (30 s)
> "Liveness, a random challenge and a 1:1 face match, signed in hardware, recorded on a verifiable ledger, and usable by an elderly pensioner at home. Next steps: calibrating the thresholds on more people, screen-replay detection, DigiLocker for identity, and anchoring the ledger on a public chain."

---

## If something goes wrong

| Problem | What to do |
|---|---|
| Phone says **Can't reach the laptop** | Check the Wi-Fi (step 1). Over USB: `adb reverse tcp:8000 tcp:8000`, then scan again (the app also tries `localhost`). |
| **No pulse** for A in S1/S2 | Better light on the face (a window or lamp in front), phone at eye level, hold still; scan a new QR code. Turn on **Diagnostics** to see what it's waiting for (TESTING_CHECKLIST.md, "How to read the diagnostics"). |
| **Challenge failed** for A | Do the action clearly (turn the head about 30°, or two normal blinks) as soon as the prompt appears. |
| **Sent for officer review** in S2 | That's the borderline band working. Approve it in **Review Queue** and explain the three bands. |
| The phone app fails completely | Use the simulator with the same portal: click **Show QR data (testing)** under the QR code, copy the JSON, then in `backend/`: `python scripts/simulate_phone.py --qr '<json>' --person A` (add `--person B`, `--no-pulse` or `--challenge-fail` for S3–S5). Say that it's a software-key simulator; the portal shows its key as SOFTWARE. |
| Something in the data looks wrong | Between runs: stop the backend, `python scripts/reset_demo.py --yes --seed`, start it again. |

To rehearse the whole flow without people or a phone: `python scripts/demo_check.py --slow` in `backend/`, while watching the portal.

---

## Likely questions

| Question | Answer |
|---|---|
| What stops a deepfake? | A pre-recorded one fails the random challenge. A real-time deepfake that follows the prompt **and** shows a pulse is a harder attack; screen-replay detection and device attestation are our next layers. We're honest that it's out of scope for this prototype. |
| Does it work for darker skin or older faces? | rPPG is harder in low light and on darker skin, so poor conditions go to "no pulse" or officer review, never to a false pass. The thresholds are tuned from measured scans, not guessed. |
| What if the pensioner changes phone? | The officer re-registers the new phone (the same in-person step as registration). |
| What is stored? | No photos or videos. An encrypted 192-number face template, the device's public key, and the certificate records. The ledger holds hashes only. |
| Why not Aadhaar face authentication? | We deliberately avoid collecting Aadhaar numbers. DigiLocker or the Aadhaar Secure QR code can be added for identity at registration. |
| How is this "blockchain"? | A hash-chained, append-only ledger with DIDs and signed credentials, behind a `LedgerBackend` interface ready to anchor on a public chain. |
| What if someone keeps failing on purpose to freeze a pension? | They'd need the pension ID **and** the registered phone. Only pulse, challenge and face failures count, and an officer restores the pension from the review queue. |
