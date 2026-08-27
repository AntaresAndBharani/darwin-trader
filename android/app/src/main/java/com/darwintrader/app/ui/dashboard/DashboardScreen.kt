package com.darwintrader.app.ui.dashboard

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.darwintrader.app.data.model.AccountInfo
import com.darwintrader.app.data.model.AccountStatusResponse
import com.darwintrader.app.data.model.Position
import com.darwintrader.app.data.model.getConnectionBadgeText

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    accountInfo: AccountInfo,
    positions: List<Position>,
    strategyStatus: String,
    accountStatus: AccountStatusResponse? = null,
    onStartStrategy: () -> Unit,
    onPauseStrategy: () -> Unit,
    onKillSwitch: () -> Unit
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Darwin Trader", fontWeight = FontWeight.Bold) },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                    titleContentColor = MaterialTheme.colorScheme.onSurface
                )
            )
        },
        containerColor = MaterialTheme.colorScheme.background
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
        ) {
            // Darwinex Account Summary Card
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    val connBadgeText = accountStatus.getConnectionBadgeText()
                    val connBadgeBg = when (connBadgeText) {
                        "Connected (Live)" -> Color(0xFF00E676)
                        "Connected (Demo)" -> Color(0xFF29B6F6)
                        "Simulation" -> Color(0xFFFFB300)
                        else -> Color(0xFF757575)
                    }
                    val connBadgeTextColor = when (connBadgeText) {
                        "Disconnected" -> Color.White
                        else -> Color.Black
                    }

                    val effectiveLogin = accountStatus?.accountInfo?.login?.takeIf { it != 0L }
                        ?: accountInfo.login.takeIf { it != 0L }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            if (effectiveLogin != null) {
                                Text(
                                    "Account #$effectiveLogin",
                                    fontSize = 12.sp,
                                    color = Color.LightGray,
                                    fontWeight = FontWeight.Medium
                                )
                            }
                            Text("Account Equity", fontSize = 12.sp, color = Color.Gray)
                            Text(
                                "$${String.format("%.2f", accountInfo.equity)}",
                                fontSize = 28.sp,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary
                            )
                        }

                        Column(
                            horizontalAlignment = Alignment.End,
                            verticalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                // Connection Status Badge
                                Box(
                                    modifier = Modifier
                                        .background(
                                            connBadgeBg,
                                            shape = RoundedCornerShape(8.dp)
                                        )
                                        .padding(horizontal = 10.dp, vertical = 6.dp)
                                ) {
                                    Text(
                                        connBadgeText,
                                        color = connBadgeTextColor,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 12.sp
                                    )
                                }

                                // Strategy Status Badge
                                Box(
                                    modifier = Modifier
                                        .background(
                                            if (strategyStatus == "RUNNING") Color(0xFF00E676) else Color(0xFFFFB300),
                                            shape = RoundedCornerShape(8.dp)
                                        )
                                        .padding(horizontal = 10.dp, vertical = 6.dp)
                                ) {
                                    Text(
                                        strategyStatus,
                                        color = Color.Black,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 12.sp
                                    )
                                }
                            }
                            if (effectiveLogin != null) {
                                Text(
                                    "ID: $effectiveLogin",
                                    fontSize = 11.sp,
                                    color = Color.Gray,
                                    fontWeight = FontWeight.Normal
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))
                    HorizontalDivider(color = Color.DarkGray)
                    Spacer(modifier = Modifier.height(12.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column {
                            Text("Balance", fontSize = 12.sp, color = Color.Gray)
                            Text("$${String.format("%.2f", accountInfo.balance)}", fontWeight = FontWeight.SemiBold)
                        }
                        Column {
                            Text("Floating PnL", fontSize = 12.sp, color = Color.Gray)
                            val pnlColor = if (accountInfo.profit >= 0) Color(0xFF00E676) else Color(0xFFFF1744)
                            Text(
                                "$${String.format("%.2f", accountInfo.profit)}",
                                fontWeight = FontWeight.SemiBold,
                                color = pnlColor
                            )
                        }
                        Column {
                            Text("D-Score", fontSize = 12.sp, color = Color.Gray)
                            Text(
                                "${accountInfo.dScore ?: 78.2}",
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.secondary
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Action Buttons Section
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = onStartStrategy,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
                ) {
                    Text("START", fontWeight = FontWeight.Bold, color = Color.Black)
                }

                Button(
                    onClick = onPauseStrategy,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFFFB300))
                ) {
                    Text("PAUSE", fontWeight = FontWeight.Bold, color = Color.Black)
                }

                Button(
                    onClick = onKillSwitch,
                    modifier = Modifier.weight(1.2f),
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.tertiary)
                ) {
                    Text("KILL SWITCH", fontWeight = FontWeight.Bold, color = Color.White)
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            Text(
                "Open Positions (${positions.size})",
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onBackground
            )

            Spacer(modifier = Modifier.height(8.dp))

            if (positions.isEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    contentAlignment = Alignment.Center
                ) {
                    Text("No open positions active", color = Color.Gray)
                }
            } else {
                LazyColumn(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(positions) { pos ->
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(12.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column {
                                    Text("${pos.symbol} • ${pos.orderType}", fontWeight = FontWeight.Bold)
                                    Text("Vol: ${pos.volume} | Entry: ${pos.openPrice}", fontSize = 12.sp, color = Color.Gray)
                                }
                                val pnlColor = if (pos.pnl >= 0) Color(0xFF00E676) else Color(0xFFFF1744)
                                Text(
                                    "$${String.format("%.2f", pos.pnl)}",
                                    fontWeight = FontWeight.Bold,
                                    color = pnlColor,
                                    fontSize = 16.sp
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
