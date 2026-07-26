# Keep Moshi-generated adapters and model fields
-keep class com.movienearme.data.model.** { *; }
-keepclassmembers class ** { @com.squareup.moshi.Json <fields>; }
