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
import android.graphics.Point
import android.preference.PreferenceManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.viewinterop.AndroidView
import com.movienearme.data.Poi
import com.movienearme.data.model.Cinema
import com.movienearme.location.LatLng
import org.osmdroid.config.Configuration
import org.osmdroid.events.MapEventsReceiver
import org.osmdroid.events.MapListener
import org.osmdroid.events.ScrollEvent
import org.osmdroid.events.ZoomEvent
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.MapEventsOverlay
import org.osmdroid.views.overlay.Marker

@Composable
fun OsmMap(
    cinemas: List<Cinema>,
    userLocation: LatLng?,
    selectedCinemaId: Int?,
    youAreHere: String,
    pois: List<Poi> = emptyList(),
    selectedOriginPoiId: String? = null,
    anchorCinema: Cinema? = null,
    onAnchorOffset: (IntOffset?) -> Unit = {},
    onMapClick: () -> Unit = {},
    onCinemaClick: (Cinema) -> Unit,
    onPoiClick: (Poi) -> Unit = {},
    onUserLocationClick: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    // Cinema name pills only render once zoomed in past a threshold; at overview
    // zoom the 100+ labels overlap into an unreadable pile, so show plain dots.
    val showLabelsState = remember { mutableStateOf(shouldShowCinemaLabels(INITIAL_ZOOM)) }
    val anchorState = rememberUpdatedState(anchorCinema)
    val onAnchorState = rememberUpdatedState(onAnchorOffset)
    val onMapClickState = rememberUpdatedState(onMapClick)

    // Projects the anchored cinema's location to a screen pixel offset (or null).
    fun publishAnchor(map: MapView) {
        val c = anchorState.value
        if (c?.lat != null && c.lng != null) {
            val p = map.projection.toPixels(GeoPoint(c.lat, c.lng), Point())
            onAnchorState.value(IntOffset(p.x, p.y))
        } else {
            onAnchorState.value(null)
        }
    }

    val mapView = remember {
        Configuration.getInstance().load(
            context,
            PreferenceManager.getDefaultSharedPreferences(context)
        )
        Configuration.getInstance().userAgentValue = context.packageName
        MapView(context).apply {
            setTileSource(TileSourceFactory.MAPNIK)
            setMultiTouchControls(true)
            controller.setZoom(INITIAL_ZOOM)
            controller.setCenter(GeoPoint(37.9838, 23.7275)) // Athens
            // Re-anchor the callout as the map pans/zooms; toggle name pills by zoom.
            addMapListener(object : MapListener {
                override fun onScroll(event: ScrollEvent?): Boolean { publishAnchor(this@apply); return false }
                override fun onZoom(event: ZoomEvent?): Boolean {
                    showLabelsState.value = shouldShowCinemaLabels(this@apply.zoomLevelDouble)
                    publishAnchor(this@apply); return false
                }
            })
        }
    }

    // Cache generated marker bitmaps (dot + name) so panning doesn't re-allocate.
    val markerCache = remember { HashMap<String, MarkerArt>() }

    // A tap on the map background (not a marker) dismisses the callout.
    val eventsOverlay = remember {
        MapEventsOverlay(object : MapEventsReceiver {
            override fun singleTapConfirmedHelper(p: GeoPoint?): Boolean { onMapClickState.value(); return false }
            override fun longPressHelper(p: GeoPoint?): Boolean = false
        })
    }

    AndroidView(
        modifier = modifier,
        factory = { mapView },
        update = { map ->
            val showLabels = showLabelsState.value
            map.overlays.clear()
            // Background-tap handler must be first and survives the clear above.
            map.overlays.add(eventsOverlay)

            userLocation?.let {
                val me = Marker(map).apply {
                    position = GeoPoint(it.lat, it.lng)
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_CENTER)
                    title = youAreHere
                    icon = dotDrawable(0xFF2979FF.toInt())
                    // Tap the "you are here" dot to measure Near me from my location.
                    setOnMarkerClickListener { _, _ -> onUserLocationClick(); true }
                }
                map.overlays.add(me)
            }

            cinemas.forEach { cinema ->
                if (cinema.lat == null || cinema.lng == null) return@forEach
                val color = when {
                    cinema.id == selectedCinemaId -> 0xFFFFC107.toInt()  // gold = selected
                    cinema.isSummer -> 0xFF00BFA5.toInt()                // teal = open-air
                    else -> 0xFFE50914.toInt()                           // red = indoor
                }
                val art = cinemaMarkerArt(context.resources, color, cinema.name, showLabels, markerCache)
                val marker = Marker(map).apply {
                    position = GeoPoint(cinema.lat, cinema.lng)
                    // Anchor so the dot centre sits on the point; the name label
                    // sits below and is part of the (large) tappable icon.
                    setAnchor(Marker.ANCHOR_CENTER, art.anchorV)
                    title = cinema.name
                    icon = art.drawable
                    setOnMarkerClickListener { _, _ ->
                        onCinemaClick(cinema)
                        true
                    }
                }
                map.overlays.add(marker)
            }

            // User points of interest (Home/Work…) — tap one to make it the
            // Near me origin. The selected origin is shown gold, others violet.
            pois.forEach { poi ->
                val selected = poi.id == selectedOriginPoiId
                val chipColor = if (selected) 0xFFFFC107.toInt() else 0xFF7C4DFF.toInt()
                val marker = Marker(map).apply {
                    position = GeoPoint(poi.lat, poi.lng)
                    setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                    icon = labelChipDrawable(context.resources, poi.label, chipColor)
                    title = poi.label
                    setOnMarkerClickListener { _, _ -> onPoiClick(poi); true }
                }
                map.overlays.add(marker)
            }
            map.invalidate()
            // Update the callout anchor position for the current selection.
            map.post { publishAnchor(map) }
        }
    )
}

