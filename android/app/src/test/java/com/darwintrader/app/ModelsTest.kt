package com.darwintrader.app

import com.darwintrader.app.data.model.*
import com.google.gson.Gson
import org.junit.Assert.*
import org.junit.Test

class ModelsTest {

    private val gson = Gson()

    @Test
    fun testAccountConnectRequestSerialization() {
        val request = AccountConnectRequest(
            login = 123456L,
            password = "securePassword",
            server = "Darwinex-Live",
            path = "C:\\MT5\\terminal64.exe",
            mockMode = false
        )

        val json = gson.toJson(request)
        assertTrue(json.contains("\"login\":123456"))
        assertTrue(json.contains("\"password\":\"securePassword\""))
        assertTrue(json.contains("\"server\":\"Darwinex-Live\""))
        assertTrue(json.contains("\"path\":\"C:\\\\MT5\\\\terminal64.exe\""))
        assertTrue(json.contains("\"mock_mode\":false"))
    }

    @Test
    fun testAccountConnectResponseDeserialization_success() {
        val json = """
            {
                "status": "CONNECTED",
                "message": "Connected to Darwinex-Demo in mock mode",
                "login": 105382,
                "server": "Darwinex-Demo",
                "trade_mode": "DEMO",
                "balance": 100000.0,
                "currency": "USD",
                "account_info": {
                    "login": 105382,
                    "trade_mode": "DEMO",
                    "server": "Darwinex-Demo",
                    "balance": 100000.0,
                    "equity": 100000.0,
                    "d_score": 75.4
                },
                "error": null
            }
        """.trimIndent()

        val response = gson.fromJson(json, AccountConnectResponse::class.java)
        assertEquals("CONNECTED", response.status)
        assertEquals(105382L, response.login)
        assertEquals("Darwinex-Demo", response.server)
        assertEquals("DEMO", response.tradeMode)
        assertEquals(100000.0, response.balance, 0.001)
        assertNull(response.error)
        assertNotNull(response.accountInfo)
        assertEquals(75.4, response.accountInfo?.dScore ?: 0.0, 0.001)
    }

    @Test
    fun testAccountConnectResponseDeserialization_error() {
        val json = """
            {
                "status": "ERROR",
                "message": "Terminal not running",
                "login": 999999,
                "server": "Darwinex-Live",
                "trade_mode": "REAL",
                "balance": 0.0,
                "currency": "USD",
                "account_info": null,
                "error": "Terminal not running: IPC pipe closed"
            }
        """.trimIndent()

        val response = gson.fromJson(json, AccountConnectResponse::class.java)
        assertEquals("ERROR", response.status)
        assertEquals("Terminal not running: IPC pipe closed", response.error)
        assertEquals(0.0, response.balance, 0.001)
        assertNull(response.accountInfo)
    }

    @Test
    fun testAccountStatusResponseDeserialization() {
        val json = """
            {
                "status": "CONNECTED",
                "server": "Darwinex-Live",
                "mock_mode": false,
                "latency_ms": 1.45,
                "connected_at": "2026-08-26T21:45:00",
                "last_error": null,
                "account_info": {
                    "login": 55555,
                    "balance": 50000.0
                }
            }
        """.trimIndent()

        val status = gson.fromJson(json, AccountStatusResponse::class.java)
        assertEquals("CONNECTED", status.status)
        assertEquals("Darwinex-Live", status.server)
        assertFalse(status.mockMode)
        assertEquals(1.45, status.latencyMs, 0.001)
        assertEquals("2026-08-26T21:45:00", status.connectedAt)
        assertNull(status.lastError)
        assertNotNull(status.accountInfo)
        assertEquals(55555L, status.accountInfo?.login)
    }

    @Test
    fun testConnectionBadgeText_liveConnected() {
        val status = AccountStatusResponse(
            status = "CONNECTED",
            server = "Darwinex-Live",
            mockMode = false
        )
        assertEquals("Connected (Live)", status.getConnectionBadgeText())
    }

    @Test
    fun testConnectionBadgeText_demoConnected() {
        val status = AccountStatusResponse(
            status = "CONNECTED",
            server = "Darwinex-Demo",
            mockMode = false
        )
        assertEquals("Connected (Demo)", status.getConnectionBadgeText())
    }

    @Test
    fun testConnectionBadgeText_simulation() {
        val status = AccountStatusResponse(
            status = "CONNECTED",
            server = "Darwinex-Live",
            mockMode = true
        )
        assertEquals("Simulation", status.getConnectionBadgeText())
    }

    @Test
    fun testConnectionBadgeText_disconnected() {
        val status = AccountStatusResponse(
            status = "DISCONNECTED",
            server = "Darwinex-Demo",
            mockMode = true
        )
        assertEquals("Disconnected", status.getConnectionBadgeText())
    }

    @Test
    fun testConnectionBadgeText_error() {
        val status = AccountStatusResponse(
            status = "ERROR",
            server = "Darwinex-Live",
            mockMode = false,
            lastError = "Terminal not running"
        )
        assertEquals("Disconnected", status.getConnectionBadgeText())
    }

    @Test
    fun testConnectionBadgeText_null() {
        val status: AccountStatusResponse? = null
        assertEquals("Disconnected", status.getConnectionBadgeText())
    }
}

