package com.movienearme

import com.movienearme.data.AppSettings
import com.movienearme.data.Poi
import com.movienearme.data.model.Movie
import com.movienearme.location.LatLng
import com.movienearme.ui.MapUiState
import com.movienearme.ui.TimeFilter
import com.movienearme.ui.selectingOrigin
import com.movienearme.ui.toCinemaQuery
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Pure-logic tests for how UI state maps to /cinemas request parameters.
 * These would have caught the "Near me used GPS instead of the POI" bug.
 */
class CinemaQueryTest {

    private val gps = LatLng(37.9420, 23.6470)          // Piraeus
    private val home = Poi("h1", "Home", 38.07, 23.81)  // Kifisia

    @Test
    fun nearMeOff_usesGps_andNoRadius() {
        val q = MapUiState(userLocation = gps, nearMe = false).toCinemaQuery()
        assertEquals(37.9420, q.lat!!, 1e-6)
        assertEquals(23.6470, q.lng!!, 1e-6)
        assertNull(q.maxKm)
    }

    @Test
    fun nearMeOn_withPoiOrigin_usesPoiCoordinates() {
        val state = MapUiState(
            userLocation = gps,
            nearMe = true,
            settings = AppSettings(pois = listOf(home), nearMeOriginId = "h1", nearMeKm = 5),
        )
        val q = state.toCinemaQuery()
        assertEquals("lat should be the POI's, not GPS", 38.07, q.lat!!, 1e-6)
        assertEquals("lng should be the POI's, not GPS", 23.81, q.lng!!, 1e-6)
        assertEquals(5.0, q.maxKm!!, 1e-6)
    }

    @Test
    fun nearMeOn_withoutOrigin_usesGps() {
        val state = MapUiState(userLocation = gps, nearMe = true, settings = AppSettings(nearMeKm = 7))
        val q = state.toCinemaQuery()
        assertEquals(37.9420, q.lat!!, 1e-6)
        assertEquals(7.0, q.maxKm!!, 1e-6)
    }

    @Test
    fun quickFilterA_usesConfiguredHours() {
        val state = MapUiState(timeFilter = TimeFilter.QUICK_A, settings = AppSettings(filterAHours = 4))
        assertEquals(4.0, state.toCinemaQuery().withinHours!!, 1e-6)
    }

    @Test
    fun today_is24h_and_anytime_isNull() {
        assertEquals(24.0, MapUiState(timeFilter = TimeFilter.TODAY).toCinemaQuery().withinHours!!, 1e-6)
        assertNull(MapUiState(timeFilter = TimeFilter.ANY).toCinemaQuery().withinHours)
    }

    @Test
    fun movieFilter_passesMovieId() {
        val state = MapUiState(selectedMovie = Movie(id = 42, slug = "x", title = "X"))
        assertEquals(42, state.toCinemaQuery().movieId)
    }

    // --- Tapping a POI on the map selects it as the Near me origin ---

    @Test
    fun tappingPoi_enablesNearMe_andUsesItsCoordinates() {
        val base = MapUiState(
            userLocation = gps,
            settings = AppSettings(pois = listOf(home), nearMeKm = 5),
        )
        val after = base.selectingOrigin("h1")
        assertTrue("Near me should turn on", after.nearMe)
        assertEquals("h1", after.settings.nearMeOriginId)
        val q = after.toCinemaQuery()
        assertEquals(38.07, q.lat!!, 1e-6)   // Home, not GPS
        assertEquals(23.81, q.lng!!, 1e-6)
    }

    @Test
    fun tappingMyLocation_enablesNearMe_fromGps() {
        val base = MapUiState(
            userLocation = gps,
            settings = AppSettings(pois = listOf(home), nearMeOriginId = "h1"),
        )
        val after = base.selectingOrigin(null)
        assertTrue(after.nearMe)
        assertNull(after.settings.nearMeOriginId)
        val q = after.toCinemaQuery()
        assertEquals(37.9420, q.lat!!, 1e-6)  // back to GPS
        assertEquals(23.6470, q.lng!!, 1e-6)
    }
}
