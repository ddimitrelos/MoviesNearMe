package com.movienearme.data.api

import com.movienearme.data.model.Cinema
import com.movienearme.data.model.Movie
import retrofit2.http.GET
import retrofit2.http.Query

interface ApiService {

    @GET("movies")
    suspend fun getMovies(
        @Query("query") query: String? = null,
        @Query("only_showing") onlyShowing: Boolean = true,
    ): List<Movie>

    @GET("cinemas")
    suspend fun getCinemas(
        @Query("movie_id") movieId: Int? = null,
        @Query("within_hours") withinHours: Double? = null,
        @Query("lat") lat: Double? = null,
        @Query("lng") lng: Double? = null,
    ): List<Cinema>
}
