package com.movienearme.data

import android.content.Context
import android.content.res.Configuration
import java.util.Locale

/** User-configurable settings, persisted in SharedPreferences. */
data class AppSettings(
    val language: String = LANG_SYSTEM,      // "system" | "en" | "el"
    val nearMeKm: Int = 5,
    val filterAEnabled: Boolean = true,
    val filterAHours: Int = 3,
    val filterBEnabled: Boolean = true,
    val filterBHours: Int = 6,
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

    fun load(): AppSettings = AppSettings(
        language = prefs.getString("language", AppSettings.LANG_SYSTEM)
            ?: AppSettings.LANG_SYSTEM,
        nearMeKm = prefs.getInt("nearMeKm", 5),
        filterAEnabled = prefs.getBoolean("filterAEnabled", true),
        filterAHours = prefs.getInt("filterAHours", 3),
        filterBEnabled = prefs.getBoolean("filterBEnabled", true),
        filterBHours = prefs.getInt("filterBHours", 6),
    )

    fun save(s: AppSettings) {
        prefs.edit()
            .putString("language", s.language)
            .putInt("nearMeKm", s.nearMeKm)
            .putBoolean("filterAEnabled", s.filterAEnabled)
            .putInt("filterAHours", s.filterAHours)
            .putBoolean("filterBEnabled", s.filterBEnabled)
            .putInt("filterBHours", s.filterBHours)
            .apply()
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
