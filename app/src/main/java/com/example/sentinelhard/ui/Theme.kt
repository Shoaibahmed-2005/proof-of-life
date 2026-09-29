package com.example.sentinelhard.ui

import androidx.compose.ui.graphics.Color

/** DESIGN.md §1 colour tokens (same as the portal's src/theme/tokens.css). */
object Jst {
    val Primary = Color(0xFFE8603C)
    val PrimaryDark = Color(0xFFC94A28)      // orange text on white
    val PrimarySoft = Color(0xFFFBD9C7)
    val PeachBg = Color(0xFFFFF1E8)
    val Green = Color(0xFF1E7B5E)
    val GreenBg = Color(0xFFE3F4EC)
    val Warning = Color(0xFFB7791F)
    val WarningBg = Color(0xFFFFF4DE)
    val Danger = Color(0xFFB42318)
    val DangerBg = Color(0xFFFDECEC)
    val Text = Color(0xFF1F2933)
    val TextMuted = Color(0xFF5B6573)
    val Surface = Color(0xFFFFFFFF)
    val Border = Color(0xFFEADFD7)
    val Charcoal = Color(0xFF26282B)

    /** Green for the guide circle over the dark camera view (the token green is too dark there). */
    val GreenOnDark = Color(0xFF3DBE8B)
    val Scrim = Color(0x8C000000)
}
