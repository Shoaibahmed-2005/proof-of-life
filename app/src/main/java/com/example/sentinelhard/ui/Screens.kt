package com.example.sentinelhard.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/*
 * The app's screens (build-prompt §4.6, DESIGN.md §7): Scan QR → Consent →
 * Face Scan → Result. White screens, orange pill buttons, green success; the
 * face scan is a dark camera view with a guide circle and a progress ring.
 * All composables here are stateless: MainActivity passes the values in.
 */

enum class ResultKind { SUCCESS, REVIEW, FAILURE }

// ── Shared pieces ───────────────────────────────────────────────────────

@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
        shape = RoundedCornerShape(50),
        colors = ButtonDefaults.buttonColors(containerColor = Jst.Primary, contentColor = Color.White),
        modifier = modifier.fillMaxWidth().heightIn(min = 60.dp),
    ) {
        Text(text, fontSize = 20.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
    }
}

@Composable
fun SecondaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    OutlinedButton(
        onClick = onClick,
        shape = RoundedCornerShape(50),
        border = BorderStroke(2.dp, Jst.PrimaryDark),
        colors = ButtonDefaults.outlinedButtonColors(containerColor = Color.White, contentColor = Jst.PrimaryDark),
        modifier = modifier.fillMaxWidth().heightIn(min = 56.dp),
    ) {
        Text(text, fontSize = 18.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
    }
}

/** Fictional brand mark: a pulse line in a soft circle (no official emblems). */
@Composable
private fun BrandMark(sizeDp: Int = 88) {
    Canvas(Modifier.size(sizeDp.dp)) {
        drawCircle(Jst.PrimarySoft)
        val w = size.width
        val h = size.height
        val path = Path().apply {
            moveTo(w * 0.18f, h * 0.55f)
            lineTo(w * 0.38f, h * 0.55f)
            lineTo(w * 0.46f, h * 0.30f)
            lineTo(w * 0.56f, h * 0.75f)
            lineTo(w * 0.63f, h * 0.50f)
            lineTo(w * 0.82f, h * 0.50f)
        }
        drawPath(path, Jst.PrimaryDark, style = Stroke(width = w * 0.06f, cap = StrokeCap.Round))
    }
}

@Composable
private fun WhitePage(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize().background(Jst.Surface)) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp, vertical = 32.dp),
        ) { content() }
    }
}

// ── 1. Scan QR ──────────────────────────────────────────────────────────

/** Start of screen 1, before the camera opens. */
@Composable
fun WelcomeScreen(onScan: () -> Unit) {
    WhitePage {
        Spacer(Modifier.height(24.dp))
        BrandMark()
        Spacer(Modifier.height(20.dp))
        Text("Jeevan Suraksha", color = Jst.Text, fontSize = 32.sp, fontWeight = FontWeight.Bold)
        Text("Life certificate from home", color = Jst.TextMuted, fontSize = 20.sp)
        Spacer(Modifier.height(28.dp))
        Column(
            Modifier.fillMaxWidth().background(Jst.PeachBg, RoundedCornerShape(12.dp)).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Step(1, "Open the portal on the laptop and choose what to do.")
            Step(2, "Tap the button below and point this phone at the QR code.")
            Step(3, "Follow the big prompts on this screen.")
        }
        Spacer(Modifier.height(32.dp))
        PrimaryButton("Scan QR code", onScan)
    }
}

@Composable
private fun Step(n: Int, text: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(36.dp).background(Jst.Primary, CircleShape), contentAlignment = Alignment.Center) {
            Text("$n", color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.width(14.dp))
        Text(text, color = Jst.Text, fontSize = 19.sp)
    }
}

