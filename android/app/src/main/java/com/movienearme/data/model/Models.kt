package com.movienearme.data.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class Movie(
    val id: Int,
    val slug: String,
    val title: String,
    @Json(name = "original_title") val originalTitle: String? = null,
    val genre: String? = null,
    @Json(name = "duration_min") val durationMin: Int? = null,
    @Json(name = "poster_url") val posterUrl: String? = null,
)

@JsonClass(generateAdapter = true)
data class ScreeningBrief(
    val id: Int,
    @Json(name = "start_time") val startTime: String,
    val hall: String? = null,
    val movie: Movie,
)

@JsonClass(generateAdapter = true)
data class Cinema(
    val id: Int,
    val slug: String,
    val name: String,
    val address: String? = null,
    val phone: String? = null,
    val lat: Double? = null,
    val lng: Double? = null,
    val region: String? = null,
    @Json(name = "distance_km") val distanceKm: Double? = null,
    val screenings: List<ScreeningBrief> = emptyList(),
)
