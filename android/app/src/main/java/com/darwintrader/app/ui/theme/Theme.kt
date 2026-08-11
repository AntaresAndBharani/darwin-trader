package com.darwintrader.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkColorScheme = darkColorScheme(
    primary = Color(0xFF00E676),      // Bright Trading Green
    secondary = Color(0xFF2979FF),    // Professional Blue
    tertiary = Color(0xFFFF1744),     // Warning / Stop Loss Red
    background = Color(0xFF0F172A),   // Deep Dark Navy Background
    surface = Color(0xFF1E293B),      // Slate Card Surface
    onPrimary = Color.Black,
    onBackground = Color.White,
    onSurface = Color.White
)

@Composable
fun DarwinTraderTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = DarkColorScheme,
        content = content
    )
}
