package com.movienearme.ui

import android.preference.PreferenceManager
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Place
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.movienearme.R
import com.movienearme.location.LatLng
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView

@Composable
fun PoiPicker(
    initial: LatLng?,
    onAdd: (label: String, lat: Double, lng: Double) -> Unit,
    onDismiss: () -> Unit,
) {
    val context = LocalContext.current
    val start = initial ?: LatLng(37.9755, 23.7348)

    val mapView = remember {
        Configuration.getInstance().load(
            context, PreferenceManager.getDefaultSharedPreferences(context)
        )
        Configuration.getInstance().userAgentValue = context.packageName
        MapView(context).apply {
            setTileSource(TileSourceFactory.MAPNIK)
            setMultiTouchControls(true)
            controller.setZoom(15.0)
            controller.setCenter(GeoPoint(start.lat, start.lng))
        }
    }

    var showName by remember { mutableStateOf(false) }
    var pickedLat by remember { mutableStateOf(0.0) }
    var pickedLng by remember { mutableStateOf(0.0) }
    var label by remember { mutableStateOf("") }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(Modifier.fillMaxSize()) {
            Box(Modifier.fillMaxSize()) {
                AndroidView(factory = { mapView }, modifier = Modifier.fillMaxSize())

                // Center pin — its tip marks the map centre.
                Icon(
                    Icons.Filled.Place,
                    contentDescription = null,
                    tint = Color(0xFF7C4DFF),
                    modifier = Modifier
                        .align(Alignment.Center)
                        .size(48.dp)
                        .offset(y = (-24).dp),
                )

                IconButton(
                    onClick = onDismiss,
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .statusBarsPadding()
                        .padding(8.dp),
                ) {
                    Surface(shape = RoundedCornerShape(50), tonalElevation = 4.dp) {
                        Icon(Icons.Filled.Close, contentDescription = stringResource(R.string.cancel),
                            modifier = Modifier.padding(6.dp))
                    }
                }

                Column(
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .navigationBarsPadding()
                        .padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        tonalElevation = 4.dp,
                        shadowElevation = 6.dp,
                    ) {
                        Text(
                            stringResource(R.string.poi_pick_hint),
                            Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                        )
                    }
                    Spacer(Modifier.height(12.dp))
                    Button(
                        onClick = {
                            val c = mapView.mapCenter
                            pickedLat = c.latitude
                            pickedLng = c.longitude
                            label = ""
                            showName = true
                        },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Icon(Icons.Filled.Place, contentDescription = null,
                            modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(stringResource(R.string.poi_save_here))
                    }
                }
            }
        }
    }

    if (showName) {
        AlertDialog(
            onDismissRequest = { showName = false },
            title = { Text(stringResource(R.string.poi_name_title)) },
            text = {
                OutlinedTextField(
                    value = label,
                    onValueChange = { label = it },
                    singleLine = true,
                    label = { Text(stringResource(R.string.poi_label_hint)) },
                )
            },
            confirmButton = {
                TextButton(
                    enabled = label.isNotBlank(),
                    onClick = {
                        onAdd(label.trim(), pickedLat, pickedLng)
                        showName = false
                        onDismiss()
                    },
                ) { Text(stringResource(R.string.save)) }
            },
            dismissButton = {
                TextButton(onClick = { showName = false }) {
                    Text(stringResource(R.string.cancel))
                }
            },
        )
    }
}
