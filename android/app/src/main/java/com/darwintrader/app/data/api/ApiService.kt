package com.darwintrader.app.data.api

import com.darwintrader.app.data.model.*
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Body
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

interface ApiService {
    @GET("api/v1/strategy/status")
    suspend fun getStrategyStatus(): Response<StrategyStatusResponse>

    @POST("api/v1/strategy/start")
    suspend fun startStrategy(): Response<GenericResponse>

    @POST("api/v1/strategy/pause")
    suspend fun pauseStrategy(): Response<GenericResponse>

    @POST("api/v1/strategy/stop")
    suspend fun stopStrategy(): Response<GenericResponse>

    @POST("api/v1/strategy/kill-switch")
    suspend fun triggerKillSwitch(): Response<GenericResponse>

    @GET("api/v1/account/info")
    suspend fun getAccountInfo(): Response<AccountInfo>

    @GET("api/v1/account/positions")
    suspend fun getPositions(): Response<List<Position>>

    @GET("api/v1/account/darwinex-stats")
    suspend fun getDarwinexStats(): Response<DarwinexStatsResponse>

    companion object {
        private const val BASE_URL = "http://10.0.2.2:8000/" // Android Emulator localhost bridge

        fun create(): ApiService {
            return Retrofit.Builder()
                .baseUrl(BASE_URL)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(ApiService::class.java)
        }
    }
}
