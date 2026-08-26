package com.darwintrader.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Analytics
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.lifecycle.lifecycleScope
import com.darwintrader.app.data.api.ApiService
import com.darwintrader.app.data.model.AccountInfo
import com.darwintrader.app.data.model.Position
import com.darwintrader.app.ui.account.AccountSettingsScreen
import com.darwintrader.app.ui.backtest.BacktestScreen
import com.darwintrader.app.ui.dashboard.DashboardScreen
import com.darwintrader.app.ui.strategy.StrategyControlScreen
import com.darwintrader.app.ui.theme.DarwinTraderTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val apiService by lazy { ApiService.create() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            DarwinTraderTheme {
                var selectedTab by remember { mutableIntStateOf(0) }
                var accountInfo by remember { mutableStateOf(AccountInfo()) }
                var positions by remember { mutableStateOf<List<Position>>(emptyList()) }
                var strategyStatus by remember { mutableStateOf("IDLE") }

                fun fetchTelemetry() {
                    lifecycleScope.launch {
                        try {
                            val accRes = apiService.getAccountInfo()
                            if (accRes.isSuccessful) accRes.body()?.let { accountInfo = it }

                            val posRes = apiService.getPositions()
                            if (posRes.isSuccessful) posRes.body()?.let { positions = it }

                            val statusRes = apiService.getStrategyStatus()
                            if (statusRes.isSuccessful) statusRes.body()?.let { strategyStatus = it.status }
                        } catch (e: Exception) {
                            // Fallback to default mock data if offline
                        }
                    }
                }

                LaunchedEffect(Unit) {
                    fetchTelemetry()
                }

                Scaffold(
                    bottomBar = {
                        NavigationBar(
                            containerColor = MaterialTheme.colorScheme.surface
                        ) {
                            NavigationBarItem(
                                selected = selectedTab == 0,
                                onClick = { selectedTab = 0 },
                                icon = { Icon(Icons.Default.Dashboard, contentDescription = "Dashboard") },
                                label = { Text("Dashboard") }
                            )
                            NavigationBarItem(
                                selected = selectedTab == 1,
                                onClick = { selectedTab = 1 },
                                icon = { Icon(Icons.Default.Settings, contentDescription = "Strategy") },
                                label = { Text("Strategy") }
                            )
                            NavigationBarItem(
                                selected = selectedTab == 2,
                                onClick = { selectedTab = 2 },
                                icon = { Icon(Icons.Default.Analytics, contentDescription = "Backtest") },
                                label = { Text("Backtest") }
                            )
                            NavigationBarItem(
                                selected = selectedTab == 3,
                                onClick = { selectedTab = 3 },
                                icon = { Icon(Icons.Default.AccountCircle, contentDescription = "Account") },
                                label = { Text("Account") }
                            )
                        }
                    }
                ) { innerPadding ->
                    Surface(modifier = Modifier.padding(innerPadding)) {
                        when (selectedTab) {
                            0 -> DashboardScreen(
                                accountInfo = accountInfo,
                                positions = positions,
                                strategyStatus = strategyStatus,
                                onStartStrategy = {
                                    lifecycleScope.launch {
                                        apiService.startStrategy()
                                        fetchTelemetry()
                                    }
                                },
                                onPauseStrategy = {
                                    lifecycleScope.launch {
                                        apiService.pauseStrategy()
                                        fetchTelemetry()
                                    }
                                },
                                onKillSwitch = {
                                    lifecycleScope.launch {
                                        apiService.triggerKillSwitch()
                                        fetchTelemetry()
                                    }
                                }
                            )
                            1 -> StrategyControlScreen()
                            2 -> BacktestScreen()
                            3 -> AccountSettingsScreen(
                                apiService = apiService,
                                onAccountConnected = {
                                    accountInfo = it
                                    fetchTelemetry()
                                }
                            )
                        }
                    }
                }
            }
        }
    }
}
