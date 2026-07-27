package com.movienearme.data

import android.content.Context
import android.content.res.Configuration
import com.squareup.moshi.Moshi
import com.squareup.moshi.Types
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import java.util.Locale

/** A user-defined point of interest (e.g. "Home", "Work"). */
data class Poi(
    val id: String,
    val label: String,
    val lat: Double,
    val lng: Double,
)

/** User-configurable settings, persisted in SharedPreferences. */
data class AppSettings(
    val language: String = LANG_SYSTEM,      // "system" | "en" | "el"
    val nearMeKm: Int = 5,
    val filterAEnabled: Boolean = true,
    val filterAHours: Int = 3,
    val filterBEnabled: Boolean = true,
    val filterBHours: Int = 6,
    val pois: List<Poi> = emptyList(),
    // Origin the "Near me" filter measures from: null = my GPS location,
    // otherwise a POI id.
    val nearMeOriginId: String? = null,
) {
    companion object {
        const val LANG_SYSTEM = "system"
        const val LANG_EN = "en"
        const val LANG_EL = "el"
    }
}

class SettingsStore(context: Context) {
    private val prefs =
        context.applicationContext.getSharedPreferences("mnm_settings", Context.MODE_PRIVATE)

    private val poiAdapter by lazy {
        val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
        val type = Types.newParameterizedType(List::class.java, Poi::class.java)
        moshi.adapter<List<Poi>>(type)
    }

    fun load(): AppSettings = AppSettings(
        language = prefs.getString("language", AppSettings.LANG_SYSTEM)
            ?: AppSettings.LANG_SYSTEM,
        nearMeKm = prefs.getInt("nearMeKm", 5),
        filterAEnabled = prefs.getBoolean("filterAEnabled", true),
        filterAHours = prefs.getInt("filterAHours", 3),
        filterBEnabled = prefs.getBoolean("filterBEnabled", true),
        filterBHours = prefs.getInt("filterBHours", 6),
        pois = loadPois(),
        nearMeOriginId = prefs.getString("nearMeOriginId", null),
    )

    fun save(s: AppSettings) {
        prefs.edit()
            .putString("language", s.language)
            .putInt("nearMeKm", s.nearMeKm)
            .putBoolean("filterAEnabled", s.filterAEnabled)
            .putInt("filterAHours", s.filterAHours)
            .putBoolean("filterBEnabled", s.filterBEnabled)
            .putInt("filterBHours", s.filterBHours)
            .putString("pois", poiAdapter.toJson(s.pois))
            .putString("nearMeOriginId", s.nearMeOriginId)
            .apply()
    }

    private fun loadPois(): List<Poi> {
        val json = prefs.getString("pois", null) ?: return emptyList()
        return try {
            poiAdapter.fromJson(json) ?: emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun language(): String =
        prefs.getString("language", AppSettings.LANG_SYSTEM) ?: AppSettings.LANG_SYSTEM
}

/** Applies an in-app language override on top of the device locale. */
object LocaleManager {
    fun wrap(context: Context, language: String): Context {
        if (language == AppSettings.LANG_SYSTEM) return context
        val locale = Locale(language)
        Locale.setDefault(locale)
        val config = Configuration(context.resources.configuration)
        config.setLocale(locale)
        return context.createConfigurationContext(config)
    }
}
