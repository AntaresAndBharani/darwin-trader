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
