package com.movienearme

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.movienearme.data.LocaleManager
import com.movienearme.data.SettingsStore
import com.movienearme.location.LocationHelper
import com.movienearme.ui.MainScreen
import com.movienearme.ui.MapViewModel
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private val vm: MapViewModel by viewModels()
    private lateinit var locationHelper: LocationHelper

    // Language this activity instance was created with (for detecting changes).
    private var createdLanguage: String = "system"

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        val granted = grants.values.any { it }
        resolveLocation(useGps = granted)
    }

    override fun attachBaseContext(newBase: Context) {
        val lang = SettingsStore(newBase).language()
        createdLanguage = lang
        super.attachBaseContext(LocaleManager.wrap(newBase, lang))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        locationHelper = LocationHelper(this)

        vm.loadMovies()

        setContent {
            // Recreate the activity when the user picks a different language so
            // the whole UI re-renders in the new locale.
            val state by vm.state.collectAsState()
            LaunchedEffect(state.settings.language) {
                if (state.settings.language != createdLanguage) recreate()
            }
            MaterialTheme(colorScheme = darkColorScheme()) {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    MainScreen(vm)
                }
            }
        }

        requestLocation()
    }

    private fun requestLocation() {
        val fine = Manifest.permission.ACCESS_FINE_LOCATION
        if (ContextCompat.checkSelfPermission(this, fine) == PackageManager.PERMISSION_GRANTED) {
            resolveLocation(useGps = true)
        } else {
            permissionLauncher.launch(
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION,
                )
            )
        }
    }

    private fun resolveLocation(useGps: Boolean) {
        lifecycleScope.launch {
            val loc = if (useGps) locationHelper.currentLocation() else null
            vm.setUserLocation(loc ?: locationHelper.fallback)
        }
    }
}