/** Drawn over the back-camera preview while looking for the QR code. */
@Composable
fun QrScannerOverlay(onCancel: () -> Unit) {
    Box(Modifier.fillMaxSize()) {
        Canvas(Modifier.fillMaxSize()) {
            val side = size.minDimension * 0.66f
            val left = (size.width - side) / 2f
            val top = (size.height - side) / 2f
            val hole = Path().apply {
                fillType = PathFillType.EvenOdd
                addRect(Rect(Offset.Zero, size))
                addRect(Rect(Offset(left, top), Size(side, side)))
            }
            drawPath(hole, Jst.Scrim)
            val arm = side * 0.18f
            val stroke = Stroke(width = 10f, cap = StrokeCap.Round)
            listOf(
                Offset(left, top) to Offset(1f, 1f), Offset(left + side, top) to Offset(-1f, 1f),
                Offset(left, top + side) to Offset(1f, -1f), Offset(left + side, top + side) to Offset(-1f, -1f),
            ).forEach { (c, d) ->
                val p = Path().apply {
                    moveTo(c.x + d.x * arm, c.y)
                    lineTo(c.x, c.y)
                    lineTo(c.x, c.y + d.y * arm)
                }
                drawPath(p, Jst.Primary, style = stroke)
            }
        }
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.align(Alignment.TopCenter).fillMaxWidth().background(Jst.Surface).padding(20.dp),
        ) {
            Text("Scan the QR code", color = Jst.Text, fontSize = 26.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            Text("Point the phone at the code on the laptop screen.", color = Jst.TextMuted, fontSize = 18.sp,
                textAlign = TextAlign.Center)
        }
        Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().background(Jst.Surface).padding(20.dp)) {
            SecondaryButton("Cancel", onCancel)
        }
    }
}

@Composable
fun BusyScreen(message: String) {
    Box(Modifier.fillMaxSize().background(Jst.Surface), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(32.dp)) {
            CircularProgressIndicator(color = Jst.Primary, strokeWidth = 6.dp, modifier = Modifier.size(72.dp))
            Spacer(Modifier.height(24.dp))
            Text(message, color = Jst.Text, fontSize = 22.sp, textAlign = TextAlign.Center,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
        }
    }
}

// ── 2. Consent ──────────────────────────────────────────────────────────