/** Default map zoom (whole Athens basin). */
const val INITIAL_ZOOM = 12.5

/** Below this zoom the map shows plain dots; at or above it, dots gain name pills. */
const val LABEL_ZOOM = 14.0

/** Whether cinema name pills should render at the given zoom level. */
fun shouldShowCinemaLabels(zoom: Double): Boolean = zoom >= LABEL_ZOOM

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

/** A generated cinema marker (colored dot + name pill) plus its vertical anchor. */
class MarkerArt(val drawable: Drawable, val anchorV: Float)

private fun cinemaMarkerArt(
    res: Resources,
    color: Int,
    name: String,
    showLabel: Boolean,
    cache: HashMap<String, MarkerArt>,
): MarkerArt = cache.getOrPut("$color|$showLabel|$name") { buildCinemaMarker(res, color, name, showLabel) }

private fun buildCinemaMarker(res: Resources, color: Int, name: String, showLabel: Boolean): MarkerArt {
    val d = res.displayMetrics.density
    val dot = 30f * d              // dot diameter (larger, easier to tap)
    val stroke = 3f * d
    val gap = 4f * d
    val pad = 8f * d               // transparent padding enlarges the tap target
    if (!showLabel) return buildDotMarker(res, color, dot, stroke, pad)
    val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        this.color = Color.WHITE
        textSize = 11f * d
        typeface = Typeface.DEFAULT_BOLD
    }
    val label = ellipsize(name, textPaint, 130f * d)
    val fm = textPaint.fontMetrics
    val textW = textPaint.measureText(label)
    val textH = fm.descent - fm.ascent
    val pillPadH = 6f * d
    val pillPadV = 3f * d
    val pillW = textW + pillPadH * 2
    val pillH = textH + pillPadV * 2
    val contentW = maxOf(dot, pillW)
    val w = (contentW + pad * 2).toInt().coerceAtLeast(1)
    val h = (pad + dot + gap + pillH + pad).toInt().coerceAtLeast(1)
    val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
    val cv = Canvas(bmp)
    val cx = w / 2f
    val dotCy = pad + dot / 2f
    cv.drawCircle(cx, dotCy, dot / 2f, Paint(Paint.ANTI_ALIAS_FLAG).apply { this.color = color })
    cv.drawCircle(cx, dotCy, dot / 2f - stroke / 2f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = stroke; this.color = Color.WHITE
    })
    val pillTop = pad + dot + gap
    val pillLeft = cx - pillW / 2f
    val r = pillH / 2f
    cv.drawRoundRect(pillLeft, pillTop, pillLeft + pillW, pillTop + pillH, r, r,
        Paint(Paint.ANTI_ALIAS_FLAG).apply { this.color = 0xCC101018.toInt() })
    cv.drawText(label, cx - textW / 2f, pillTop + pillPadV - fm.ascent, textPaint)
    return MarkerArt(BitmapDrawable(res, bmp), anchorV = dotCy / h)
}

/** A label-less dot with transparent padding preserving the large tap target. */
private fun buildDotMarker(res: Resources, color: Int, dot: Float, stroke: Float, pad: Float): MarkerArt {
    val size = (dot + pad * 2).toInt().coerceAtLeast(1)
    val bmp = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
    val cv = Canvas(bmp)
    val c = size / 2f
    cv.drawCircle(c, c, dot / 2f, Paint(Paint.ANTI_ALIAS_FLAG).apply { this.color = color })
    cv.drawCircle(c, c, dot / 2f - stroke / 2f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = stroke; this.color = Color.WHITE
    })
    return MarkerArt(BitmapDrawable(res, bmp), anchorV = 0.5f)
}

/** Trim a label with an ellipsis so it fits within maxWidth px. */
private fun ellipsize(text: String, paint: Paint, maxWidth: Float): String {
    if (paint.measureText(text) <= maxWidth) return text
    val ell = "…"
    var end = text.length
    while (end > 0 && paint.measureText(text.substring(0, end) + ell) > maxWidth) end--
    return text.substring(0, end).trimEnd() + ell
}

/** A rounded chip with the POI label drawn in white — always visible on the map. */
private fun labelChipDrawable(res: Resources, label: String, bgColor: Int): Drawable {
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
    val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = bgColor }
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
