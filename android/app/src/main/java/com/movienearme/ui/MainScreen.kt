package com.movienearme.ui

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Directions
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.NearMe
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.movienearme.R
import com.movienearme.data.AppSettings
import com.movienearme.data.model.Cinema
import com.movienearme.data.model.Movie
import com.movienearme.data.model.ScreeningBrief
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(vm: MapViewModel) {
    val state by vm.state.collectAsState()

    Box(Modifier.fillMaxSize()) {
    PullToRefreshBox(
        isRefreshing = state.loading,
        onRefresh = { vm.refresh() },
        modifier = Modifier.fillMaxSize(),
    ) {
        Box(Modifier.fillMaxSize()) {
            OsmMap(
                cinemas = state.cinemas,
                userLocation = state.userLocation,
                selectedCinemaId = state.selectedCinema?.id,
                youAreHere = stringResource(R.string.you_are_here),
                pois = state.settings.pois,
                onCinemaClick = { vm.selectCinema(it) },
                modifier = Modifier.fillMaxSize(),
            )

            FilterBar(
                movies = state.movies,
                selectedMovie = state.selectedMovie,
                timeFilter = state.timeFilter,
                settings = state.settings,
                summerOnly = state.summerOnly,
                nearMe = state.nearMe,
                resultCount = state.cinemas.size,
                onMovieSelected = vm::selectMovie,
                onSelectTimeFilter = vm::selectTimeFilter,
                onToggleSummer = vm::toggleSummerOnly,
                onToggleNearMe = vm::toggleNearMe,
                onOpenSettings = { vm.openSettings(true) },
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .statusBarsPadding()
                    .padding(12.dp),
            )

            FloatingActionButton(
                onClick = { vm.refresh() },
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .navigationBarsPadding()
                    .padding(16.dp),
            ) {
                if (state.loading) {
                    CircularProgressIndicator(
                        Modifier.size(24.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                    )
                } else {
                    Icon(Icons.Filled.Refresh, contentDescription = stringResource(R.string.refresh))
                }
            }

            if (state.waking) {
                Surface(
                    color = MaterialTheme.colorScheme.tertiaryContainer,
                    modifier = Modifier
                        .align(Alignment.Center)
                        .padding(16.dp),
                    shape = RoundedCornerShape(20.dp),
                    shadowElevation = 6.dp,
                ) {
                    Row(
                        Modifier.padding(horizontal = 20.dp, vertical = 14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        CircularProgressIndicator(
                            Modifier.size(20.dp),
                            strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.onTertiaryContainer,
                        )
                        Text(stringResource(R.string.waking_server),
                            color = MaterialTheme.colorScheme.onTertiaryContainer)
                    }
                }
            }

            if (state.error) {
                Surface(
                    color = MaterialTheme.colorScheme.errorContainer,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(16.dp),
                    shape = RoundedCornerShape(12.dp),
                ) {
                    Text(
                        stringResource(R.string.error_unreachable),
                        Modifier.padding(16.dp),
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
            }
        }
    }

    state.selectedCinema?.let { cinema ->
        CinemaSheet(cinema = cinema, onDismiss = { vm.selectCinema(null) })
    }

    if (state.showSettings) {
        SettingsSheet(
            settings = state.settings,
            onChange = vm::updateSettings,
            onAddPoi = { vm.openSettings(false); vm.openPoiPicker(true) },
            onRemovePoi = vm::removePoi,
            onSetOrigin = vm::setNearMeOrigin,
            onDismiss = { vm.openSettings(false) },
        )
    }

    if (state.showPoiPicker) {
        PoiPicker(
            initial = state.userLocation,
            onAdd = { label, lat, lng -> vm.addPoi(label, lat, lng) },
            onDismiss = { vm.openPoiPicker(false); vm.openSettings(true) },
        )
    }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FilterBar(
    movies: List<Movie>,
    selectedMovie: Movie?,
    timeFilter: TimeFilter,
    settings: AppSettings,
    summerOnly: Boolean,
    nearMe: Boolean,
    resultCount: Int,
    onMovieSelected: (Movie?) -> Unit,
    onSelectTimeFilter: (TimeFilter) -> Unit,
    onToggleSummer: () -> Unit,
    onToggleNearMe: () -> Unit,
    onOpenSettings: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        tonalElevation = 4.dp,
        shadowElevation = 8.dp,
    ) {
        Column(Modifier.padding(12.dp)) {
            MovieDropdown(movies, selectedMovie, onMovieSelected)
            Spacer(Modifier.height(8.dp))

            // Time filters: Any, the enabled quick filters, Today.
            val timeChips = buildList {
                add(TimeFilter.ANY to stringResource(R.string.time_any))
                if (settings.filterAEnabled) {
                    add(TimeFilter.QUICK_A to
                        stringResource(R.string.time_next_hours, settings.filterAHours))
                }
                if (settings.filterBEnabled) {
                    add(TimeFilter.QUICK_B to
                        stringResource(R.string.time_next_hours, settings.filterBHours))
                }
                add(TimeFilter.TODAY to stringResource(R.string.time_today))
            }
            Row(
                Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                timeChips.forEach { (f, label) ->
                    FilterChip(
                        selected = timeFilter == f,
                        onClick = { onSelectTimeFilter(f) },
                        label = { Text(label) },
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = summerOnly,
                    onClick = onToggleSummer,
                    label = { Text(stringResource(R.string.filter_summer)) },
                    leadingIcon = {
                        Icon(Icons.Filled.WbSunny, contentDescription = null,
                            modifier = Modifier.size(18.dp))
                    },
                )
                FilterChip(
                    selected = nearMe,
                    onClick = onToggleNearMe,
                    label = { Text(stringResource(R.string.filter_near_me)) },
                    leadingIcon = {
                        Icon(Icons.Filled.NearMe, contentDescription = null,
                            modifier = Modifier.size(18.dp))
                    },
                )
            }
            Spacer(Modifier.height(6.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                val label = buildString {
                    append(stringResource(R.string.cinemas_count, resultCount))
                    if (summerOnly) { append(" "); append(stringResource(R.string.suffix_summer)) }
                    if (nearMe) { append(" "); append(stringResource(R.string.suffix_near_me)) }
                    selectedMovie?.let { append(" · "); append(it.title) }
                }
                Text(
                    text = label,
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f),
                )
                IconButton(onClick = onOpenSettings, modifier = Modifier.size(28.dp)) {
                    Icon(Icons.Filled.Settings,
                        contentDescription = stringResource(R.string.open_settings),
                        modifier = Modifier.size(20.dp))
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MovieDropdown(
    movies: List<Movie>,
    selected: Movie?,
    onSelected: (Movie?) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    val allMovies = stringResource(R.string.all_movies)
    ExposedDropdownMenuBox(
        expanded = expanded,
        onExpandedChange = { expanded = it },
    ) {
        OutlinedTextField(
            value = selected?.title ?: allMovies,
            onValueChange = {},
            readOnly = true,
            leadingIcon = { Icon(Icons.Filled.Movie, contentDescription = null) },
            trailingIcon = { Icon(Icons.Filled.ArrowDropDown, contentDescription = null) },
            label = { Text(stringResource(R.string.movie_label)) },
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor(),
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            DropdownMenuItem(
                text = { Text(allMovies) },
                onClick = { onSelected(null); expanded = false },
            )
            movies.forEach { movie ->
                DropdownMenuItem(
                    text = { Text(movie.title) },
                    onClick = { onSelected(movie); expanded = false },
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CinemaSheet(cinema: Cinema, onDismiss: () -> Unit) {
    val context = LocalContext.current
    val noMapsMsg = stringResource(R.string.no_directions_app)
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.LocationOn, contentDescription = null, tint = Color(0xFFE50914))
                Spacer(Modifier.width(8.dp))
                Column {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(cinema.name, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                        if (cinema.isSummer) {
                            Spacer(Modifier.width(8.dp))
                            Surface(
                                color = Color(0xFF00BFA5),
                                shape = RoundedCornerShape(6.dp),
                            ) {
                                Row(
                                    Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                                ) {
                                    Icon(
                                        Icons.Filled.WbSunny, contentDescription = null,
                                        tint = Color.White,
                                        modifier = Modifier.size(14.dp),
                                    )
                                    Text(
                                        stringResource(R.string.open_air),
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.SemiBold,
                                        color = Color.White,
                                    )
                                }
                            }
                        }
                    }
                    val distance = cinema.distanceKm?.let {
                        "  ·  " + stringResource(R.string.km_away, it)
                    } ?: ""
                    val sub = (cinema.address ?: "") + distance
                    if (sub.isNotBlank()) {
                        Text(sub, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }

            if (cinema.lat != null && cinema.lng != null) {
                Spacer(Modifier.height(14.dp))
                FilledTonalButton(
                    onClick = { openDirections(context, cinema, noMapsMsg) },
                ) {
                    Icon(Icons.Filled.Directions, contentDescription = null,
                        modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(stringResource(R.string.directions))
                }
            }

            Spacer(Modifier.height(16.dp))

            if (cinema.screenings.isEmpty()) {
                Text(stringResource(R.string.no_screenings))
            } else {
                groupByMovie(cinema.screenings).forEach { (movie, showtimes) ->
                    MovieShowtimes(movie.title, movie.genre, showtimes)
                    Spacer(Modifier.height(14.dp))
                }
            }
        }
    }
}

@Composable
private fun MovieShowtimes(title: String, genre: String?, screenings: List<ScreeningBrief>) {
    Column {
        Text(title, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
        genre?.let {
            Text(it, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.height(6.dp))
        Row(
            Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            screenings.forEach { s ->
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = MaterialTheme.colorScheme.secondaryContainer,
                ) {
                    Column(
                        Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            formatShowtime(s.startTime),
                            fontSize = 13.sp,
                            color = MaterialTheme.colorScheme.onSecondaryContainer,
                        )
                        s.hall?.let { hall ->
                            Text(
                                hall,
                                fontSize = 10.sp,
                                color = MaterialTheme.colorScheme.onSecondaryContainer
                                    .copy(alpha = 0.7f),
                            )
                        }
                    }
                }
            }
        }
    }
}

// --- helpers ---------------------------------------------------------------

private fun openDirections(context: android.content.Context, cinema: Cinema, noMapsMsg: String) {
    val lat = cinema.lat ?: return
    val lng = cinema.lng ?: return
    val label = Uri.encode(cinema.name)
    // Universal Google Maps directions link: opens the Maps app if installed,
    // otherwise the browser. Destination is the exact coordinates.
    val url = "https://www.google.com/maps/dir/?api=1" +
        "&destination=$lat,$lng&destination_place_id=&travelmode=driving" +
        "&dir_action=navigate&destination_name=$label"
    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
        // Prefer the Google Maps app when present.
        setPackage("com.google.android.apps.maps")
    }
    try {
        context.startActivity(intent)
    } catch (e: Exception) {
        // Maps app not installed — retry without a forced package (browser).
        try {
            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (e2: Exception) {
            Toast.makeText(context, noMapsMsg, Toast.LENGTH_SHORT).show()
        }
    }
}

private fun groupByMovie(screenings: List<ScreeningBrief>): List<Pair<Movie, List<ScreeningBrief>>> =
    screenings
        .groupBy { it.movie.id }
        .map { (_, list) -> list.first().movie to list.sortedBy { it.startTime } }
        .sortedBy { it.first.title }

private val outFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")

private fun formatShowtime(iso: String): String =
    try {
        val dt = LocalDateTime.parse(iso)
        val today = LocalDateTime.now().toLocalDate()
        val day = if (dt.toLocalDate() == today) {
            ""
        } else {
            dt.dayOfWeek.getDisplayName(TextStyle.SHORT, Locale.getDefault()) + " "
        }
        day + dt.format(outFmt)
    } catch (e: Exception) {
        iso
    }
