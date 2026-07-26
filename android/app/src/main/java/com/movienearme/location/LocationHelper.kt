package com.movienearme.location

import android.annotation.SuppressLint
import android.content.Context
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

data class LatLng(val lat: Double, val lng: Double)

class LocationHelper(context: Context) {

    private val client = LocationServices.getFusedLocationProviderClient(context)

    // Central Athens (Syntagma) — used as a fallback when GPS is unavailable.
    val fallback = LatLng(37.9755, 23.7348)

    @SuppressLint("MissingPermission")
    suspend fun currentLocation(): LatLng? =
        suspendCancellableCoroutine { cont ->
            client.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, null)
                .addOnSuccessListener { loc ->
                    cont.resume(loc?.let { LatLng(it.latitude, it.longitude) })
                }
                .addOnFailureListener { cont.resume(null) }
        }
}
