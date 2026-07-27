package com.movienearme.ui

import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.preference.PreferenceManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import com.movienearme.data.model.Cinema
import com.movienearme.location.LatLng
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker

@Composable
fun OsmMap(
    cinemas: List<Cinema>,
    userLocation: LatLng?,
    selectedCinemaId: Int?,
    youAreHere: String,
    onCinemaClick: (Cinema) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current

    val mapView = remember {
        Configuration.getInstance().load(
            context,
            PreferenceManager.getDefaultSharedPreferences(context)
        )
        Configuration.getInstance().userAgentValue = context.packageName
        MapView(context).apply {
            setTileSource(TileSourceFactory.MAPNIK)
            setMultiTouchControls(true)
            controller.setZoom(12.5)
            controller.setCenter(GeoPoint(37.9838, 23.7275)) // Athens
        }
    }

    AndroidView(
        modifier = modifier,
        factory = { mapView },
        update = { map ->
            map.overlays.clear()

            userLocation?.let {
                val me = Marker(map).apply {
                    position = GeoPoint(it.lat, it.lng)
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                    title = youAreHere
                    icon = dotDrawable(0xFF2979FF.toInt())
                }
                map.overlays.add(me)
            }

            cinemas.forEach { cinema ->
                if (cinema.lat == null || cinema.lng == null) return@forEach
                val marker = Marker(map).apply {
                    position = GeoPoint(cinema.lat, cinema.lng)
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                    title = cinema.name
                    snippet = cinema.address ?: ""
                    val highlighted = cinema.id == selectedCinemaId
                    val color = when {
                        highlighted -> 0xFFFFC107.toInt()          // gold = selected
                        cinema.isSummer -> 0xFF00BFA5.toInt()      // teal = open-air
                        else -> 0xFFE50914.toInt()                 // red = indoor
                    }
                    icon = pinDrawable(color)
                    setOnMarkerClickListener { _, _ ->
                        onCinemaClick(cinema)
                        true
                    }
                }
                map.overlays.add(marker)
            }
            map.invalidate()
        }
    )
}

private fun dotDrawable(color: Int): GradientDrawable =
    GradientDrawable().apply {
        shape = GradientDrawable.OVAL
        setColor(color)
        setStroke(4, Color.WHITE)
        setSize(36, 36)
    }

private fun pinDrawable(color: Int): GradientDrawable =
    GradientDrawable().apply {
        shape = GradientDrawable.OVAL
        setColor(color)
        setStroke(6, Color.WHITE)
        setSize(52, 52)
    }
