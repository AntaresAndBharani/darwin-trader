package com.darwintrader.app.ui.account

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.darwintrader.app.data.api.ApiService
import com.darwintrader.app.data.model.AccountConnectRequest
import com.darwintrader.app.data.model.AccountConnectResponse
import com.darwintrader.app.data.model.AccountInfo
import kotlinx.coroutines.launch

@Composable
fun AccountSettingsScreen(
    apiService: ApiService = remember { ApiService.create() },
    onAccountConnected: ((AccountInfo) -> Unit)? = null
) {
    val coroutineScope = rememberCoroutineScope()
    val scrollState = rememberScrollState()

    var login by remember { mutableStateOf("105382") }
    var password by remember { mutableStateOf("") }
    var passwordVisible by remember { mutableStateOf(false) }
    var server by remember { mutableStateOf("Darwinex-Demo") }
    var terminalPath by remember { mutableStateOf("C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe") }
    var mockMode by remember { mutableStateOf(true) }

    var isLoading by remember { mutableStateOf(false) }
    var connectResponse by remember { mutableStateOf<AccountConnectResponse?>(null) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    fun performConnectionTest() {
        coroutineScope.launch {
            isLoading = true
            errorMessage = null
            connectResponse = null
            try {
                val loginNum = login.trim().toLongOrNull() ?: 0L
                val request = AccountConnectRequest(
                    login = loginNum,
                    password = password,
                    server = server.trim(),
                    path = terminalPath.trim().ifBlank { null },
                    mockMode = mockMode
                )
                val response = apiService.connectAccount(request)
                if (response.isSuccessful && response.body() != null) {
                    val body = response.body()!!
                    connectResponse = body
                    if (body.status == "CONNECTED") {
                        body.accountInfo?.let { onAccountConnected?.invoke(it) }
                    } else {
                        errorMessage = body.error ?: body.message.ifBlank { "Connection failed on $server" }
                    }
                } else {
                    errorMessage = "Server error (HTTP ${response.code()}): ${response.message().ifBlank { "Failed to connect" }}"
                }
            } catch (e: Exception) {
                errorMessage = e.localizedMessage ?: "Network error: Unable to reach Darwin Trader gateway"
            } finally {
                isLoading = false
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scrollState)
            .padding(16.dp)
    ) {
        Text(
            text = "Account & MT5 Connection",
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onBackground
        )

        Text(
            text = "Configure your Darwinex Zero / DarwinX MT5 credentials",
            fontSize = 14.sp,
            color = Color.Gray
        )

        Spacer(modifier = Modifier.height(16.dp))

        // Configuration Card Form
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(12.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                // Mock Mode Toggle
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = if (mockMode) "Mock Simulation Mode" else "Live MT5 Terminal",
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 16.sp
                        )
                        Text(
                            text = if (mockMode) "Simulates MT5 IPC responses locally" else "Connects to running MT5 terminal via IPC",
                            fontSize = 12.sp,
                            color = Color.Gray
                        )
                    }
                    Switch(
                        checked = mockMode,
                        onCheckedChange = { mockMode = it }
                    )
                }

                Spacer(modifier = Modifier.height(16.dp))
                HorizontalDivider(color = Color.DarkGray)
                Spacer(modifier = Modifier.height(16.dp))

                // Login Field
                OutlinedTextField(
                    value = login,
                    onValueChange = { login = it },
                    label = { Text("MT5 Login / Account ID") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(12.dp))

                // Password Field
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = { Text("MT5 Password") },
                    visualTransformation = if (passwordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    trailingIcon = {
                        IconButton(onClick = { passwordVisible = !passwordVisible }) {
                            Icon(
                                imageVector = if (passwordVisible) Icons.Default.Visibility else Icons.Default.VisibilityOff,
                                contentDescription = if (passwordVisible) "Hide password" else "Show password"
                            )
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(12.dp))

                // Server Field
                OutlinedTextField(
                    value = server,
                    onValueChange = { server = it },
                    label = { Text("MT5 Server (e.g. Darwinex-Live, Darwinex-Demo)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(12.dp))

                // Terminal Path Field
                OutlinedTextField(
                    value = terminalPath,
                    onValueChange = { terminalPath = it },
                    label = { Text("MT5 Terminal Path") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(16.dp))

                // Action Button
                Button(
                    onClick = { performConnectionTest() },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !isLoading,
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
                ) {
                    if (isLoading) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            color = Color.Black,
                            strokeWidth = 2.dp
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("CONNECTING...", fontWeight = FontWeight.Bold, color = Color.Black)
                    } else {
                        Text("TEST CONNECTION", fontWeight = FontWeight.Bold, color = Color.Black)
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // Connection Success State
        if (connectResponse != null && connectResponse?.status == "CONNECTED") {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.CheckCircle,
                            contentDescription = "Connected",
                            tint = Color(0xFF00E676)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "CONNECTED",
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFF00E676),
                            fontSize = 18.sp
                        )
                    }

                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = connectResponse?.message ?: "Account authenticated successfully.",
                        fontSize = 14.sp,
                        color = MaterialTheme.colorScheme.onSurface
                    )

                    Spacer(modifier = Modifier.height(12.dp))
                    HorizontalDivider(color = Color.DarkGray)
                    Spacer(modifier = Modifier.height(12.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column {
                            Text("Account ID", fontSize = 12.sp, color = Color.Gray)
                            Text("${connectResponse?.login}", fontWeight = FontWeight.SemiBold)
                        }
                        Column {
                            Text("Server", fontSize = 12.sp, color = Color.Gray)
                            Text("${connectResponse?.server}", fontWeight = FontWeight.SemiBold)
                        }
                        Column {
                            Text("Balance", fontSize = 12.sp, color = Color.Gray)
                            Text(
                                "$${String.format("%.2f", connectResponse?.balance ?: 0.0)}",
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary
                            )
                        }
                    }
                }
            }
        }

        // Connection Error / Troubleshooting State
        if (errorMessage != null) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.Error,
                            contentDescription = "Connection Error",
                            tint = MaterialTheme.colorScheme.tertiary
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "CONNECTION FAILED",
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.tertiary,
                            fontSize = 16.sp
                        )
                    }

                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = errorMessage ?: "Unknown error occurred during connection",
                        fontSize = 14.sp,
                        color = MaterialTheme.colorScheme.onSurface
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    // Helpful troubleshooting advice
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(Color(0xFF2C1A1D), shape = RoundedCornerShape(8.dp))
                            .padding(12.dp)
                    ) {
                        Column {
                            Text(
                                text = "Troubleshooting tips:",
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.tertiary
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "• Verify MT5 terminal is running if in Live mode\n• Check server name (e.g. Darwinex-Live vs Darwinex-Demo)\n• Confirm account login ID and password are correct\n• Ensure terminal path points to terminal64.exe",
                                fontSize = 12.sp,
                                color = Color.LightGray
                            )
                        }
                    }
                }
            }
        }
    }
}
