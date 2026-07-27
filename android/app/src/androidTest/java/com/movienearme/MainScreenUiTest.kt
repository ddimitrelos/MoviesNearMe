package com.movienearme

import android.Manifest
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Instrumented UI tests that run on the emulator. They only assert on static UI
 * chrome (which composes immediately), so they don't depend on the backend.
 * assertExists() is used rather than assertIsDisplayed() because chips/settings
 * rows may be off-screen in scrollable containers while still composed.
 */
@RunWith(AndroidJUnit4::class)
class MainScreenUiTest {

    // Grant location before the activity launches so no system dialog appears.
    @get:Rule(order = 0)
    val permission: GrantPermissionRule =
        GrantPermissionRule.grant(Manifest.permission.ACCESS_FINE_LOCATION)

    @get:Rule(order = 1)
    val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun filterBar_rendersChips() {
        compose.onNodeWithText("Any time").assertExists()
        compose.onNodeWithText("Summer").assertExists()
        compose.onNodeWithText("Near me").assertExists()
    }

    @Test
    fun settings_openFromGear_showsSections() {
        compose.onNodeWithContentDescription("Open settings").performClick()
        compose.waitForIdle()
        compose.onNodeWithText("Language").assertExists()
        compose.onNodeWithText("Points of interest").assertExists()
    }
}
