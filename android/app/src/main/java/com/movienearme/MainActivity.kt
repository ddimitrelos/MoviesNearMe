package com.movienearme

import android.Manifest
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
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.movienearme.location.LocationHelper
import com.movienearme.ui.MainScreen
import com.movienearme.ui.MapViewModel
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private val vm: MapViewModel by viewModels()
    private lateinit var locationHelper: LocationHelper

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        val granted = grants.values.any { it }
        resolveLocation(useGps = granted)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        locationHelper = LocationHelper(this)

        vm.loadMovies()

        setContent {
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
