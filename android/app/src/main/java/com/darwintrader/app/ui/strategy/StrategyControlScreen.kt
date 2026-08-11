package com.darwintrader.app.ui.strategy

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun StrategyControlScreen() {
    var riskPct by remember { mutableStateOf("1.0") }
    var maxDrawdownPct by remember { mutableStateOf("3.0") }
    var magicNumber by remember { mutableStateOf("20260811") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Text("Strategy Parameters", fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Spacer(modifier = Modifier.height(16.dp))

        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(12.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                OutlinedTextField(
                    value = riskPct,
                    onValueChange = { riskPct = it },
                    label = { Text("Risk Per Trade (%)") },
                    modifier = Modifier.fillMaxWidth()
                )

                Spacer(modifier = Modifier.height(12.dp))

                OutlinedTextField(
                    value = maxDrawdownPct,
                    onValueChange = { maxDrawdownPct = it },
                    label = { Text("Max Daily Drawdown Cap (%)") },
                    modifier = Modifier.fillMaxWidth()
                )

                Spacer(modifier = Modifier.height(12.dp))

                OutlinedTextField(
                    value = magicNumber,
                    onValueChange = { magicNumber = it },
                    label = { Text("Strategy Magic Number") },
                    modifier = Modifier.fillMaxWidth()
                )

                Spacer(modifier = Modifier.height(16.dp))

                Button(
                    onClick = { /* Apply config updates */ },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
                ) {
                    Text("SAVE PARAMETERS", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}
