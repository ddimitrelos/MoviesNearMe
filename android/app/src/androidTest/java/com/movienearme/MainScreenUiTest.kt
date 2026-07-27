package com.movienearme

import android.Manifest
import androidx.compose.ui.test.assertIsDisplayed
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
 * Instrumented UI tests that run on the emulator. They only assert on static
 * UI chrome (which renders immediately), so they don't depend on the backend.
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
    fun filterBar_showsTimeChips() {
        // "Today" is the default-selected time chip and needs no network.
        compose.onNodeWithText("Today").assertIsDisplayed()
        compose.onNodeWithText("Summer").assertIsDisplayed()
        compose.onNodeWithText("Near me").assertIsDisplayed()
    }

    @Test
    fun settings_openFromGear_showsLanguageSection() {
        compose.onNodeWithContentDescription("Open settings").performClick()
        compose.onNodeWithText("Language").assertIsDisplayed()
        compose.onNodeWithText("Points of interest").assertIsDisplayed()
    }
}
