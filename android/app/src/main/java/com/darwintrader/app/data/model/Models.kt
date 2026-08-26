package com.darwintrader.app.data.model

import com.google.gson.annotations.SerializedName

data class AccountInfo(
    @SerializedName("login") val login: Long = 0,
    @SerializedName("trade_mode") val tradeMode: String = "DEMO",
    @SerializedName("server") val server: String = "Darwinex-Demo",
    @SerializedName("balance") val balance: Double = 100000.0,
    @SerializedName("equity") val equity: Double = 100000.0,
    @SerializedName("margin") val margin: Double = 0.0,
    @SerializedName("free_margin") val freeMargin: Double = 100000.0,
    @SerializedName("profit") val profit: Double = 0.0,
    @SerializedName("currency") val currency: String = "USD",
    @SerializedName("d_score") val dScore: Double? = 78.2
)

data class Position(
    @SerializedName("ticket") val ticket: Long,
    @SerializedName("symbol") val symbol: String,
    @SerializedName("order_type") val orderType: String,
    @SerializedName("volume") val volume: Double,
    @SerializedName("open_price") val openPrice: Double,
    @SerializedName("current_price") val currentPrice: Double,
    @SerializedName("sl") val sl: Double = 0.0,
    @SerializedName("tp") val tp: Double = 0.0,
    @SerializedName("pnl") val pnl: Double = 0.0
)

data class StrategyStatusResponse(
    @SerializedName("status") val status: String,
    @SerializedName("strategy_name") val strategyName: String,
    @SerializedName("symbol") val symbol: String,
    @SerializedName("mock_mode") val mockMode: Boolean,
    @SerializedName("open_positions_count") val openPositionsCount: Int,
    @SerializedName("account_balance") val accountBalance: Double,
    @SerializedName("account_equity") val accountEquity: Double,
    @SerializedName("d_score") val dScore: Double?
)

data class DarwinexStatsResponse(
    @SerializedName("darwin_symbol") val darwinSymbol: String,
    @SerializedName("d_score") val dScore: Double,
    @SerializedName("investor_capital_allocated_eur") val investorCapital: Double,
    @SerializedName("return_pct_monthly") val returnMonthly: Double,
    @SerializedName("max_drawdown_pct") val maxDrawdown: Double,
    @SerializedName("var_95_pct") val var95: Double,
    @SerializedName("darwinex_zero_status") val status: String
)

data class GenericResponse(
    @SerializedName("message") val message: String,
    @SerializedName("status") val status: String? = null
)

data class AccountConnectRequest(
    @SerializedName("login") val login: Long = 0,
    @SerializedName("password") val password: String = "",
    @SerializedName("server") val server: String = "Darwinex-Demo",
    @SerializedName("path") val path: String? = "C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe",
    @SerializedName("mock_mode") val mockMode: Boolean = true
)

data class AccountConnectResponse(
    @SerializedName("status") val status: String = "CONNECTED",
    @SerializedName("message") val message: String = "",
    @SerializedName("login") val login: Long = 0,
    @SerializedName("server") val server: String = "Darwinex-Demo",
    @SerializedName("trade_mode") val tradeMode: String = "DEMO",
    @SerializedName("balance") val balance: Double = 100000.0,
    @SerializedName("currency") val currency: String = "USD",
    @SerializedName("account_info") val accountInfo: AccountInfo? = null,
    @SerializedName("error") val error: String? = null
)

data class AccountStatusResponse(
    @SerializedName("status") val status: String = "DISCONNECTED",
    @SerializedName("server") val server: String = "Darwinex-Demo",
    @SerializedName("mock_mode") val mockMode: Boolean = true,
    @SerializedName("latency_ms") val latencyMs: Double = 0.0,
    @SerializedName("connected_at") val connectedAt: String? = null,
    @SerializedName("last_error") val lastError: String? = null,
    @SerializedName("account_info") val accountInfo: AccountInfo? = null
)

typealias ConnectionStatusResponse = AccountStatusResponse

