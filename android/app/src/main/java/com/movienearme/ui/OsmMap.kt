package com.movienearme.ui

import android.content.res.Resources
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.preference.PreferenceManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import com.movienearme.data.Poi
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
    pois: List<Poi> = emptyList(),
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

            // User points of interest (Home/Work…) — violet labeled chip.
            pois.forEach { poi ->
                val marker = Marker(map).apply {
                    position = GeoPoint(poi.lat, poi.lng)
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                    icon = labelChipDrawable(context.resources, poi.label)
                    title = poi.label
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

/** A rounded violet chip with the POI label drawn in white — always visible on the map. */
private fun labelChipDrawable(res: Resources, label: String): Drawable {
    val d = res.displayMetrics.density
    val padH = 10f * d
    val padV = 6f * d
    val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = 12f * d
        typeface = Typeface.DEFAULT_BOLD
    }
    val fm = textPaint.fontMetrics
    val textW = textPaint.measureText(label)
    val textH = fm.descent - fm.ascent
    val w = (textW + padH * 2).toInt().coerceAtLeast(1)
    val h = (textH + padV * 2).toInt().coerceAtLeast(1)
    val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bmp)
    val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF7C4DFF.toInt() }
    val r = h / 2f
    canvas.drawRoundRect(0f, 0f, w.toFloat(), h.toFloat(), r, r, bgPaint)
    val strokePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2f * d
        color = Color.WHITE
    }
    canvas.drawRoundRect(1f, 1f, w - 1f, h - 1f, r, r, strokePaint)
    canvas.drawText(label, padH, padV - fm.ascent, textPaint)
    return BitmapDrawable(res, bmp)
}
