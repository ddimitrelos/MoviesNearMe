package com.movienearme.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.movienearme.data.model.Cinema
import com.movienearme.data.model.Movie

private val CardColor = Color(0xF01C1C24)

/** A fancy callout of tiny movie-poster cards (with showtimes) for a cinema. */
@Composable
fun PosterCallout(
    cinema: Cinema,
    onPosterClick: (Movie) -> Unit,
    onOpenDetails: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // Each movie with its sorted showtimes at this cinema.
    val movies: List<Pair<Movie, List<String>>> = remember(cinema) {
        cinema.screenings
            .groupBy { it.movie.id }
            .map { (_, list) -> list.first().movie to list.map { it.startTime }.sorted() }
            .sortedBy { it.first.title }
    }
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = CardColor,
            shadowElevation = 12.dp,
        ) {
            Column(Modifier.widthIn(max = 340.dp).padding(12.dp)) {
                Row(
                    Modifier.clickable { onOpenDetails() },
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Filled.LocationOn, contentDescription = null,
                        tint = Color(0xFFE50914), modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(
                        cinema.name,
                        color = Color.White,
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    Icon(Icons.Filled.KeyboardArrowRight, contentDescription = null,
                        tint = Color.White.copy(alpha = 0.6f), modifier = Modifier.size(20.dp))
                }
                Spacer(Modifier.height(10.dp))
                Row(
                    Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    movies.forEach { (movie, times) ->
                        MovieCard(movie, times) { onPosterClick(movie) }
                    }
                }
            }
        }
        // Downward pointer toward the cinema pin.
        Canvas(Modifier.size(width = 22.dp, height = 11.dp)) {
            val path = Path().apply {
                moveTo(0f, 0f); lineTo(size.width, 0f); lineTo(size.width / 2f, size.height); close()
            }
            drawPath(path, CardColor)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun MovieCard(movie: Movie, times: List<String>, onClick: () -> Unit) {
    Column(
        Modifier.width(104.dp).clickable(onClick = onClick),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            Modifier
                .size(width = 104.dp, height = 150.dp)
                .clip(RoundedCornerShape(10.dp))
                .background(Color(0xFF2C2C36)),
            contentAlignment = Alignment.Center,
        ) {
            if (!movie.posterUrl.isNullOrBlank()) {
                AsyncImage(
                    model = movie.posterUrl,
                    contentDescription = movie.title,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                )
            } else {
                Icon(Icons.Filled.Movie, contentDescription = null,
                    tint = Color.White.copy(alpha = 0.5f), modifier = Modifier.size(30.dp))
            }
        }
        Spacer(Modifier.height(4.dp))
        Text(
            movie.title,
            color = Color.White,
            fontSize = 11.sp,
            lineHeight = 13.sp,
            fontWeight = FontWeight.Medium,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(4.dp))
        // Showtimes as small chips, wrapping onto multiple lines.
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            times.take(8).forEach { iso ->
                Surface(shape = RoundedCornerShape(6.dp), color = Color(0xFF3A3A46)) {
                    Text(
                        formatShowtime(iso),
                        color = Color.White,
                        fontSize = 10.sp,
                        modifier = Modifier.padding(horizontal = 5.dp, vertical = 2.dp),
                    )
                }
            }
        }
    }
}