@Composable
fun ConsentScreen(title: String, points: List<String>, onAgree: () -> Unit, onCancel: () -> Unit) {
    WhitePage {
        Text(title, color = Jst.Text, fontSize = 28.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
        Spacer(Modifier.height(6.dp))
        Text("Please read before we start", color = Jst.TextMuted, fontSize = 18.sp)
        Spacer(Modifier.height(24.dp))
        Column(verticalArrangement = Arrangement.spacedBy(16.dp), modifier = Modifier.fillMaxWidth()) {
            points.forEach { p ->
                Row {
                    Box(Modifier.padding(top = 9.dp).size(10.dp).background(Jst.Primary, CircleShape))
                    Spacer(Modifier.width(14.dp))
                    Text(p, color = Jst.Text, fontSize = 19.sp)
                }
            }
        }
        Spacer(Modifier.height(24.dp))
        Text(
            "Only you should be in front of the camera. Sit in good, even light and hold the phone at eye level.",
            color = Jst.Text, fontSize = 18.sp,
            modifier = Modifier.fillMaxWidth().background(Jst.PeachBg, RoundedCornerShape(12.dp)).padding(16.dp),
        )
        Spacer(Modifier.height(28.dp))
        PrimaryButton("I agree, start the scan", onAgree)
        Spacer(Modifier.height(12.dp))
        SecondaryButton("Cancel", onCancel)
    }
}

// ── 3. Face scan ────────────────────────────────────────────────────────

/**
 * Drawn over the front-camera preview: darkened surroundings with a face-guide
 * circle (orange while measuring, green once verified), a progress ring, a big
 * prompt at the top, and live pulse + waveform in a white card at the bottom.
 */
@Composable
fun FaceScanHud(
    prompt: String,
    detail: String?,
    progress: Float,
    verified: Boolean,
    bpm: String,
    snr: String,
    waveform: DoubleArray,
    diagnosticsOn: Boolean,
    onToggleDiagnostics: () -> Unit,
) {
    val ringColor = if (verified) Jst.GreenOnDark else Jst.Primary
    Box(Modifier.fillMaxSize()) {
        Canvas(Modifier.fillMaxSize()) {
            val center = Offset(size.width / 2f, size.height * GUIDE_CENTER_Y)
            val radius = minOf(size.width * 0.40f, size.height * 0.26f)
            val hole = Path().apply {
                fillType = PathFillType.EvenOdd
                addRect(Rect(Offset.Zero, size))
                addOval(Rect(center, radius))
            }
            drawPath(hole, Jst.Scrim)
            drawCircle(ringColor.copy(alpha = 0.35f), radius = radius, center = center, style = Stroke(width = 14f))
            val ring = radius + 18f
            drawArc(
                color = ringColor,
                startAngle = -90f,
                sweepAngle = 360f * progress.coerceIn(0f, 1f),
                useCenter = false,
                topLeft = Offset(center.x - ring, center.y - ring),
                size = Size(ring * 2f, ring * 2f),
                style = Stroke(width = 14f, cap = StrokeCap.Round),
            )
        }
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.align(Alignment.TopCenter).fillMaxWidth().padding(top = 36.dp, start = 20.dp, end = 20.dp),
        ) {
            Text(
                prompt, color = if (verified) Jst.GreenOnDark else Color.White, fontSize = 32.sp,
                fontWeight = FontWeight.Bold, textAlign = TextAlign.Center, lineHeight = 38.sp,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
            if (detail != null) {
                Spacer(Modifier.height(6.dp))
                Text(detail, color = Color.White.copy(alpha = 0.9f), fontSize = 20.sp, textAlign = TextAlign.Center)
            }
        }
        Column(
            Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                .background(Jst.Surface, RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp))
                .padding(horizontal = 20.dp, vertical = 14.dp),
        ) {
            Row(verticalAlignment = Alignment.Bottom, modifier = Modifier.fillMaxWidth()) {
                Column {
                    Text("Pulse", color = Jst.TextMuted, fontSize = 15.sp)
                    Row(verticalAlignment = Alignment.Bottom) {
                        Text(bpm, color = Jst.Text, fontSize = 40.sp, fontWeight = FontWeight.Bold)
                        Text(" BPM", color = Jst.TextMuted, fontSize = 16.sp, modifier = Modifier.padding(bottom = 7.dp))
                    }
                }
                Spacer(Modifier.weight(1f))
                Column(horizontalAlignment = Alignment.End) {
                    Text("Signal", color = Jst.TextMuted, fontSize = 15.sp)
                    Text("$snr dB", color = Jst.Text, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                }
            }
            Waveform(waveform, Modifier.fillMaxWidth().height(72.dp))
            Text(
                if (diagnosticsOn) "Hide diagnostics" else "Diagnostics",
                color = Jst.TextMuted, fontSize = 14.sp,
                modifier = Modifier.align(Alignment.End).clickable { onToggleDiagnostics() }.padding(6.dp),
            )
        }
    }
}

/** Vertical position of the guide circle's centre, as a fraction of the screen height. */
const val GUIDE_CENTER_Y = 0.42f

@Composable
private fun Waveform(signal: DoubleArray, modifier: Modifier) {
    Canvas(modifier) {
        if (signal.size < 2) return@Canvas
        val path = Path()
        val xStep = size.width / (signal.size - 1)
        val mid = size.height / 2f
        signal.forEachIndexed { i, v ->
            val x = i * xStep
            val y = mid - (v.toFloat() * size.height * 0.42f)  // signal is scaled to [-1, 1]
            if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        drawPath(path, Jst.Primary, style = Stroke(width = 5f, cap = StrokeCap.Round))
    }
}

// ── 4. Result ───────────────────────────────────────────────────────────

@Composable
fun ResultScreen(kind: ResultKind, title: String, message: String?, onDone: () -> Unit) {
    val (fg, bg, glyph) = when (kind) {
        ResultKind.SUCCESS -> Triple(Jst.Green, Jst.GreenBg, "✓")
        ResultKind.REVIEW -> Triple(Jst.Warning, Jst.WarningBg, "…")
        ResultKind.FAILURE -> Triple(Jst.Danger, Jst.DangerBg, "✕")
    }
    WhitePage {
        Spacer(Modifier.height(40.dp))
        Box(Modifier.size(128.dp).background(bg, CircleShape), contentAlignment = Alignment.Center) {
            Text(glyph, color = fg, fontSize = 64.sp, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(24.dp))
        Text(
            title, color = fg, fontSize = 30.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center,
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
        )
        if (message != null) {
            Spacer(Modifier.height(14.dp))
            Text(message, color = Jst.Text, fontSize = 20.sp, textAlign = TextAlign.Center)
        }
        Spacer(Modifier.height(40.dp))
        PrimaryButton("Done", onDone)
    }
}
