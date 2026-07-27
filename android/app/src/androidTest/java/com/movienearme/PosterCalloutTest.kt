package com.movienearme

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.movienearme.data.model.Cinema
import com.movienearme.data.model.Movie
import com.movienearme.data.model.ScreeningBrief
import com.movienearme.ui.PosterCallout
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class PosterCalloutTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun rendersAPosterPerMovie_andTapOpensThatMovie() {
        val alpha = Movie(id = 1, slug = "a", title = "Alpha", sourceUrl = "https://ath/a")
        val beta = Movie(id = 2, slug = "b", title = "Beta", sourceUrl = "https://ath/b")
        val screenings = listOf(
            ScreeningBrief(1, "2026-07-27T20:00:00", "R1", alpha),
            ScreeningBrief(2, "2026-07-27T20:00:00", "R1", alpha), // same movie, deduped
            ScreeningBrief(3, "2026-07-27T21:00:00", "R2", beta),
        )
        val cinema = Cinema(id = 1, slug = "c", name = "Cine X", screenings = screenings)

        var opened: Movie? = null
        compose.setContent {
            PosterCallout(cinema, onPosterClick = { opened = it }, onOpenDetails = {})
        }

        compose.onNodeWithText("Alpha").assertExists()
        compose.onNodeWithText("Beta").assertExists()

        compose.onNodeWithText("Beta").performClick()
        assertEquals(2, opened?.id)
    }
}
