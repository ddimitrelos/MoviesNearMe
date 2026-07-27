package com.movienearme

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.unit.dp
import com.movienearme.data.model.Cinema
import com.movienearme.data.model.Movie
import com.movienearme.data.model.ScreeningBrief
import com.movienearme.ui.CinemaDetails
import org.junit.Rule
import org.junit.Test

/**
 * Guards the "cinema sheet clipped its last movies" bug: the detail content must
 * be scrollable so a cinema with many movies exposes all of them. performScrollTo
 * throws if there's no scrollable ancestor, so this fails if the fix regresses.
 */
class CinemaDetailsScrollTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun manyMovies_lastOneReachableByScrolling() {
        val movies = (1..8).map { Movie(id = it, slug = "m$it", title = "MovieTitle$it") }
        val screenings = movies.mapIndexed { i, m ->
            ScreeningBrief(id = i, startTime = "2026-07-27T20:00:00", hall = "Room", movie = m)
        }
        val cinema = Cinema(
            id = 1, slug = "c", name = "Test Cinema",
            lat = 37.9, lng = 23.7, screenings = screenings,
        )

        compose.setContent {
            Box(Modifier.height(400.dp)) { CinemaDetails(cinema) }
        }

        compose.onNodeWithText("MovieTitle8").performScrollTo().assertIsDisplayed()
    }
}
