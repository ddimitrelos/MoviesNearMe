package com.movienearme.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.movienearme.R
import com.movienearme.data.AppSettings

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsSheet(
    settings: AppSettings,
    onChange: (AppSettings) -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                stringResource(R.string.settings),
                fontSize = 22.sp, fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(bottom = 8.dp),
            )

            // --- Language ---
            SectionTitle(stringResource(R.string.settings_language))
            LanguageRow(stringResource(R.string.lang_system), settings.language == AppSettings.LANG_SYSTEM) {
                onChange(settings.copy(language = AppSettings.LANG_SYSTEM))
            }
            LanguageRow(stringResource(R.string.lang_en), settings.language == AppSettings.LANG_EN) {
                onChange(settings.copy(language = AppSettings.LANG_EN))
            }
            LanguageRow(stringResource(R.string.lang_el), settings.language == AppSettings.LANG_EL) {
                onChange(settings.copy(language = AppSettings.LANG_EL))
            }

            HorizontalDivider(Modifier.padding(vertical = 12.dp))

            // --- Near me radius ---
            SectionTitle(stringResource(R.string.settings_near_me_radius))
            var km by remember(settings.nearMeKm) { mutableStateOf(settings.nearMeKm.toFloat()) }
            Text(stringResource(R.string.settings_km, km.toInt()),
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Slider(
                value = km,
                onValueChange = { km = it },
                onValueChangeFinished = { onChange(settings.copy(nearMeKm = km.toInt())) },
                valueRange = 1f..20f,
                steps = 18,
            )

            HorizontalDivider(Modifier.padding(vertical = 12.dp))

            // --- Quick time filters ---
            SectionTitle(stringResource(R.string.settings_quick_filters))
            QuickFilterRow(
                title = stringResource(R.string.settings_filter_one),
                enabled = settings.filterAEnabled,
                hours = settings.filterAHours,
                onEnabledChange = { onChange(settings.copy(filterAEnabled = it)) },
                onHoursChange = { onChange(settings.copy(filterAHours = it)) },
            )
            Spacer(Modifier.height(8.dp))
            QuickFilterRow(
                title = stringResource(R.string.settings_filter_two),
                enabled = settings.filterBEnabled,
                hours = settings.filterBHours,
                onEnabledChange = { onChange(settings.copy(filterBEnabled = it)) },
                onHoursChange = { onChange(settings.copy(filterBHours = it)) },
            )

            Spacer(Modifier.height(20.dp))
            Button(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.close))
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(text, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
        color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(top = 4.dp, bottom = 4.dp))
}

@Composable
private fun LanguageRow(label: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = onClick)
        Spacer(Modifier.width(8.dp))
        Text(label)
    }
}

@Composable
private fun QuickFilterRow(
    title: String,
    enabled: Boolean,
    hours: Int,
    onEnabledChange: (Boolean) -> Unit,
    onHoursChange: (Int) -> Unit,
) {
    Column {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
            Text(stringResource(R.string.settings_show_filter), fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.width(8.dp))
            Switch(checked = enabled, onCheckedChange = onEnabledChange)
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(stringResource(R.string.settings_hours, hours),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f))
            IconButton(
                onClick = { if (hours > 1) onHoursChange(hours - 1) },
                enabled = enabled && hours > 1,
            ) { Icon(Icons.Filled.Remove, contentDescription = "-") }
            Text("$hours", fontWeight = FontWeight.Bold)
            IconButton(
                onClick = { if (hours < 24) onHoursChange(hours + 1) },
                enabled = enabled && hours < 24,
            ) { Icon(Icons.Filled.Add, contentDescription = "+") }
        }
    }
}
